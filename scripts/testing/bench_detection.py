#!/usr/bin/env python3
"""Débit de la détection (ENF-02) : N événements d'authentification publiés dans normalized-events,
mesure du temps mis par le consommateur « detection » pour tout traiter.

Le jeu mélange 80 % d'échecs répartis sur 2 000 couples utilisateur + IP (chaque événement lit et
écrit l'état de sa fenêtre dans le KV) et 20 % de succès ; quelques couples dépassent le seuil.

Usage : uv run --with nats-py==2.16.0 scripts/testing/bench_detection.py [N]
Variables : BROKER_URL (défaut nats://localhost:4222), BROKER_TOKEN.
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import sys
import time
import uuid
from datetime import datetime, timezone

import nats


async def main(n: int) -> None:
    nc = await nats.connect(os.environ.get("BROKER_URL", "nats://localhost:4222"), token=os.environ.get("BROKER_TOKEN"))
    js = nc.jetstream()
    run = uuid.uuid4().hex[:8]
    now = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    docs = []
    for i in range(n):
        k = random.randrange(2000)
        docs.append({"@timestamp": now, "ecs": {"version": "9.5.0"},
                     "event": {"id": f"bench{run}{i:09d}", "kind": "event", "category": ["authentication"],
                               "type": ["start"], "action": "ssh_login",
                               "outcome": "failure" if random.random() < 0.8 else "success"},
                     "user": {"name": f"bench{run}u{k}"}, "source": {"ip": f"10.{k // 250}.{k % 250}.9"},
                     "host": {"name": "srv-bench"},
                     "baolsec": {"source": {"type": "linux", "ingestion_mode": "direct"}}})
    t0 = time.perf_counter()
    for i in range(0, n, 500):
        await asyncio.gather(*(js.publish("normalized-events", json.dumps(d).encode(), headers={"Nats-Msg-Id": d["event"]["id"]})
                               for d in docs[i:i + 500]))
    published = time.perf_counter() - t0
    while True:
        info = await js.consumer_info("NORMALIZED_EVENTS", "detection")
        if info.num_pending == 0 and info.num_ack_pending == 0:
            break
        await asyncio.sleep(0.2)
    total = time.perf_counter() - t0
    print(f"{n} événements publiés en {published:.1f} s ; tous évalués après {total:.1f} s : {n / total:.0f} événements/s")
    await nc.close()


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 20000))
