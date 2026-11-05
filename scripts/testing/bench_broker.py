#!/usr/bin/env python3
"""Mesure le débit de publication du broker (ADR 0002, choix de sync_interval).

À lancer sur la machine de démonstration (CT-06), broker démarré :
    uv run --with nats-py==2.16.0 scripts/testing/bench_broker.py

Publie dans un flux temporaire BENCH_* (mêmes réglages que les flux réels), puis le supprime.
Pour comparer sync_interval 1s et always : modifier infrastructure/broker/nats-server.conf,
redémarrer le broker (make broker-restart) et relancer ce script.
"""
from __future__ import annotations

import asyncio
import os
import time
import uuid

import nats
from nats.js.api import StreamConfig

URL = os.environ.get("BROKER_URL", "nats://localhost:4222")
TOKEN = os.environ.get("BROKER_TOKEN")
SIZE = int(os.environ.get("BENCH_MSG_SIZE", "1000"))     # octets, ordre de grandeur d'un raw_event
TOTAL = int(os.environ.get("BENCH_MESSAGES", "20000"))
TARGET = 500                                              # ENF-02 : événements/s


async def main() -> None:
    nc = await nats.connect(URL, token=TOKEN)
    js = nc.jetstream()
    name = f"BENCH_{uuid.uuid4().hex[:6].upper()}"
    await js.add_stream(StreamConfig(name=name, subjects=[name.lower()], duplicate_window=600))
    payload = os.urandom(SIZE)
    try:
        t = time.perf_counter()
        for i in range(1000):
            await js.publish(name.lower(), payload, headers={"Nats-Msg-Id": f"s{i}"})
        seq = 1000 / (time.perf_counter() - t)

        sem = asyncio.Semaphore(50)

        async def one(i: int) -> None:
            async with sem:
                await js.publish(name.lower(), payload, headers={"Nats-Msg-Id": f"p{i}"})

        t = time.perf_counter()
        await asyncio.gather(*(one(i) for i in range(TOTAL)))
        par = TOTAL / (time.perf_counter() - t)
    finally:
        await js.delete_stream(name)
        await nc.close()

    print(f"Messages de {SIZE} octets")
    print(f"  publication séquentielle : {seq:8.0f} msg/s")
    print(f"  50 publications en vol   : {par:8.0f} msg/s")
    print(f"Chaque événement est écrit dans raw-events puis normalized-events : il faut au moins "
          f"{2 * TARGET} écritures/s pour {TARGET} événements/s (ENF-02), sans compter la charge des autres services.")


if __name__ == "__main__":
    asyncio.run(main())
