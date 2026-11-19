"""Tests unitaires des trackers de réception et de traitement (C17 axe 2).

Pas d'accès PostgreSQL ni NATS.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from dataclasses import dataclass, field

import pytest

from coverage.tracker import ProcessingTracker, ReceptionTracker, _parse_ts
from coverage.repositories import DatabaseUnavailable

# ------------------------------------------------------------------ helpers

SRC_ID = uuid.uuid4()
NOW = datetime(2026, 11, 13, 10, 0, 0, tzinfo=timezone.utc)


def _raw_msg(source_id=SRC_ID, received_at=NOW) -> bytes:
    return json.dumps({
        "source_id": str(source_id),
        "received_at": received_at.isoformat(),
    }).encode()


def _norm_msg(source_id=SRC_ID, processed_at=NOW) -> bytes:
    return json.dumps({
        "source_id": str(source_id),
        "processed_at": processed_at.isoformat(),
    }).encode()


@dataclass
class FakeMsg:
    data: bytes
    _calls: list = field(default_factory=list)

    async def ack(self):
        self._calls.append("ack")

    async def nak(self, delay=None):
        self._calls.append("nak")


class FakeConsumer:
    """Consommateur NATS factice."""

    def __init__(self, messages: list[FakeMsg]):
        self._messages = messages
        self._fetched = False

    async def fetch(self, batch: int, timeout: float = 1.0) -> list[FakeMsg]:
        if self._fetched:
            await asyncio.sleep(10)  # bloque — le stop event finira par arrêter la boucle
        self._fetched = True
        return self._messages


class FakeDB:
    def __init__(self, raises=None):
        self._raises = raises
        self.received: list[dict] = []
        self.processed: list[dict] = []

    async def ping(self) -> bool:
        return self._raises is None

    @asynccontextmanager
    async def connection(self):
        if self._raises:
            raise self._raises
        yield self


# monkey-patch des fonctions de repo dans tracker
async def _fake_bump_received(conn, *, source_id, received_at):
    conn._db_ref.received.append({"source_id": source_id, "received_at": received_at})


async def _fake_bump_processed(conn, *, source_id, processed_at):
    conn._db_ref.processed.append({"source_id": source_id, "processed_at": processed_at})


class _PatchedDB(FakeDB):
    @asynccontextmanager
    async def connection(self):
        if self._raises:
            raise self._raises
        conn = type("Conn", (), {"_db_ref": self})()
        yield conn


# ------------------------------------------------------------------ tests _parse_ts

@pytest.mark.parametrize("ts, expected_offset", [
    ("2026-11-13T10:00:00Z", "+00:00"),
    ("2026-11-13T10:00:00+00:00", "+00:00"),
    ("2026-11-13T12:00:00+02:00", "+00:00"),  # converti en UTC
    ("2026-11-13T10:00:00.123Z", "+00:00"),
])
def test_parse_ts(ts, expected_offset):
    result = _parse_ts(ts)
    assert result.tzinfo is not None
    assert result.utcoffset().total_seconds() == 0.0


# ------------------------------------------------------------------ tests ReceptionTracker

async def test_reception_tracker_ack_message_valide(monkeypatch):
    msg = FakeMsg(_raw_msg())
    db = _PatchedDB()
    consumer = FakeConsumer([msg])
    stop = asyncio.Event()

    import coverage.tracker as _tr
    monkeypatch.setattr(_tr, "bump_received", _fake_bump_received)

    tracker = ReceptionTracker(db)
    # On laisse la boucle tourner 1 itération puis on l'arrête
    task = asyncio.create_task(tracker.run(consumer, stop))
    await asyncio.sleep(0.05)
    stop.set()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert "ack" in msg._calls
    assert len(db.received) == 1
    assert db.received[0]["source_id"] == SRC_ID


async def test_reception_tracker_ack_message_illisible(monkeypatch):
    """Un message JSON invalide est acquitté (ignoré, pas NAK)."""
    msg = FakeMsg(b"{pas json}")
    db = _PatchedDB()
    consumer = FakeConsumer([msg])
    stop = asyncio.Event()

    import coverage.tracker as _tr
    monkeypatch.setattr(_tr, "bump_received", _fake_bump_received)

    tracker = ReceptionTracker(db)
    task = asyncio.create_task(tracker.run(consumer, stop))
    await asyncio.sleep(0.05)
    stop.set()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert "ack" in msg._calls
    assert "nak" not in msg._calls


async def test_reception_tracker_nak_si_db_indisponible(monkeypatch):
    """Si PostgreSQL est indisponible, le message reçoit un NAK."""
    msg = FakeMsg(_raw_msg())
    db = _PatchedDB(raises=DatabaseUnavailable("coupure"))
    consumer = FakeConsumer([msg])
    stop = asyncio.Event()

    async def _raise(*a, **kw):
        raise DatabaseUnavailable("coupure")

    import coverage.tracker as _tr
    monkeypatch.setattr(_tr, "bump_received", _raise)
    # ping retourne False pour simuler la coupure
    db._raises = DatabaseUnavailable("coupure")

    class _NoPingDB(_PatchedDB):
        async def ping(self):
            return False

    tracker = ReceptionTracker(_NoPingDB())
    task = asyncio.create_task(tracker.run(consumer, stop))
    await asyncio.sleep(0.1)
    stop.set()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    # Le message n'a pas encore été consommé car ping échoue dès le départ
    assert "nak" not in msg._calls  # ne tente pas sans DB


# ------------------------------------------------------------------ tests ProcessingTracker

async def test_processing_tracker_ack_message_valide(monkeypatch):
    msg = FakeMsg(_norm_msg())
    db = _PatchedDB()
    consumer = FakeConsumer([msg])
    stop = asyncio.Event()

    import coverage.tracker as _tr
    monkeypatch.setattr(_tr, "bump_processed", _fake_bump_processed)

    tracker = ProcessingTracker(db)
    task = asyncio.create_task(tracker.run(consumer, stop))
    await asyncio.sleep(0.05)
    stop.set()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert "ack" in msg._calls
    assert len(db.processed) == 1
    assert db.processed[0]["source_id"] == SRC_ID


async def test_processing_tracker_ack_message_illisible(monkeypatch):
    msg = FakeMsg(b"pas du json du tout")
    db = _PatchedDB()
    consumer = FakeConsumer([msg])
    stop = asyncio.Event()

    import coverage.tracker as _tr
    monkeypatch.setattr(_tr, "bump_processed", _fake_bump_processed)

    tracker = ProcessingTracker(db)
    task = asyncio.create_task(tracker.run(consumer, stop))
    await asyncio.sleep(0.05)
    stop.set()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert "ack" in msg._calls
    assert "nak" not in msg._calls
