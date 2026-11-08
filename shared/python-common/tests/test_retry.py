"""Tests unitaires de la règle « 5 tentatives puis dlq », sans broker."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from baolsec_common.messaging import BrokerUnavailable, ProcessingError, PublishResult, RetryPolicy, process

SCHEMA = Path(__file__).resolve().parents[3] / "shared" / "contracts" / "dlq_message" / "v1" / "schema.json"
VALIDATOR = Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8")), format_checker=FormatChecker())


@dataclass
class FakeMessage:
    data: bytes
    delivery_count: int
    subject: str = "raw-events"
    msg_id: str | None = "a" * 64
    stream_sequence: int = 42
    calls: list = field(default_factory=list)

    async def ack(self):
        self.calls.append(("ack",))

    async def nak(self, delay=None):
        self.calls.append(("nak", delay))

    async def in_progress(self):
        self.calls.append(("wip",))


class FakePublisher:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.sent: list[tuple[str, dict, str]] = []

    async def publish(self, subject, data, msg_id, timeout=5.0):
        if self.fail:
            raise BrokerUnavailable("arrêté")
        self.sent.append((subject, json.loads(data), msg_id))
        return PublishResult("DLQ", len(self.sent), False)


async def ok(_msg):
    return None


async def boom(_msg):
    raise ProcessingError("parse_error", "ligne Syslog illisible")


def policy(pub):
    return RetryPolicy(service="normalization-worker", stream="raw-events", publisher=pub)


async def test_succes_acquitte():
    msg = FakeMessage(b'{"x":1}', 1)
    assert await process(msg, ok, policy(FakePublisher())) == "ack"
    assert msg.calls == [("ack",)]


@pytest.mark.parametrize("attempt, delay", [(1, 5), (2, 15), (3, 30), (4, 60)])
async def test_echec_relivre_avec_delai_croissant(attempt, delay):
    msg = FakeMessage(b"x", attempt)
    pub = FakePublisher()
    assert await process(msg, boom, policy(pub)) == "retry"
    assert msg.calls == [("nak", delay)]
    assert pub.sent == []


async def test_cinquieme_echec_publie_dlq_conforme_puis_acquitte():
    msg = FakeMessage(b'{"contract":"raw_event/v1"}', 5)
    pub = FakePublisher()
    assert await process(msg, boom, policy(pub)) == "dlq"
    subject, dlq, msg_id = pub.sent[0]
    assert subject == "dlq.normalization-worker"
    assert msg_id == f"dlq:normalization-worker:{'a' * 64}"
    assert sorted(VALIDATOR.iter_errors(dlq), key=str) == []
    assert dlq["attempts"] == 5 and dlq["reason_code"] == "parse_error" and dlq["payload_encoding"] == "json"
    assert msg.calls == [("ack",)]


async def test_dlq_injoignable_pas_d_acquittement():
    msg = FakeMessage(b"x", 5)
    assert await process(msg, boom, policy(FakePublisher(fail=True))) == "retry"
    assert msg.calls == []


async def test_contenu_binaire_et_trop_long():
    pub = FakePublisher()
    await process(FakeMessage(b"\xff\xfe", 5), boom, policy(pub))
    await process(FakeMessage(b"z" * 200_000, 5, msg_id="b" * 64), boom, policy(pub))
    binaire, long = pub.sent[0][1], pub.sent[1][1]
    assert binaire["payload_encoding"] == "base64"
    assert len(long["payload"]) == 131072 and long["reason"].endswith("(contenu tronqué)")
    for _, dlq, _ in pub.sent:
        assert sorted(VALIDATOR.iter_errors(dlq), key=str) == []


async def permanent_boom(_msg):
    raise ProcessingError("parse_error", "format inconnu", permanent=True)


async def test_echec_definitif_part_en_dlq_des_la_premiere_tentative():
    pub = FakePublisher()
    msg = FakeMessage(b"ligne illisible", delivery_count=1)
    assert await process(msg, permanent_boom, policy(pub)) == "dlq"
    assert msg.calls == [("ack",)]
    subject, dlq, _ = pub.sent[0]
    assert subject == "dlq.normalization-worker"
    assert dlq["attempts"] == 1 and dlq["reason_code"] == "parse_error"
    VALIDATOR.validate(dlq)


async def test_echec_definitif_sans_dlq_joignable_non_acquitte():
    msg = FakeMessage(b"ligne illisible", delivery_count=1)
    assert await process(msg, permanent_boom, policy(FakePublisher(fail=True))) == "retry"
    assert msg.calls == []
