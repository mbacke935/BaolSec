"""Trackers de réception et de traitement des événements (C17 W6).

ReceptionTracker — consomme le flux raw-events :
  → enregistre last_received_at et incrémente received_count dans couverture.coverage_state.

ProcessingTracker — consomme le flux normalized-events :
  → enregistre last_processed_at et incrémente normalized_count.

Les deux trackers fonctionnent en mode fire-and-forget vis-à-vis des compteurs :
si PostgreSQL est indisponible lors d'un message, le message est NAK (il sera relivré),
et la lecture est suspendue jusqu'au retour de la base.

Chaque message est attendu de la forme :
  {"source_id": "<uuid>", "received_at": "<iso8601>", ...}
  (les champs supplémentaires sont ignorés — seule la source_id et l'horodatage comptent)
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

from . import metrics
from .repositories import Database, DatabaseUnavailable, bump_received, bump_processed

log = logging.getLogger(__name__)

_PAUSE_S = 2.0


def _parse_ts(value: str) -> datetime:
    """Parse un horodatage ISO 8601 (avec ou sans Z/offset) en datetime UTC."""
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value).astimezone(timezone.utc)


class ReceptionTracker:
    """Consomme le flux raw-events et met à jour last_received_at / received_count."""

    def __init__(self, db: Database):
        self._db = db

    async def run(self, consumer, stop: asyncio.Event) -> None:
        """Boucle principale ; s'arrête quand stop est positionné."""
        db_ok = False
        while not stop.is_set():
            if not db_ok:
                db_ok = await self._db.ping()
                if not db_ok:
                    log.warning("ReceptionTracker : PostgreSQL indisponible, lecture suspendue")
                    await _sleep(stop, _PAUSE_S)
                    continue
            try:
                msgs = await consumer.fetch(100, timeout=1)
            except Exception as exc:
                if stop.is_set():
                    break
                log.warning("ReceptionTracker : lecture raw-events impossible (%s), nouvel essai", exc)
                await _sleep(stop, _PAUSE_S)
                continue

            for msg in msgs:
                ok = await self._handle(msg)
                if not ok:
                    db_ok = False
                    break

    async def _handle(self, msg) -> bool:
        """Traite un message ; retourne False si PostgreSQL était indisponible."""
        try:
            doc = json.loads(msg.data)
            source_id = uuid.UUID(doc["source_id"])
            received_at = _parse_ts(doc.get("received_at") or doc.get("timestamp", ""))
        except Exception as exc:
            log.warning("ReceptionTracker : message illisible (%s), ignoré", exc)
            await msg.ack()
            return True

        try:
            async with self._db.connection() as conn:
                await bump_received(conn, source_id=source_id, received_at=received_at)
        except DatabaseUnavailable as exc:
            log.warning("ReceptionTracker : PostgreSQL (%s), NAK", exc)
            await msg.nak()
            return False

        source_name = str(source_id)[:8]
        metrics.EVENTS_RECEIVED.labels(source_name).inc()
        await msg.ack()
        return True


class ProcessingTracker:
    """Consomme le flux normalized-events et met à jour last_processed_at / normalized_count."""

    def __init__(self, db: Database):
        self._db = db

    async def run(self, consumer, stop: asyncio.Event) -> None:
        """Boucle principale ; s'arrête quand stop est positionné."""
        db_ok = False
        while not stop.is_set():
            if not db_ok:
                db_ok = await self._db.ping()
                if not db_ok:
                    log.warning("ProcessingTracker : PostgreSQL indisponible, lecture suspendue")
                    await _sleep(stop, _PAUSE_S)
                    continue
            try:
                msgs = await consumer.fetch(100, timeout=1)
            except Exception as exc:
                if stop.is_set():
                    break
                log.warning("ProcessingTracker : lecture normalized-events impossible (%s), nouvel essai", exc)
                await _sleep(stop, _PAUSE_S)
                continue

            for msg in msgs:
                ok = await self._handle(msg)
                if not ok:
                    db_ok = False
                    break

    async def _handle(self, msg) -> bool:
        """Traite un message ; retourne False si PostgreSQL était indisponible."""
        try:
            doc = json.loads(msg.data)
            source_id = uuid.UUID(doc["source_id"])
            processed_at = _parse_ts(doc.get("processed_at") or doc.get("timestamp", ""))
        except Exception as exc:
            log.warning("ProcessingTracker : message illisible (%s), ignoré", exc)
            await msg.ack()
            return True

        try:
            async with self._db.connection() as conn:
                await bump_processed(conn, source_id=source_id, processed_at=processed_at)
        except DatabaseUnavailable as exc:
            log.warning("ProcessingTracker : PostgreSQL (%s), NAK", exc)
            await msg.nak()
            return False

        source_name = str(source_id)[:8]
        metrics.EVENTS_PROCESSED.labels(source_name).inc()
        await msg.ack()
        return True


async def _sleep(stop: asyncio.Event, seconds: float) -> None:
    try:
        await asyncio.wait_for(stop.wait(), timeout=seconds)
    except asyncio.TimeoutError:
        pass


__all__ = ["ReceptionTracker", "ProcessingTracker"]
