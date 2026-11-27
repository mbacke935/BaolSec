"""Indexeurs NATS → OpenSearch (C19).

Trois indexeurs asynchrones :
  - EventIndexer   : flux NORMALIZED_EVENTS → index baolsec-events-AAAA.MM.JJ (_id = event.id)
  - AlertIndexer   : flux ALERTS            → index baolsec-alerts-AAAA.MM.JJ (_id = event.id de l'alerte)
  - IncidentIndexer: flux INCIDENTS         → index baolsec-incidents-current (_id = incident_id)

Garanties (ENF-05, C3 W5) :
  - un message n'est acquitté qu'une fois son document indexé ; en cas d'échec il est rendu au
    broker (nak avec délai) et relivré — aucun événement n'est perdu si OpenSearch s'arrête ;
  - identifiants déterministes : une relivraison réécrit le même document, sans doublon ;
  - un message illisible est acquitté et journalisé (il ne serait jamais lisible à la relivraison).

Les index des événements et des alertes sont quotidiens (purge par ancienneté, ES-09) ; celui des
incidents est unique, car un incident est mis à jour pendant toute sa vie : un index par jour
dupliquerait l'incident à chaque jour d'activité.

Les appels à opensearch-py (bibliothèque synchrone) sont délégués à run_in_executor.
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
_NAK_DELAY_S = 5.0
INCIDENTS_INDEX = "baolsec-incidents-current"


def _today_index(prefix: str) -> str:
    return f"{prefix}-{datetime.now(timezone.utc).strftime('%Y.%m.%d')}"


async def _sleep(stop: asyncio.Event, seconds: float) -> None:
    try:
        await asyncio.wait_for(stop.wait(), timeout=seconds)
    except asyncio.TimeoutError:
        pass


async def _nak(msg) -> None:
    try:
        await msg.nak(delay=_NAK_DELAY_S)
    except TypeError:            # adaptateur sans délai
        await msg.nak()


async def _settle(os_client: OpenSearchClient, pending: list[tuple[dict, Any]]) -> tuple[int, int]:
    """Indexe le lot puis acquitte les réussites et rend les échecs au broker."""
    if not pending:
        return 0, 0
    actions = [a for a, _ in pending]
    loop = asyncio.get_running_loop()
    failed = await loop.run_in_executor(None, os_client.bulk_index_ids, actions)
    ok = ko = 0
    for action, msg in pending:
        if str(action["_id"]) in failed:
            await _nak(msg)
            ko += 1
        else:
            await msg.ack()
            ok += 1
    return ok, ko


def _source_fields(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if not k.startswith("_")}


class _BatchIndexer:
    """Lecture par lots, indexation groupée, acquittement après succès."""

    name = "indexer"
    batch = _BULK_SIZE

    def __init__(self, os_client: OpenSearchClient) -> None:
        self._os = os_client

    def build(self, doc: dict) -> dict:  # pragma: no cover - redéfini
        raise NotImplementedError

    async def run(self, consumer, stop: asyncio.Event) -> None:
        pending: list[tuple[dict, Any]] = []
        last_flush = asyncio.get_running_loop().time()
        while not stop.is_set():
            now = asyncio.get_running_loop().time()
            if pending and (len(pending) >= self.batch or now - last_flush >= _BULK_TIMEOUT_S):
                ok, ko = await _settle(self._os, pending)
                if ko:
                    log.warning("%s : %d document(s) non indexé(s), relivrés plus tard", self.name, ko)
                pending.clear()
                last_flush = now
            try:
                msgs = await consumer.fetch(self.batch, timeout=1)
            except Exception as exc:  # noqa: BLE001
                if stop.is_set():
                    break
                log.warning("%s : lecture du flux impossible (%s)", self.name, exc)
                await _sleep(stop, _PAUSE_S)
                continue
            for msg in msgs:
                try:
                    doc = json.loads(msg.data)
                    action = self.build(doc)
                except Exception as exc:  # noqa: BLE001
                    log.warning("%s : message illisible (%s), ignoré", self.name, exc)
                    await msg.ack()
                    continue
                pending.append((action, msg))
        if pending:                                    # dernier lot à l'arrêt
            await _settle(self._os, pending)


class EventIndexer(_BatchIndexer):
    """NORMALIZED_EVENTS → baolsec-events-* (normalized_event/v1, ECS)."""

    name = "EventIndexer"

    def build(self, doc: dict) -> dict:
        event_id = doc["event"]["id"]
        return {"_op_type": "index", "_index": _today_index("baolsec-events"), "_id": event_id,
                **_source_fields(doc),
                "@timestamp": doc.get("@timestamp") or datetime.now(timezone.utc).isoformat()}


class AlertIndexer(_BatchIndexer):
    """ALERTS → baolsec-alerts-* (alert/v1, document immuable)."""

    name = "AlertIndexer"
    batch = 50

    def build(self, doc: dict) -> dict:
        # alert/v1 : l'identifiant de l'alerte est event.id (déterministe, C14) ; alert_id/id ne sont
        # acceptés que pour d'anciens messages.
        alert_id = ((doc.get("event") or {}).get("id")) or doc.get("alert_id") or doc.get("id")
        if not alert_id:
            raise ValueError("alerte sans identifiant (event.id)")
        ts = doc.get("@timestamp") or doc.get("fired_at") or datetime.now(timezone.utc).isoformat()
        return {"_op_type": "index", "_index": _today_index("baolsec-alerts"), "_id": alert_id,
                **_source_fields(doc), "@timestamp": ts}


class IncidentIndexer(_BatchIndexer):
    """INCIDENTS → baolsec-incidents-current : résumé dénormalisé, réécrit à chaque mise à jour."""

    name = "IncidentIndexer"
    batch = 20

    def build(self, doc: dict) -> dict:
        incident_id = doc.get("incident_id") or doc.get("id")
        if not incident_id:
            raise ValueError("incident sans identifiant")
        return {
            "_op_type": "index", "_index": INCIDENTS_INDEX, "_id": incident_id,
            "@timestamp": doc.get("last_activity_at") or doc.get("opened_at") or datetime.now(timezone.utc).isoformat(),
            "incident_id": incident_id,
            "title": doc.get("title", ""),
            "description": doc.get("description", ""),
            "state": doc.get("state", "ouvert"),
            "severity": doc.get("severity", "moyenne"),
            "opened_at": doc.get("opened_at"),
            "closed_at": doc.get("closed_at"),
            "last_activity_at": doc.get("last_activity_at"),
            "alert_count": doc.get("alert_count", 0),
            "source_ids": doc.get("source_ids", []),
            "rule_ids": doc.get("rule_ids", []),
        }
