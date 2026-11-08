"""Débit du service de normalisation (C9, objectif ENF-02 : 500 événements/s soutenus).

Publie N événements bruts directement dans raw-events (mélange des quatre types de sources, à partir
des exemples du contrat, chacun avec un event_id unique), puis mesure le temps nécessaire au service
pour tous les traiter (consommateur « normalization » vide). La passerelle n'est pas mesurée ici.

Usage (pile démarrée, service de normalisation lancé) :
    BROKER_URL=nats://localhost:4222 BROKER_TOKEN=… python scripts/testing/bench_normalizer.py [N]
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid
from pathlib import Path

import nats

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = sorted((ROOT / "shared/contracts/raw_event/v1/examples").glob("*.json"))


async def main(n: int) -> None:
    nc = await nats.connect(os.environ.get("BROKER_URL", "nats://localhost:4222"), token=os.environ.get("BROKER_TOKEN"))
    js = nc.jetstream()
    templates = [json.loads(p.read_text(encoding="utf-8")) for p in EXAMPLES]
    run = uuid.uuid4().hex[:8]

    async def idle() -> tuple[int, int]:
        info = await js.consumer_info("RAW_EVENTS", "normalization")
        return info.num_pending, info.num_ack_pending

    if await idle() != (0, 0):
        print("Le consommateur « normalization » n'est pas vide : attendre la fin du traitement en cours.")
        return
    start = time.perf_counter()
    pending = []
    for i in range(n):
        event = dict(templates[i % len(templates)], event_id=f"bench-{run}-{i:08d}")
        pending.append(js.publish("raw-events", json.dumps(event).encode(), headers={"Nats-Msg-Id": event["event_id"]}))
        if len(pending) == 500:
            await asyncio.gather(*pending)
            pending = []
    await asyncio.gather(*pending)
    published = time.perf_counter() - start
    while await idle() != (0, 0):
        await asyncio.sleep(0.2)
    total = time.perf_counter() - start
    await nc.close()
    print(f"{n} événements publiés en {published:.1f} s ; tous normalisés en {total:.1f} s : {n / total:.0f} événements/s")


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 20000))
