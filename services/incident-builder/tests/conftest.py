from __future__ import annotations

import copy
import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from baolsec_common.messaging import BrokerUnavailable, PublishResult
from incidents.alert_state import Alert
from incidents.contracts import Contracts
from incidents.repositories import DatabaseUnavailable, UnknownRule

ROOT = Path(__file__).resolve().parents[3]
CONTRACTS = ROOT / "shared" / "contracts"
EXAMPLE = json.loads((CONTRACTS / "alert" / "v1" / "examples" / "auth001_force_brute.json").read_text(encoding="utf-8"))


def alert_doc(**changes) -> dict:
    """Alerte AUTH-001 conforme à alert/v1, avec un alert_id différent à chaque appel sauf si `event_id` est donné."""
    doc = copy.deepcopy(EXAMPLE)
    doc["event"]["id"] = changes.pop("event_id", uuid.uuid4().hex + uuid.uuid4().hex)
    if "severity" in changes:
        doc["baolsec"]["severity"]["label"] = changes.pop("severity")
    if "rule" in changes:
        doc["rule"]["id"] = changes.pop("rule")
    assert not changes
    return doc


@pytest.fixture(scope="session")
def contracts():
    return Contracts(CONTRACTS)


@dataclass
class Msg:
    data: bytes
    delivery_count: int = 1
    subject: str = "alerts"
    msg_id: str | None = "m"
    stream_sequence: int = 1
    calls: list = field(default_factory=list)

    async def ack(self):
        self.calls.append("ack")

    async def nak(self, delay=None):
        self.calls.append("nak")

    async def in_progress(self):
        pass


def msg(doc, **kw) -> Msg:
    data = doc if isinstance(doc, bytes) else json.dumps(doc).encode()
    return Msg(data, msg_id=kw.pop("msg_id", None) or (doc.get("event", {}).get("id") if isinstance(doc, dict) else None), **kw)


class FakeBroker:
    """Publie dans une liste (file de rejet) ; une panne simulée fait échouer la publication."""

    def __init__(self):
        self.sent: list[tuple[str, dict, str]] = []
        self.fail_next = 0

    async def publish(self, subject, data, msg_id, timeout=5.0):
        if self.fail_next:
            self.fail_next -= 1
            raise BrokerUnavailable("arrêté")
        self.sent.append((subject, json.loads(data), msg_id))
        return PublishResult("X", len(self.sent), False)

    def dlq(self):
        return [d for s, d, _ in self.sent if s.startswith("dlq.")]


class FakeSink:
    """Destination en mémoire : clé alert_id, comme la clé primaire de alert_state."""

    def __init__(self):
        self.alerts: dict[str, Alert] = {}
        self.errors: list[Exception] = []       # levées une par une à chaque record()
        self.up = True
        self.record_calls = 0

    async def record(self, alert: Alert) -> bool:
        self.record_calls += 1
        if self.errors:
            raise self.errors.pop(0)
        if alert.alert_id in self.alerts:
            return False
        self.alerts[alert.alert_id] = alert
        return True

    async def ready(self) -> bool:
        return self.up


@pytest.fixture
def broker():
    return FakeBroker()


@pytest.fixture
def sink():
    return FakeSink()
