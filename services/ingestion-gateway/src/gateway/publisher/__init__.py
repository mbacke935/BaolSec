"""Publication des raw_event/v1 dans raw-events (Msg-Id = event_id), avec attente des PubAck."""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from baolsec_common.messaging import BrokerUnavailable, Publisher

from .. import metrics

SUBJECT = "raw-events"
DLQ_SUBJECT = "dlq.ingestion-gateway"
MAX_DLQ_PAYLOAD = 131072      # dlq_message/v1 : payload.maxLength


@dataclass
class PublishSummary:
    stored: int = 0
    duplicates: int = 0


class RawEventPublisher:
    def __init__(self, broker: Publisher, timeout_s: float, concurrency: int):
        self._broker = broker
        self._timeout = timeout_s
        self._sem = asyncio.Semaphore(concurrency)

    async def _publish(self, subject: str, body: dict, msg_id: str) -> bool:
        data = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        async with self._sem:
            start = time.perf_counter()
            try:
                result = await self._broker.publish(subject, data, msg_id=msg_id, timeout=self._timeout)
            except BrokerUnavailable:
                metrics.BROKER_ERRORS.inc()
                raise
            metrics.PUBLISH_SECONDS.observe(time.perf_counter() - start)
        return result.duplicate

    async def reject(self, source_id: str, content: str, reason: str) -> bool:
        """Conserve un événement refusé dans la file de rejet (dlq_message/v1), avant toute réponse.

        Ainsi chaque événement d'un lot a un résultat durable : publié dans raw-events, ou
        conservé dans la file de rejet avec son motif. Lève BrokerUnavailable.
        """
        message_id = hashlib.sha256(f"{source_id}|{content}".encode("utf-8")).hexdigest()
        try:
            json.loads(content)
            encoding = "json"
        except ValueError:
            encoding = "text"
        if len(content) > MAX_DLQ_PAYLOAD:
            content, encoding = content[:MAX_DLQ_PAYLOAD], "text"
            reason += " (contenu tronqué)"
        body = {
            "contract": "dlq_message/v1", "message_id": message_id,
            "original_stream": "ingest", "original_contract": "ingest_record",
            "service": "ingestion-gateway", "source_id": source_id, "attempts": 1,
            "reason_code": "validation_error", "reason": reason[:2000],
            "failed_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "payload_encoding": encoding, "payload": content or " ",
        }
        return await self._publish(DLQ_SUBJECT, body, f"dlq:ingestion-gateway:{message_id}")

    async def publish_one(self, event: dict) -> bool:
        """Renvoie True si le broker signale un doublon. Lève BrokerUnavailable."""
        return await self._publish(SUBJECT, event, event["event_id"])

    async def publish_all(self, events: list[dict], rejections: list[tuple[str, str, str]] = ()) -> PublishSummary:
        """Publie les événements valides et conserve les refusés (source_id, contenu, motif).

        Si une seule publication échoue, BrokerUnavailable est levée : l'émetteur renvoie le
        lot entier, et ce qui a déjà été stocké est écarté comme doublon (mêmes identifiants).
        """
        tasks = [self.publish_one(e) for e in events] + [self.reject(*r) for r in rejections]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        errors = [r for r in results if isinstance(r, BaseException)]
        if errors:
            first = errors[0]
            raise first if isinstance(first, BrokerUnavailable) else BrokerUnavailable(str(first))
        dup = sum(1 for r in results[:len(events)] if r is True)
        return PublishSummary(stored=len(events) - dup, duplicates=dup)
