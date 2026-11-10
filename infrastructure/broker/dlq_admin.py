#!/usr/bin/env python3
"""Exploitation de la file de rejet (flux DLQ, contrat dlq_message/v1) — carte C11.

Commandes :
    list    [filtres] [-v]            nombre de messages par service et par motif (-v : un message par ligne)
    show    SEQ                       message complet : motif, tentatives, contenu d'origine
    replay  [filtres] [--dry-run] [--keep]
                                      renvoie les messages dans leur flux d'origine, puis les retire de la file
    purge   [filtres] --yes           supprime les messages sélectionnés
    metrics [--port 9102]             expose la taille de la file pour Prometheus (service dlq-monitor)

Filtres : --service, --reason, --since (date ISO 8601), --grep (texte du message), --seq (répétable).

Reprise : le contenu d'origine est republié avec le Msg-Id « replay:<séquence dlq>:<identifiant d'origine> ».
Ce Msg-Id est nouveau, donc la fenêtre de déduplication du broker ne l'écarte pas ; l'identifiant de
l'événement (event_id, alert_id) ne change pas, donc les services en aval restent idempotents.
Un message refusé par la passerelle (original_stream = ingest) ou dont le contenu a été tronqué
n'est pas repris : la source doit le renvoyer.

Variables : BROKER_URL (défaut nats://localhost:4222), BROKER_TOKEN.
Usage (depuis la racine du dépôt) :
    uv run --with nats-py==2.16.0 infrastructure/broker/dlq_admin.py list
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone

STREAM = "DLQ"
REPLAY_SUBJECT = {"raw-events": "raw-events", "normalized-events": "normalized-events", "alerts": "alerts"}
TRUNCATED = "(contenu tronqué)"


# ---------------------------------------------------------------- logique sans broker (tests unitaires)

@dataclass(frozen=True)
class Entry:
    seq: int
    subject: str
    doc: dict
    raw: str = ""

    @property
    def service(self) -> str:
        return self.doc.get("service") or self.subject.removeprefix("dlq.")


class NotReplayable(Exception):
    pass


def parse_time(value: str) -> datetime:
    t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def select(entries: list[Entry], service: str | None = None, reason: str | None = None,
           since: str | None = None, grep: str | None = None, seqs: list[int] | None = None) -> list[Entry]:
    limit = parse_time(since) if since else None
    out = []
    for e in entries:
        if seqs and e.seq not in seqs:
            continue
        if service and e.service != service:
            continue
        if reason and e.doc.get("reason_code") != reason:
            continue
        if limit and parse_time(e.doc.get("failed_at", "1970-01-01T00:00:00Z")) < limit:
            continue
        if grep and grep not in (e.raw or json.dumps(e.doc, ensure_ascii=False)):
            continue
        out.append(e)
    return out


def replay_target(e: Entry) -> tuple[str, bytes, str]:
    """(sujet, contenu, Msg-Id) de la republication ; lève NotReplayable si la reprise est impossible."""
    d = e.doc
    stream = d.get("original_stream")
    if stream not in REPLAY_SUBJECT:
        raise NotReplayable(f"flux d'origine « {stream} » : la source doit renvoyer l'événement")
    if d.get("payload_encoding") != "json" or TRUNCATED in d.get("reason", ""):
        raise NotReplayable("contenu d'origine tronqué ou non JSON")
    return REPLAY_SUBJECT[stream], d["payload"].encode("utf-8"), f"replay:{e.seq}:{d['message_id']}"


def summary(entries: list[Entry]) -> Counter:
    return Counter((e.service, e.doc.get("reason_code", "?")) for e in entries)


# ---------------------------------------------------------------- accès au broker

async def connect():
    import nats
    url = os.environ.get("BROKER_URL", "nats://localhost:4222")

    async def quiet(_e):
        return None
    return await asyncio.wait_for(nats.connect(url, token=os.environ.get("BROKER_TOKEN") or None,
                                               allow_reconnect=False, error_cb=quiet), 10)


async def load(js, subject: str = "dlq.>") -> list[Entry]:
    """Lit tout le flux DLQ avec un consommateur éphémère, sans acquittement : la file n'est pas modifiée."""
    from nats.errors import TimeoutError as NatsTimeout
    from nats.js.api import AckPolicy, ConsumerConfig, DeliverPolicy

    info = await js.stream_info(STREAM)
    if info.state.messages == 0:
        return []
    sub = await js.pull_subscribe(subject, durable=None, stream=STREAM, config=ConsumerConfig(
        deliver_policy=DeliverPolicy.ALL, ack_policy=AckPolicy.NONE, inactive_threshold=30))
    out: list[Entry] = []
    try:
        while True:
            try:
                msgs = await sub.fetch(500, timeout=1)
            except (NatsTimeout, asyncio.TimeoutError):
                break
            for m in msgs:
                text = m.data.decode("utf-8", "replace")
                try:
                    doc = json.loads(text)
                except ValueError:
                    doc = {"reason": "message de rejet illisible", "reason_code": "?"}
                out.append(Entry(m.metadata.sequence.stream, m.subject, doc, text))
            if msgs and msgs[-1].metadata.num_pending == 0:
                break
    finally:
        await sub.unsubscribe()
    return out


def filters(a) -> dict:
    return dict(service=a.service, reason=a.reason, since=a.since, grep=a.grep, seqs=a.seq)


def subject_for(a) -> str:
    return f"dlq.{a.service}" if a.service else "dlq.>"


