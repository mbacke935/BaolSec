"""Tests unitaires de l'outil de la file de rejet (C11), sans broker."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dlq_admin as d  # noqa: E402

RAW = json.dumps({"contract": "raw_event/v1", "event_id": "e" * 64})


def entry(seq, service="normalization-worker", reason="parse_error", stream="raw-events",
          encoding="json", payload=RAW, failed_at="2026-11-08T10:00:00.000Z", why="ligne illisible"):
    doc = {"contract": "dlq_message/v1", "message_id": "e" * 64, "original_stream": stream, "service": service,
           "attempts": 1, "reason_code": reason, "reason": why, "failed_at": failed_at,
           "payload_encoding": encoding, "payload": payload}
    return d.Entry(seq, f"dlq.{service}", doc, json.dumps(doc))


ENTRIES = [
    entry(1),
    entry(2, reason="validation_error", failed_at="2026-11-08T12:00:00Z"),
    entry(3, service="ingestion-gateway", stream="ingest", reason="validation_error", payload="srv-42 inconnu"),
]


def test_filtres():
    assert [e.seq for e in d.select(ENTRIES, service="normalization-worker")] == [1, 2]
    assert [e.seq for e in d.select(ENTRIES, reason="validation_error")] == [2, 3]
    assert [e.seq for e in d.select(ENTRIES, since="2026-11-08T11:00:00Z")] == [2]
    assert [e.seq for e in d.select(ENTRIES, grep="srv-42")] == [3]
    assert [e.seq for e in d.select(ENTRIES, seqs=[1, 3])] == [1, 3]


def test_resume_par_service_et_motif():
    assert d.summary(ENTRIES) == {("normalization-worker", "parse_error"): 1,
                                  ("normalization-worker", "validation_error"): 1,
                                  ("ingestion-gateway", "validation_error"): 1}


def test_reprise_vers_le_flux_d_origine_avec_nouveau_msg_id():
    subject, data, msg_id = d.replay_target(ENTRIES[0])
    assert subject == "raw-events"
    assert json.loads(data)["event_id"] == "e" * 64        # l'identifiant de l'événement ne change pas
    assert msg_id == f"replay:1:{'e' * 64}"                 # nouveau Msg-Id : pas écarté par la fenêtre de déduplication


@pytest.mark.parametrize("e", [
    entry(4, stream="ingest"),                                       # refus de la passerelle : la source renvoie
    entry(5, encoding="text", payload="ligne"),                      # contenu non JSON
    entry(6, why="trop gros (contenu tronqué)"),                     # contenu incomplet
])
def test_reprises_impossibles(e):
    with pytest.raises(d.NotReplayable):
        d.replay_target(e)


def test_purge_sans_confirmation_refusee(capsys):
    assert d.main(["purge"]) == 2
