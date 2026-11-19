"""Tests de résilience de la chaîne de collecte (carte C11, scénarios S1 et S2 de C2, ENF-05).

Chaque test compte les événements séparément :
    émis = normalisés + rejetés par la normalisation + rejetés par la passerelle
et vérifie qu'aucun event_id n'est présent deux fois. L'indexation (C19) ajoutera le comptage
des événements indexés au même test.

Pile : broker + passerelle + normalisation (make normalizer-up). Puis : make test-resilience.

Variables (valeurs par défaut pour Docker Compose) :
  GATEWAY_URL, BROKER_URL, BROKER_TOKEN
  BROKER_KILL_CMD / BROKER_START_CMD             arrêt brutal / redémarrage du broker
  NORMALIZER_KILL_CMD / NORMALIZER_START_CMD     arrêt brutal / redémarrage de la normalisation
  DLQ_ADMIN_CMD                                  commande de l'outil de la file de rejet
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shlex
import ssl
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
import nats
import pytest
from nats.js.api import AckPolicy, ConsumerConfig, DeliverPolicy

ROOT = Path(__file__).resolve().parents[3]
DEV = ROOT / "infrastructure" / "tls" / "dev"
COMPOSE = "docker compose --env-file .env -f infrastructure/compose/compose.yaml"
URL = os.environ.get("GATEWAY_URL", "https://localhost:8443")
BROKER_URL = os.environ.get("BROKER_URL", "nats://localhost:4222")
BROKER_TOKEN = os.environ.get("BROKER_TOKEN")
BROKER_KILL = os.environ.get("BROKER_KILL_CMD", f"{COMPOSE} kill broker")
BROKER_START = os.environ.get("BROKER_START_CMD", f"{COMPOSE} up -d --wait broker")
NORMALIZER_KILL = os.environ.get("NORMALIZER_KILL_CMD", f"{COMPOSE} kill normalization-worker")
NORMALIZER_START = os.environ.get("NORMALIZER_START_CMD", f"{COMPOSE} up -d --wait normalization-worker")
DLQ_ADMIN = os.environ.get("DLQ_ADMIN_CMD", f"{shlex.quote(sys.executable)} infrastructure/broker/dlq_admin.py")

TOKENS = dict(line.strip().split("=", 1) for line in (DEV / "tokens.env").read_text().splitlines() if "=" in line)
SOURCES = {s["name"]: s for s in json.loads((DEV / "sources.json").read_text())["sources"]}

pytestmark = pytest.mark.asyncio(loop_scope="function")


def run(cmd: str) -> subprocess.CompletedProcess:
    return subprocess.run(shlex.split(cmd), cwd=ROOT, check=True, timeout=180, capture_output=True, text=True)


def unique(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:16]}"


# ---------------------------------------------------------------- jeu d'essai

def records(marker: str, n: int) -> list[dict]:
    """n enregistrements : 1 sur 50 illisible pour la normalisation, 1 sur 100 refusé par la passerelle."""
    out = []
    for i in range(n):
        if i % 100 == 99:
            out.append({"log": 42, "m": f"{marker}-{i}"})                      # refusé à l'ingestion
        elif i % 50 == 49:
            out.append({"log": f"pas une ligne syslog {marker}-{i}"})           # parse_error
        else:
            out.append({"log": f"Nov  8 10:00:00 srv-test sshd[{4000 + i % 1000}]: Failed password for invalid user "
                               f"{marker}-{i} from 203.0.113.{i % 250 + 1} port {40000 + i} ssh2"})
    return out


EXPECTED_GATEWAY = lambda n: n // 100                                              # noqa: E731
EXPECTED_PARSE = lambda n: sum(1 for i in range(n) if i % 50 == 49 and i % 100 != 99)  # noqa: E731


# ---------------------------------------------------------------- émetteur au comportement d'agent

async def send_like_agent(token: str, recs: list[dict], batch: int = 100, pause: float = 0.05,
                          timeout: float = 240) -> int:
    """Envoie par lots ; sur 503, 429 ou connexion impossible, garde le lot et le renvoie (comme Fluent Bit).

    Renvoie le nombre de renvois. Un lot renvoyé produit les mêmes event_id : le broker écarte les doublons.
    """
    ctx = ssl.create_default_context(cafile=str(DEV / "sources-ca.crt"))
    retries = 0
    deadline = time.monotonic() + timeout
    async with httpx.AsyncClient(base_url=URL, verify=ctx, timeout=15) as c:
        for i in range(0, len(recs), batch):
            while True:
                assert time.monotonic() < deadline, "la passerelle n'a pas accepté les lots à temps"
                try:
                    r = await c.post("/ingest", json=recs[i:i + batch], headers={"Authorization": f"Bearer {token}"})
                    if r.status_code == 202:
                        break
                    assert r.status_code in (429, 503), r.text
                    wait = float(r.headers.get("retry-after", "1"))
                except httpx.TransportError:
                    wait = 1.0
                retries += 1
                await asyncio.sleep(min(wait, 2))
            await asyncio.sleep(pause)
    return retries


# ---------------------------------------------------------------- comptage dans le broker

async def read(stream: str, subject: str, marker: str, timeout: float = 5) -> list[dict]:
    """Messages des 15 dernières minutes de `stream` contenant `marker`."""
    nc = await asyncio.wait_for(nats.connect(BROKER_URL, token=BROKER_TOKEN, allow_reconnect=False), 10)
    found: list[dict] = []
    try:
        sub = await nc.jetstream().pull_subscribe(subject, durable=None, stream=stream, config=ConsumerConfig(
            deliver_policy=DeliverPolicy.BY_START_TIME, ack_policy=AckPolicy.NONE,
            opt_start_time=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 900))))
        while True:
            try:
                msgs = await sub.fetch(1000, timeout=timeout)
            except (asyncio.TimeoutError, nats.errors.TimeoutError):
                break
            found += [json.loads(m.data) for m in msgs if marker.encode() in m.data]
            if msgs and msgs[-1].metadata.num_pending == 0:
                break
    finally:
        await nc.close()
    return found


async def wait_normalizer_idle(timeout: float = 180) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            nc = await asyncio.wait_for(nats.connect(BROKER_URL, token=BROKER_TOKEN, allow_reconnect=False), 10)
            try:
                info = await nc.jetstream().consumer_info("RAW_EVENTS", "normalization")
            finally:
                await nc.close()
            if info.num_pending == 0 and info.num_ack_pending == 0:
                return
        except Exception:
            pass
        await asyncio.sleep(1)
    pytest.fail("la normalisation n'a pas vidé raw-events à temps")


async def account(marker: str, n: int) -> dict:
    """Comptage séparé, puis contrôle émis = normalisés + rejetés, sans doublon."""
    await wait_normalizer_idle()
    normalized = await read("NORMALIZED_EVENTS", "normalized-events", marker)
    dlq_norm = await read("DLQ", "dlq.normalization-worker", marker)
    dlq_gw = await read("DLQ", "dlq.ingestion-gateway", marker)
    ids = [d["event"]["id"] for d in normalized]
    counts = {"emis": n, "normalises": len(normalized), "rejet_normalisation": len(dlq_norm),
              "rejet_passerelle": len(dlq_gw), "doublons": len(ids) - len(set(ids))}
    print(f"\n{marker} : {counts}")
    assert counts["doublons"] == 0, f"{counts['doublons']} event_id en double"
    assert len({d["message_id"] for d in dlq_norm}) == len(dlq_norm), "rejet enregistré deux fois"
    assert counts["rejet_passerelle"] == EXPECTED_GATEWAY(n)
    assert counts["rejet_normalisation"] == EXPECTED_PARSE(n)
    assert all(d["reason_code"] == "parse_error" for d in dlq_norm)
    assert n == counts["normalises"] + counts["rejet_normalisation"] + counts["rejet_passerelle"], counts
    return counts


# ---------------------------------------------------------------- S1 : broker arrêté pendant l'envoi

async def test_s1_broker_arrete_pendant_l_envoi():
    marker, n = unique("s1"), 100
    run(BROKER_KILL)
    await asyncio.sleep(1)
    sender = asyncio.create_task(send_like_agent(TOKENS["DEV_TOKEN_LINUX"], records(marker, n)))
    await asyncio.sleep(5)
    run(BROKER_START)
    retries = await sender
    print(f"\nlots renvoyés pendant la coupure : {retries}")
    assert retries > 0, "la coupure aurait dû provoquer des renvois (503)"
    await account(marker, n)


# ---------------------------------------------------------------- S2 : service arrêté pendant le traitement

async def test_s2_normalisation_arretee_pendant_le_traitement():
    marker, n = unique("s2"), 100
    sender = asyncio.create_task(send_like_agent(TOKENS["DEV_TOKEN_LINUX"], records(marker, n), pause=0.02))
    await asyncio.sleep(1.0)
    run(NORMALIZER_KILL)
    await sender
    await asyncio.sleep(2)
    run(NORMALIZER_START)
    await account(marker, n)


# ---------------------------------------------------------------- reprise depuis la file de rejet

def raw_event(marker: str) -> dict:
    src = SOURCES["dev-linux"]
    now = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    line = f"<38>Nov  8 10:00:00 srv-test sshd[1842]: Failed password for {marker} from 10.0.4.23 port 51234 ssh2"
    return {"contract": "raw_event/v1",
            "event_id": hashlib.sha256(f"{src['id']}\ntext\n{line}".encode()).hexdigest(),
            "source": {"id": src["id"], "type": "linux", "ingestion_mode": "direct"},
            "transport": "https", "received_at": now, "agent": {"name": "fluent-bit", "read_at": now},
            "payload_format": "text", "payload": line}


async def test_reprise_depuis_la_file_de_rejet():
    """Un événement abandonné après 5 échecs passagers est repris avec dlq_admin.py replay :
    il est normalisé, sort de la file de rejet, et une seconde reprise ne crée pas de doublon."""
    marker = unique("replay")
    raw = raw_event(marker)
    dlq = {"contract": "dlq_message/v1", "message_id": raw["event_id"], "original_stream": "raw-events",
           "original_contract": "raw_event/v1", "service": "normalization-worker", "attempts": 5,
           "reason_code": "processing_error", "reason": "broker indisponible pendant les 5 tentatives",
           "failed_at": raw["received_at"], "payload_encoding": "json", "payload": json.dumps(raw)}
    nc = await asyncio.wait_for(nats.connect(BROKER_URL, token=BROKER_TOKEN), 10)
    try:
        await nc.jetstream().publish("dlq.normalization-worker", json.dumps(dlq).encode(),
                                     headers={"Nats-Msg-Id": f"dlq:normalization-worker:{raw['event_id']}:test"})
    finally:
        await nc.close()

    out = run(f"{DLQ_ADMIN} replay --service normalization-worker --grep {marker}").stdout
    assert "repris : 1" in out, out
    await wait_normalizer_idle()
    docs = await read("NORMALIZED_EVENTS", "normalized-events", marker)
    assert [d["event"]["id"] for d in docs] == [raw["event_id"]]
    assert await read("DLQ", "dlq.normalization-worker", marker) == [], "le message repris est retiré de la file"
    assert "total : 0" in run(f"{DLQ_ADMIN} list --grep {marker}").stdout

    # Reprise répétée (ex. : arrêt de l'outil entre la republication et la suppression) : même event_id,
    # le message normalisé est écarté par le broker (Msg-Id = event_id).
    nc = await asyncio.wait_for(nats.connect(BROKER_URL, token=BROKER_TOKEN), 10)
    try:
        await nc.jetstream().publish("raw-events", json.dumps(raw).encode(), headers={"Nats-Msg-Id": "replay:0:" + raw["event_id"]})
    finally:
        await nc.close()
    await wait_normalizer_idle()
    assert len(await read("NORMALIZED_EVENTS", "normalized-events", marker)) == 1