async def cmd_list(a) -> int:
    nc = await connect()
    try:
        entries = select(await load(nc.jetstream(), subject_for(a)), **filters(a))
    finally:
        await nc.close()
    if a.verbose:
        for e in entries:
            d = e.doc
            print(f"{e.seq:>8}  {d.get('failed_at', '?'):<24}  {e.service:<22}  {d.get('reason_code', '?'):<17}  "
                  f"{d.get('attempts', '?')}  {str(d.get('message_id', '?'))[:20]:<20}  {d.get('reason', '')[:80]}")
    for (service, reason), n in sorted(summary(entries).items()):
        print(f"{service:<22} {reason:<17} {n:>8}")
    print(f"total : {len(entries)}")
    return 0


async def cmd_show(a) -> int:
    nc = await connect()
    try:
        m = await nc.jetstream().get_msg(STREAM, a.seq_number)
    except Exception as exc:
        print(f"séquence {a.seq_number} introuvable : {exc}", file=sys.stderr)
        return 1
    finally:
        await nc.close()
    doc = json.loads(m.data)
    if doc.get("payload_encoding") == "json":
        try:
            doc["payload"] = json.loads(doc["payload"])
        except ValueError:
            pass
    print(json.dumps(doc, ensure_ascii=False, indent=2))
    return 0


async def cmd_replay(a) -> int:
    nc = await connect()
    js = nc.jetstream()
    done = skipped = 0
    try:
        for e in select(await load(js, subject_for(a)), **filters(a)):
            try:
                subject, data, msg_id = replay_target(e)
            except NotReplayable as exc:
                skipped += 1
                print(f"ignoré  {e.seq} : {exc}")
                continue
            if a.dry_run:
                print(f"à reprendre {e.seq} -> {subject} ({msg_id})")
                done += 1
                continue
            # Ordre sûr : republication confirmée, puis suppression. Un arrêt entre les deux laisse
            # le message dans la file ; une seconde reprise produit le même event_id, écarté en aval.
            await js.publish(subject, data, headers={"Nats-Msg-Id": msg_id}, timeout=5)
            if not a.keep:
                await js.delete_msg(STREAM, e.seq)
            done += 1
    finally:
        await nc.close()
    verb = "à reprendre" if a.dry_run else "repris"
    print(f"{verb} : {done}, ignorés : {skipped}")
    return 0


async def cmd_purge(a) -> int:
    if not a.yes:
        print("purge : ajouter --yes pour confirmer (la suppression est définitive)", file=sys.stderr)
        return 2
    nc = await connect()
    js = nc.jetstream()
    n = 0
    try:
        for e in select(await load(js, subject_for(a)), **filters(a)):
            await js.delete_msg(STREAM, e.seq)
            n += 1
    finally:
        await nc.close()
    print(f"supprimés : {n}")
    return 0


async def cmd_metrics(a) -> int:
    from prometheus_client import Gauge, start_http_server

    messages = Gauge("baolsec_dlq_messages", "Messages dans la file de rejet", ["service", "reason_code"])
    size = Gauge("baolsec_dlq_bytes", "Taille du flux DLQ en octets")
    oldest = Gauge("baolsec_dlq_oldest_age_seconds", "Âge du plus ancien message de la file de rejet")
    up = Gauge("baolsec_dlq_monitor_up", "1 si la dernière lecture du broker a réussi")
    start_http_server(a.port)
    print(f"métriques sur :{a.port}/metrics, lecture toutes les {a.interval} s", flush=True)
    while True:
        try:
            nc = await connect()
            try:
                js = nc.jetstream()
                info = await js.stream_info(STREAM)
                entries = await load(js)
            finally:
                await nc.close()
            messages.clear()
            for (service, reason), n in summary(entries).items():
                messages.labels(service, reason).set(n)
            size.set(info.state.bytes)
            times = [parse_time(e.doc["failed_at"]) for e in entries if "failed_at" in e.doc]
            oldest.set((datetime.now(timezone.utc) - min(times)).total_seconds() if times else 0)
            up.set(1)
        except Exception as exc:
            up.set(0)
            print(f"lecture du broker impossible : {exc}", file=sys.stderr, flush=True)
        await asyncio.sleep(a.interval)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Exploitation de la file de rejet BaolSec (C11)")
    sp = p.add_subparsers(dest="cmd", required=True)

    def with_filters(q):
        q.add_argument("--service", help="ex. normalization-worker")
        q.add_argument("--reason", help="parse_error, validation_error, mapping_error, index_rejected, processing_error")
        q.add_argument("--since", help="date ISO 8601 (failed_at)")
        q.add_argument("--grep", help="texte recherché dans le message de rejet")
        q.add_argument("--seq", type=int, action="append", help="séquence dans le flux DLQ (répétable)")
        return q

    with_filters(sp.add_parser("list")).add_argument("-v", "--verbose", action="store_true")
    sp.add_parser("show").add_argument("seq_number", type=int)
    r = with_filters(sp.add_parser("replay"))
    r.add_argument("--dry-run", action="store_true", help="affiche sans republier")
    r.add_argument("--keep", action="store_true", help="garde les messages dans la file après la reprise")
    with_filters(sp.add_parser("purge")).add_argument("--yes", action="store_true")
    m = sp.add_parser("metrics")
    m.add_argument("--port", type=int, default=9102)
    m.add_argument("--interval", type=float, default=15)
    return p


def main(argv: list[str] | None = None) -> int:
    a = parser().parse_args(argv)
    cmd = {"list": cmd_list, "show": cmd_show, "replay": cmd_replay, "purge": cmd_purge, "metrics": cmd_metrics}[a.cmd]
    try:
        return asyncio.run(cmd(a))
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"ÉCHEC : {type(exc).__name__} : {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
