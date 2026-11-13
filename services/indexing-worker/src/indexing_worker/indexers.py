"""Indexeurs NATS → OpenSearch (C19).

Trois indexeurs asynchrones :
  - EventIndexer   : flux NORMALIZED_EVENTS → index baolsec-events-YYYY.MM.DD
  - AlertIndexer   : flux ALERTS            → index baolsec-alerts-YYYY.MM.DD
  - IncidentIndexer: flux INCIDENTS         → index baolsec-incidents-YYYY.MM.DD

Chaque message est un JSON. Les identifiants sont déterministes
(source_id:event_id, alert_id, incident_id) pour garantir l'idempotence.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

from .opensearch_client import OpenSearchClient

log = logging.getLogger(__name__)

_PAUSE_S = 2.0
_BULK_SIZE = 100
_BULK_TIMEOUT_S = 2.0


def _today_index(prefix: str) -> str:
    return f"{prefix}-{datetime.now(timezone.utc).strftime('%Y.%m.%d')}"


async def _sleep(stop: asyncio.Event, seconds: float) -> None:
    try:
        await asyncio.wait_for(stop.wait(), timeout=seconds)
    except asyncio.TimeoutError:
        pass


class EventIndexer:
    """Consomme NORMALIZED_EVENTS et indexe dans OpenSearch."""

    def __init__(self, os_client: OpenSearchClient) -> None:
        self._os = os_client

    async def run(self, consumer, stop: asyncio.Event) -> None:
        buffer: list[dict[str, Any]] = []
        last_flush = asyncio.get_event_loop().time()

        while not stop.is_set():
            # Flush si buffer plein ou timeout
            now = asyncio.get_event_loop().time()
            if buffer and (len(buffer) >= _BULK_SIZE or now - last_flush >= _BULK_TIMEOUT_S):
                await self._flush(buffer)
                buffer.clear()
                last_flush = now

            try:
                msgs = await consumer.fetch(_BULK_SIZE, timeout=1)
            except Exception as exc:
                if stop.is_set():
                    break
                log.warning("EventIndexer : fetch impossible (%s)", exc)
                await _sleep(stop, _PAUSE_S)
                continue

            for msg in msgs:
                try:
                    doc = json.loads(msg.data)
                    ts = doc.get("@timestamp") or doc.get("received_at") or datetime.now(timezone.utc).isoformat()
                    doc_id = f"{doc.get('source_id','')}-{doc.get('event_id', msg.seq)}"
                    action = {
                        "_op_type": "index",
                        "_index": _today_index("baolsec-events"),
                        "_id": doc_id,
                        "@timestamp": ts,
                        **{k: v for k, v in doc.items() if not k.startswith("_")},
                    }
                    buffer.append(action)
                    await msg.ack()
                except Exception as exc:
                    log.warning("EventIndexer : message illisible (%s), ignoré", exc)
                    await msg.ack()

        # Flush final
        if buffer:
            await self._flush(buffer)

    async def _flush(self, buffer: list[dict]) -> None:
        ok, err = self._os.bulk_index(buffer)
        log.debug("EventIndexer : indexé %d événements (%d erreurs)", ok, err)


class AlertIndexer:
    """Consomme ALERTS et indexe dans OpenSearch."""

    def __init__(self, os_client: OpenSearchClient) -> None:
        self._os = os_client

    async def run(self, consumer, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                msgs = await consumer.fetch(50, timeout=1)
            except Exception as exc:
                if stop.is_set():
                    break
                log.warning("AlertIndexer : fetch impossible (%s)", exc)
                await _sleep(stop, _PAUSE_S)
                continue

            actions = []
            for msg in msgs:
                try:
                    doc = json.loads(msg.data)
                    alert_id = doc.get("alert_id") or doc.get("id")
                    ts = doc.get("fired_at") or datetime.now(timezone.utc).isoformat()
                    action = {
                        "_op_type": "index",
                        "_index": _today_index("baolsec-alerts"),
                        "_id": alert_id,
                        "@timestamp": ts,
                        **{k: v for k, v in doc.items() if not k.startswith("_")},
                    }
                    actions.append(action)
                    await msg.ack()
                except Exception as exc:
                    log.warning("AlertIndexer : message illisible (%s), ignoré", exc)
                    await msg.ack()

            if actions:
                ok, err = self._os.bulk_index(actions)
                log.debug("AlertIndexer : indexé %d alertes (%d erreurs)", ok, err)


class IncidentIndexer:
    """Consomme INCIDENTS et indexe un résumé dénormalisé dans OpenSearch."""

    def __init__(self, os_client: OpenSearchClient) -> None:
        self._os = os_client

    async def run(self, consumer, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                msgs = await consumer.fetch(20, timeout=1)
            except Exception as exc:
                if stop.is_set():
                    break
                log.warning("IncidentIndexer : fetch impossible (%s)", exc)
                await _sleep(stop, _PAUSE_S)
                continue

            for msg in msgs:
                try:
                    doc = json.loads(msg.data)
                    incident_id = doc.get("incident_id") or doc.get("id")
                    ts = doc.get("opened_at") or datetime.now(timezone.utc).isoformat()
                    summary = {
                        "_op_type": "index",
                        "_index": _today_index("baolsec-incidents"),
                        "_id": incident_id,
                        "@timestamp": ts,
                        "incident_id":  incident_id,
                        "title":        doc.get("title", ""),
                        "description":  doc.get("description", ""),
                        "state":        doc.get("state", "OUVERT"),
                        "severity":     doc.get("severity", "MOYEN"),
                        "opened_at":    doc.get("opened_at"),
                        "closed_at":    doc.get("closed_at"),
                        "alert_count":  doc.get("alert_count", 0),
                        "source_ids":   doc.get("source_ids", []),
                        "rule_ids":     doc.get("rule_ids", []),
                    }
                    self._os.index_one(
                        summary["_index"], summary["_id"],
                        {k: v for k, v in summary.items() if not k.startswith("_")},
                    )
                    await msg.ack()
                except Exception as exc:
                    log.warning("IncidentIndexer : message illisible (%s), ignoré", exc)
                    await msg.ack()
