"""Tests du service Indexing Worker (C19)."""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from indexing_worker.indexers import EventIndexer, AlertIndexer, IncidentIndexer
from indexing_worker.opensearch_client import OpenSearchClient


# ── Helpers ────────────────────────────────────────────────────────────────────

def _msg(data: dict) -> MagicMock:
    m = MagicMock()
    m.data = json.dumps(data).encode()
    m.seq = 1
    m.ack = AsyncMock()
    m.nak = AsyncMock()
    return m


def _consumer(msgs: list) -> MagicMock:
    c = MagicMock()
    fetched = False

    async def fetch(batch, timeout):
        nonlocal fetched
        if not fetched:
            fetched = True
            return msgs
        await asyncio.sleep(0.1)
        return []

    c.fetch = fetch
    return c


# ── EventIndexer ──────────────────────────────────────────────────────────────

class TestEventIndexer:
    @pytest.fixture
    def os_client(self):
        c = MagicMock(spec=OpenSearchClient)
        c.bulk_index.return_value = (1, 0)
        return c

    async def test_indexe_evenement_valide(self, os_client):
        event = {
            "source_id": "s1",
            "event_id": "e1",
            "@timestamp": "2026-11-13T10:00:00Z",
            "category": "auth",
        }
        consumer = _consumer([_msg(event)])
        stop = asyncio.Event()
        stop.set()
        indexer = EventIndexer(os_client)
        await indexer.run(consumer, stop)
        # Le buffer est flushé à l'arrêt
        assert os_client.bulk_index.called

    async def test_message_illisible_est_ack(self, os_client):
        """Un message JSON invalide est quand même ACKé (pas de NAK)."""
        m = MagicMock()
        m.data = b"pas du json {"
        m.seq = 42
        m.ack = AsyncMock()
        consumer = _consumer([m])
        stop = asyncio.Event()
        stop.set()
        await EventIndexer(os_client).run(consumer, stop)
        m.ack.assert_called_once()


# ── AlertIndexer ──────────────────────────────────────────────────────────────

class TestAlertIndexer:
    @pytest.fixture
    def os_client(self):
        c = MagicMock(spec=OpenSearchClient)
        c.bulk_index.return_value = (1, 0)
        return c

    async def test_indexe_alerte_valide(self, os_client):
        alert = {
            "alert_id": "a1",
            "rule_id": "r1",
            "severity": "ELEVE",
            "fired_at": "2026-11-13T10:00:00Z",
        }
        msg = _msg(alert)
        consumer = _consumer([msg])
        stop = asyncio.Event()
        stop.set()
        await AlertIndexer(os_client).run(consumer, stop)
        msg.ack.assert_called_once()

    async def test_message_illisible_est_ack(self, os_client):
        m = MagicMock()
        m.data = b"{"
        m.ack = AsyncMock()
        consumer = _consumer([m])
        stop = asyncio.Event()
        stop.set()
        await AlertIndexer(os_client).run(consumer, stop)
        m.ack.assert_called_once()


# ── IncidentIndexer ───────────────────────────────────────────────────────────

class TestIncidentIndexer:
    @pytest.fixture
    def os_client(self):
        c = MagicMock(spec=OpenSearchClient)
        return c

    async def test_indexe_incident_valide(self, os_client):
        incident = {
            "incident_id": "i1",
            "title": "Tentative d'intrusion",
            "state": "OUVERT",
            "severity": "CRITIQUE",
            "opened_at": "2026-11-13T10:00:00Z",
            "alert_count": 3,
            "source_ids": ["s1", "s2"],
            "rule_ids": ["r1"],
        }
        msg = _msg(incident)
        consumer = _consumer([msg])
        stop = asyncio.Event()
        stop.set()
        await IncidentIndexer(os_client).run(consumer, stop)
        os_client.index_one.assert_called_once()
        call_args = os_client.index_one.call_args
        assert call_args[0][1] == "i1"
        msg.ack.assert_called_once()

    async def test_message_illisible_est_ack(self, os_client):
        m = MagicMock()
        m.data = b"}"
        m.ack = AsyncMock()
        consumer = _consumer([m])
        stop = asyncio.Event()
        stop.set()
        await IncidentIndexer(os_client).run(consumer, stop)
        m.ack.assert_called_once()
