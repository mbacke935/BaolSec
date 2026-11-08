from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from baolsec_common.messaging import BrokerUnavailable, PublishResult
from gateway.auth import hash_token
from gateway.sources_cache import SourcesCache
from gateway.sources_cache.file import FileSourceRegistry

ROOT = Path(__file__).resolve().parents[3]
RAW_SCHEMA = json.loads((ROOT / "shared/contracts/raw_event/v1/schema.json").read_text(encoding="utf-8"))
RAW_VALIDATOR = Draft202012Validator(RAW_SCHEMA, format_checker=FormatChecker())
DLQ_SCHEMA = json.loads((ROOT / "shared/contracts/dlq_message/v1/schema.json").read_text(encoding="utf-8"))
DLQ_VALIDATOR = Draft202012Validator(DLQ_SCHEMA, format_checker=FormatChecker())

LINUX_ID = "3f1c2a4e-8b7d-4c21-9a55-1e2f3a4b5c61"
WINDOWS_ID = "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c62"
FIREWALL_ID = "b2c3d4e5-f6a7-4b8c-9d0e-1f2a3b4c5d63"
DISABLED_ID = "c3d4e5f6-a7b8-4c9d-8e0f-2a3b4c5d6e64"
LINUX_TOKEN = "bsk_linux-test-token-000000000000000000000000"
WINDOWS_TOKEN = "bsk_windows-test-token-0000000000000000000000"
OLD_TOKEN = "bsk_revoked-test-token-0000000000000000000000"
DISABLED_TOKEN = "bsk_disabled-test-token-000000000000000000000"
FW_FINGERPRINT = "AA:BB:CC:DD"


def sources_document(fw_fingerprint: str = FW_FINGERPRINT) -> dict:
    return {"sources": [
        {"id": LINUX_ID, "name": "srv-linux-01", "source_type": "linux", "transport": "https",
         "credentials": [
             {"credential_type": "token", "secret_hash": hash_token(LINUX_TOKEN)},
             {"credential_type": "token", "secret_hash": hash_token(OLD_TOKEN), "revoked_at": "2026-11-01T00:00:00Z"},
         ]},
        {"id": WINDOWS_ID, "name": "pc-compta-02", "source_type": "windows", "transport": "https",
         "credentials": [{"credential_type": "token", "secret_hash": hash_token(WINDOWS_TOKEN),
                          "expires_at": "2099-01-01T00:00:00Z"}]},
        {"id": FIREWALL_ID, "name": "fw-edge-01", "source_type": "firewall", "transport": "syslog",
         "credentials": [{"credential_type": "client_cert", "cert_fingerprint": fw_fingerprint}]},
        {"id": DISABLED_ID, "name": "ancien-serveur", "source_type": "linux", "transport": "https",
         "is_enabled": False,
         "credentials": [{"credential_type": "token", "secret_hash": hash_token(DISABLED_TOKEN)}]},
    ]}


@pytest.fixture
async def cache(tmp_path) -> SourcesCache:
    path = tmp_path / "sources.json"
    path.write_text(json.dumps(sources_document()), encoding="utf-8")
    c = SourcesCache(FileSourceRegistry(path), refresh_s=30, max_stale_s=300)
    await c.refresh()
    return c


class FakeBroker:
    """Broker en mémoire : déduplication par Msg-Id, panne simulable."""

    def __init__(self):
        self.messages: list[tuple[str, dict]] = []
        self.ids: set[str] = set()
        self.down = False
        self.connected = True

    async def publish(self, subject, data, msg_id, timeout=5.0):
        if self.down:
            raise BrokerUnavailable("simulé")
        if msg_id in self.ids:
            return PublishResult("RAW_EVENTS", 0, True)
        self.ids.add(msg_id)
        self.messages.append((subject, json.loads(data)))
        return PublishResult("RAW_EVENTS", len(self.messages), False)

    def on(self, subject: str) -> list[dict]:
        return [m for s, m in self.messages if s == subject]


@pytest.fixture
def broker() -> FakeBroker:
    return FakeBroker()


def assert_raw_event(event: dict) -> None:
    errors = sorted(RAW_VALIDATOR.iter_errors(event), key=str)
    assert not errors, [e.message for e in errors]


def assert_dlq_message(message: dict) -> None:
    errors = sorted(DLQ_VALIDATOR.iter_errors(message), key=str)
    assert not errors, [e.message for e in errors]
