"""Tests des indexeurs NATS → OpenSearch (C19, corrigés lors de l'audit du 26/11/2026).

Règle vérifiée : un message n'est acquitté qu'après l'indexation réussie de son document ; sinon il
est rendu au broker (nak) pour être relivré. Auparavant, les événements et les alertes étaient
acquittés avant l'indexation : un arrêt d'OpenSearch les perdait définitivement.
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from indexing_worker.indexers import INCIDENTS_INDEX, AlertIndexer, EventIndexer, IncidentIndexer
from indexing_worker.opensearch_client import OpenSearchClient
from indexing_worker.templates import TEMPLATES

EVENT = {
    "@timestamp": "2026-11-13T10:00:00Z", "ecs": {"version": "9.5.0"},
    "event": {"id": "e1", "kind": "event", "category": ["authentication"], "action": "ssh_login",
              "outcome": "failure"},
    "message": "Échec de connexion SSH",
    "baolsec": {"contract": "normalized_event/v1", "source": {"id": "s1"}, "received_at": "2026-11-13T10:00:00Z",
                "timestamp_source": "original", "severity": {"label": "faible", "score": 1}},
}
ALERT = {"@timestamp": "2026-11-13T10:05:00Z", "event": {"id": "a" * 64, "kind": "alert"},
         "rule": {"id": "AUTH-001", "name": "Force brute", "version": "1"},
         "baolsec": {"contract": "alert/v1", "severity": {"label": "elevee", "score": 3},
                     "alert": {"event_ids": ["e1"]}}}
INCIDENT = {"incident_id": "i1", "title": "Tentative d'intrusion", "state": "ouvert", "severity": "critique",
            "opened_at": "2026-11-13T10:00:00Z", "last_activity_at": "2026-11-13T11:00:00Z"}


def _msg(data) -> MagicMock:
    m = MagicMock()
    m.data = data if isinstance(data, bytes) else json.dumps(data).encode()
    m.ack, m.nak = AsyncMock(), AsyncMock()
    return m


def _consumer(msgs: list, stop: asyncio.Event) -> MagicMock:
    c = MagicMock()
    state = {"done": False}

    async def fetch(batch, timeout):
        if not state["done"]:
            state["done"] = True
            stop.set()
            return msgs
        return []

    c.fetch = fetch
    return c


def _os(failed: set[str] | None = None) -> MagicMock:
    c = MagicMock(spec=OpenSearchClient)
    c.bulk_index_ids.return_value = failed or set()
    return c


async def _run(indexer_cls, os_client, msgs):
    stop = asyncio.Event()
    await indexer_cls(os_client).run(_consumer(msgs, stop), stop)


@pytest.mark.parametrize("cls,doc,expected_id", [
    (EventIndexer, EVENT, "e1"), (AlertIndexer, ALERT, "a" * 64), (IncidentIndexer, INCIDENT, "i1"),
])
async def test_document_indexe_puis_acquitte(cls, doc, expected_id):
    os_client, msg = _os(), _msg(doc)
    await _run(cls, os_client, [msg])
    (actions,), _ = os_client.bulk_index_ids.call_args
    assert actions[0]["_id"] == expected_id
    msg.ack.assert_awaited_once()
    msg.nak.assert_not_awaited()


@pytest.mark.parametrize("cls,doc,doc_id", [
    (EventIndexer, EVENT, "e1"), (AlertIndexer, ALERT, "a" * 64), (IncidentIndexer, INCIDENT, "i1"),
])
async def test_echec_d_indexation_rend_le_message_sans_l_acquitter(cls, doc, doc_id):
    """OpenSearch indisponible : le message doit être relivré, jamais perdu (ENF-05)."""
    os_client, msg = _os(failed={doc_id}), _msg(doc)
    await _run(cls, os_client, [msg])
    msg.ack.assert_not_awaited()
    msg.nak.assert_awaited_once()


async def test_lot_partiellement_refuse():
    ok_msg, ko_msg = _msg(EVENT), _msg({**EVENT, "event": {**EVENT["event"], "id": "e2"}})
    await _run(EventIndexer, _os(failed={"e2"}), [ok_msg, ko_msg])
    ok_msg.ack.assert_awaited_once()
    ko_msg.nak.assert_awaited_once()


@pytest.mark.parametrize("cls", [EventIndexer, AlertIndexer, IncidentIndexer])
async def test_message_illisible_acquitte_sans_indexation(cls):
    os_client, msg = _os(), _msg(b"pas du json {")
    await _run(cls, os_client, [msg])
    msg.ack.assert_awaited_once()


async def test_alerte_identifiee_par_event_id():
    """alert/v1 n'a ni alert_id ni id à la racine : l'ancien code indexait sans _id (doublons)."""
    os_client = _os()
    await _run(AlertIndexer, os_client, [_msg(ALERT)])
    action = os_client.bulk_index_ids.call_args.args[0][0]
    assert action["_id"] == ALERT["event"]["id"] and action["@timestamp"] == ALERT["@timestamp"]


async def test_incident_dans_un_index_unique():
    """Un incident mis à jour un autre jour ne doit pas être dupliqué dans un nouvel index."""
    os_client = _os()
    await _run(IncidentIndexer, os_client, [_msg(INCIDENT)])
    action = os_client.bulk_index_ids.call_args.args[0][0]
    assert action["_index"] == INCIDENTS_INDEX
    assert INCIDENTS_INDEX.startswith("baolsec-incidents-")      # couvert par le modèle et par la recherche


def test_modeles_alignes_sur_les_documents_ecs():
    """Les champs de recherche de l'API (EF-11) sont typés ; les documents ECS ne sont pas rejetés."""
    events = TEMPLATES["baolsec-events"]["template"]["mappings"]
    assert events["dynamic"] is True
    props = events["properties"]
    assert props["source"]["properties"]["ip"]["type"] == "ip"
    assert props["user"]["properties"]["name"]["type"] == "keyword"
    assert props["baolsec"]["properties"]["source"]["properties"]["id"]["type"] == "keyword"
    assert props["event"]["properties"]["original"]["index"] is False
    for name, body in TEMPLATES.items():
        assert body["index_patterns"] == [f"{name}-*"]


# ── Maintenance (ES-09) ───────────────────────────────────────────────────────

def test_retention_ne_supprime_que_les_index_quotidiens_expires():
    from datetime import date
    from indexing_worker.maintenance import expired_indices
    names = ["baolsec-events-2026.08.01", "baolsec-events-2026.11.20", "baolsec-alerts-2026.07.30",
             "baolsec-incidents-current", "autre-index"]
    assert expired_indices(names, date(2026, 11, 26), 90) == ["baolsec-alerts-2026.07.30", "baolsec-events-2026.08.01"]


def test_rotation_des_instantanes():
    from indexing_worker.maintenance import snapshots_to_delete
    snaps = [f"baolsec-2026.11.{d:02d}-010000" for d in range(1, 6)] + ["manuel"]
    assert snapshots_to_delete(snaps, keep=3) == ["baolsec-2026.11.01-010000", "baolsec-2026.11.02-010000"]
