from __future__ import annotations

import itertools
import json
from pathlib import Path

import pytest

from baolsec_common.messaging import BrokerUnavailable, PublishResult, StateConflict, StateEntry
from detector.rules import RulesCache, RuleValidator, FileRules

ROOT = Path(__file__).resolve().parents[3]
CONTRACTS = ROOT / "shared" / "contracts"
RULES = ROOT / "rules"
BASE_MS = 1_794_300_000_000          # 2026-11-10T09:20:00Z : « maintenant » des tests
_ids = itertools.count(1)


def iso(ms: int) -> str:
    from detector.timeutil import iso as _iso
    return _iso(ms)


def event(*, ts: int = BASE_MS, category="authentication", outcome="failure", user="admin", ip="10.0.4.23",
          host="srv-linux-01", mode="direct", event_id: str | None = None, **extra) -> dict:
    doc = {"@timestamp": iso(ts), "event": {"id": event_id or f"evt-{next(_ids):08d}", "kind": "event",
                                            "category": [category], "outcome": outcome},
           "baolsec": {"source": {"type": "linux", "ingestion_mode": mode}}}
    if user is not None:
        doc["user"] = {"name": user}
    if ip is not None:
        doc["source"] = {"ip": ip}
    if host is not None:
        doc["host"] = {"name": host}
    for path, value in extra.items():
        cur = doc
        parts = path.split("__")
        for p in parts[:-1]:
            cur = cur.setdefault(p, {})
        cur[parts[-1]] = value
    return doc


@pytest.fixture(scope="session")
def validator():
    return RuleValidator(CONTRACTS)


@pytest.fixture
def rule(validator):
    def make(text: str, version: int = 1):
        return validator.parse(text, version)
    return make


@pytest.fixture
def auth001(validator):
    return validator.parse((RULES / "AUTH-001.yml").read_text(encoding="utf-8"))


class FakeStore:
    """KV en mémoire : révisions et écriture conditionnelle comme JetStream."""

    def __init__(self):
        self.data: dict[str, StateEntry] = {}
        self.seq = 0
        self.conflicts_to_inject = 0
        self.ttls: dict[str, float] = {}

    async def get(self, key):
        return self.data.get(key)

    async def put(self, key, value, expected_revision, ttl_s):
        current = self.data.get(key)
        if self.conflicts_to_inject:
            self.conflicts_to_inject -= 1
            raise StateConflict(key)
        if (current.revision if current else 0) != expected_revision:
            raise StateConflict(key)
        self.seq += 1
        self.data[key] = StateEntry(key, value, self.seq)
        self.ttls[key] = ttl_s
        return self.seq

    async def scan(self):
        return list(self.data.values())

    def states(self):
        return {k: json.loads(v.value) for k, v in self.data.items()}


class FakeBroker:
    """Publie dans une liste ; écarte un Msg-Id déjà reçu, comme la fenêtre de déduplication."""

    def __init__(self):
        self.sent: list[tuple[str, dict, str]] = []
        self.ids: set[str] = set()
        self.fail_next = 0

    async def publish(self, subject, data, msg_id, timeout=5.0):
        if self.fail_next:
            self.fail_next -= 1
            raise BrokerUnavailable("arrêté")
        dup = msg_id in self.ids
        if not dup:
            self.ids.add(msg_id)
            self.sent.append((subject, json.loads(data), msg_id))
        return PublishResult("X", len(self.sent), dup)

    def alerts(self):
        return [d for s, d, _ in self.sent if s == "alerts"]


@pytest.fixture
async def rules_cache(validator):
    cache = RulesCache(FileRules(RULES), validator)
    await cache.refresh()
    return cache
