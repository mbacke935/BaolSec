"""Boucle de consommation de raw-events (C3, workflow W2).

1. Le message est lu par le consommateur durable « normalization » (partagé par toutes les instances).
2. Il est converti, enrichi et contrôlé (normalize.py).
3. L'événement normalisé est publié dans normalized-events avec Msg-Id = event_id.
4. Le message brut n'est acquitté qu'après le PubAck. Si l'acquittement se perd, le message
   est relivré, republié avec le même Msg-Id, et le broker écarte le doublon.
Échec définitif (contenu illisible ou non conforme) : file de rejet dès la première tentative.
Échec passager (broker) : nouvelle livraison, 5 tentatives au plus, puis file de rejet.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time

from baolsec_common.messaging import Broker, ProcessingError, ReceivedMessage, RetryPolicy, process

from . import metrics
from .normalize import Normalizer
from .sources import SourcesCache

log = logging.getLogger(__name__)
SERVICE = "normalization-worker"


class Worker:
    def __init__(self, broker: Broker, normalizer: Normalizer, cache: SourcesCache, *,
                 stream: str = "RAW_EVENTS", durable: str = "normalization",
                 output_subject: str = "normalized-events", batch: int = 200, publish_timeout_s: float = 5.0):
        self._broker = broker
        self._normalizer = normalizer
        self._cache = cache
        self._stream, self._durable, self._subject = stream, durable, output_subject
        self._batch, self._timeout = batch, publish_timeout_s
        self._policy = RetryPolicy(service=SERVICE, stream="raw-events", publisher=broker)
        self._stop = asyncio.Event()
        self._reasons: dict[int, str] = {}     # motif du dernier échec, pour la métrique des rejets

    def stop(self) -> None:
        self._stop.set()

    async def handle(self, msg: ReceivedMessage) -> None:
        try:
            doc = self._normalizer.run(msg.data)
        except ProcessingError as exc:
            self._reasons[id(msg)] = exc.reason_code
            raise
        body = json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        result = await self._broker.publish(self._subject, body, msg_id=doc["event"]["id"], timeout=self._timeout)
        source_type = doc["baolsec"]["source"]["type"]
        metrics.EVENTS.labels(source_type, "duplicate" if result.duplicate else "published").inc()
        metrics.DATASETS.labels(doc["event"]["dataset"], doc["event"]["action"]).inc()

    async def _one(self, msg: ReceivedMessage) -> None:
        started = time.perf_counter()
        try:
            outcome = await process(msg, self.handle, self._policy)
        except Exception:      # acquittement impossible (broker coupé) : le message sera relivré
            log.exception("traitement interrompu pour %s", msg.msg_id)
            return
        finally:
            reason = self._reasons.pop(id(msg), "processing_error")
        metrics.SECONDS.observe(time.perf_counter() - started)
        if outcome != "ack":
            metrics.EVENTS.labels(_source_type(msg), outcome).inc()
        if outcome == "dlq":
            metrics.REJECTIONS.labels(reason).inc()

    async def run(self) -> None:
        sub = None
        while not self._stop.is_set():
            if not self._cache.usable:
                # Référentiel des sources indisponible depuis trop longtemps : on suspend la lecture
                # plutôt que de publier des événements sans enrichissement. Les messages attendent dans raw-events.
                metrics.PAUSED.set(1)
                await asyncio.sleep(1)
                continue
            metrics.PAUSED.set(0)
            try:
                if sub is None:
                    sub = await self._broker.subscribe(self._stream, self._durable)
                msgs = await sub.fetch(self._batch, timeout=1)
            except Exception as exc:
                log.warning("lecture de %s impossible (%s), nouvel essai", self._stream, exc)
                sub = None
                await asyncio.sleep(2)
                continue
            if msgs:
                # Les messages d'un lot sont indépendants : traités en parallèle, chacun acquitté après son PubAck.
                await asyncio.gather(*(self._one(m) for m in msgs))


def _source_type(msg: ReceivedMessage) -> str:
    try:
        return json.loads(msg.data)["source"]["type"]
    except Exception:
        return "inconnu"


__all__ = ["Worker"]
