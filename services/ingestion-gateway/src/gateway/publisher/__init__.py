"""Publication des raw_event/v1 dans raw-events (Msg-Id = event_id), avec attente des PubAck."""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass

from baolsec_common.messaging import BrokerUnavailable, Publisher

from .. import metrics

SUBJECT = "raw-events"


@dataclass
class PublishSummary:
    stored: int = 0
    duplicates: int = 0


class RawEventPublisher:
    def __init__(self, broker: Publisher, timeout_s: float, concurrency: int):
        self._broker = broker
        self._timeout = timeout_s
        self._sem = asyncio.Semaphore(concurrency)

    async def publish_one(self, event: dict) -> bool:
        """Renvoie True si le broker signale un doublon. Lève BrokerUnavailable."""
        data = json.dumps(event, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        async with self._sem:
            start = time.perf_counter()
            try:
                result = await self._broker.publish(SUBJECT, data, msg_id=event["event_id"], timeout=self._timeout)
            except BrokerUnavailable:
                metrics.BROKER_ERRORS.inc()
                raise
            metrics.PUBLISH_SECONDS.observe(time.perf_counter() - start)
        return result.duplicate

    async def publish_all(self, events: list[dict]) -> PublishSummary:
        """Publie tout le lot ; si une seule publication échoue, BrokerUnavailable est levée
        et le lot entier doit être renvoyé par l'agent (les événements déjà stockés seront
        écartés comme doublons)."""
        results = await asyncio.gather(*(self.publish_one(e) for e in events), return_exceptions=True)
        errors = [r for r in results if isinstance(r, BaseException)]
        if errors:
            first = errors[0]
            raise first if isinstance(first, BrokerUnavailable) else BrokerUnavailable(str(first))
        dup = sum(1 for r in results if r is True)
        return PublishSummary(stored=len(events) - dup, duplicates=dup)
