#!/usr/bin/env python3
"""Crée ou met à jour les flux, les consommateurs durables et le bucket KV de BaolSec.

Lit infrastructure/broker/topology.json et infrastructure/state-store/detection-state.json.
Peut être relancé sans risque : un élément existant est mis à jour, jamais supprimé.

Variables : BROKER_URL (défaut nats://localhost:4222), BROKER_TOKEN.
Usage (depuis la racine du dépôt) :
    uv run --with nats-py==2.16.0 infrastructure/broker/init_broker.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import nats
from nats.js.api import (
    AckPolicy,
    ConsumerConfig,
    DeliverPolicy,
    DiscardPolicy,
    KeyValueConfig,
    RetentionPolicy,
    StorageType,
    StreamConfig,
)
from nats.js.errors import NotFoundError

HERE = Path(__file__).resolve().parent
TOPOLOGY = Path(os.environ.get("BROKER_TOPOLOGY", HERE / "topology.json"))
KV_FILE = Path(os.environ.get("STATE_STORE_CONFIG", HERE.parent / "state-store" / "detection-state.json"))


def stream_config(defaults: dict, s: dict) -> StreamConfig:
    cfg = {**defaults, **{k: v for k, v in s.items() if k != "consumers"}}
    return StreamConfig(
        name=cfg["name"],
        subjects=cfg["subjects"],
        storage=StorageType(cfg["storage"]),
        retention=RetentionPolicy(cfg["retention"]),
        discard=DiscardPolicy(cfg["discard"]),
        max_age=cfg["max_age"],
        max_bytes=cfg["max_bytes"],
        max_msg_size=cfg["max_msg_size"],
        duplicate_window=cfg["duplicate_window"],
        num_replicas=cfg["num_replicas"],
    )


def consumer_config(defaults: dict, durable: str) -> ConsumerConfig:
    return ConsumerConfig(
        durable_name=durable,
        ack_policy=AckPolicy(defaults["ack_policy"]),
        deliver_policy=DeliverPolicy(defaults["deliver_policy"]),
        max_deliver=defaults["max_deliver"],
        backoff=defaults["backoff"],
        max_ack_pending=defaults["max_ack_pending"],
    )


async def apply(url: str, token: str | None) -> None:
    topo = json.loads(TOPOLOGY.read_text(encoding="utf-8"))
    async def quiet(_exc: Exception) -> None:  # l'erreur finale est affichée par main()
        return None

    nc = await nats.connect(
        url, token=token or None, connect_timeout=5, allow_reconnect=False, error_cb=quiet
    )
    js = nc.jetstream()
    try:
        for s in topo["streams"]:
            cfg = stream_config(topo["stream_defaults"], s)
            try:
                info = await js.stream_info(cfg.name)
                current = getattr(info.config.retention, "value", info.config.retention)
                if current != cfg.retention.value:
                    raise SystemExit(
                        f"Le flux {cfg.name} existe avec la rétention « {current} » ; la nouvelle valeur « {cfg.retention.value} » "
                        "n'est pas modifiable sur un flux existant. En développement : make broker-reset (supprime les données du broker)."
                    )
                await js.update_stream(cfg)
                print(f"flux mis à jour      {cfg.name}")
            except NotFoundError:
                await js.add_stream(cfg)
                print(f"flux créé            {cfg.name}")
            for durable in s["consumers"]:
                # add_consumer crée le consommateur ou met à jour ses champs modifiables.
                await js.add_consumer(cfg.name, consumer_config(topo["consumer_defaults"], durable))
                print(f"consommateur prêt    {cfg.name}/{durable}")

        kv = json.loads(KV_FILE.read_text(encoding="utf-8"))
        kv_cfg = KeyValueConfig(
            bucket=kv["bucket"],
            history=kv["history"],
            ttl=kv["ttl"],
            storage=StorageType(kv["storage"]),
            max_bytes=kv["max_bytes"],
            max_value_size=kv["max_value_size"],
        )
        try:
            await js.key_value(kv["bucket"])
            print(f"bucket KV existant   {kv['bucket']}")
        except Exception:  # bucket absent
            await js.create_key_value(kv_cfg)
            print(f"bucket KV créé       {kv['bucket']}")
        # Délai de vie par entrée (C14) : chaque état de fenêtre expire à la fin de sa fenêtre + 2 min.
        stream = await js.stream_info(f"KV_{kv['bucket']}")
        if not stream.config.allow_msg_ttl:
            stream.config.allow_msg_ttl = True
            await js.update_stream(stream.config)
            print(f"délai de vie par entrée activé sur {kv['bucket']}")
    finally:
        await nc.close()


def main() -> int:
    url = os.environ.get("BROKER_URL", "nats://localhost:4222")
    try:
        asyncio.run(apply(url, os.environ.get("BROKER_TOKEN")))
    except Exception as exc:  # message lisible pour l'exploitant
        print(f"ÉCHEC : {type(exc).__name__} : {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
