"""Cohérence entre la topologie du broker et la règle de reprise du code (C11), sans broker."""
from __future__ import annotations

import json
from pathlib import Path

from baolsec_common.messaging import RetryPolicy

TOPOLOGY = json.loads((Path(__file__).resolve().parents[1] / "topology.json").read_text(encoding="utf-8"))
C = TOPOLOGY["consumer_defaults"]
POLICY = RetryPolicy(service="normalization-worker", stream="raw-events", publisher=None)


def test_memes_tentatives_et_memes_delais():
    assert C["attempts"] == POLICY.max_deliver == 5
    assert tuple(C["backoff"]) == POLICY.backoff
    assert len(C["backoff"]) == C["attempts"] - 1


def test_broker_relivre_sans_limite():
    """Le compte des tentatives est fait par le code : un message dont la dernière tentative
    n'a pas abouti doit revenir, sinon il resterait bloqué sans aller en file de rejet."""
    assert C["max_deliver"] == -1


def test_fenetre_de_deduplication_plus_longue_que_les_reprises():
    """Toutes les relivraisons d'un message (délais + délai d'acquittement à chaque tentative)
    tiennent dans la fenêtre : une republication pendant les reprises est écartée par le broker."""
    ack_wait = C["backoff"][0]          # avec des délais de relivraison, le broker prend le premier comme délai d'acquittement
    reprises = sum(C["backoff"]) + C["attempts"] * ack_wait
    assert TOPOLOGY["stream_defaults"]["duplicate_window"] >= 2 * reprises


def test_file_de_rejet_refuse_plutot_que_supprimer():
    dlq = next(s for s in TOPOLOGY["streams"] if s["name"] == "DLQ")
    assert dlq["discard"] == "new" and dlq["subjects"] == ["dlq.>"]
    assert dlq["max_age"] >= 30 * 86400
