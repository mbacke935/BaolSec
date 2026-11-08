"""Outils communs aux tests unitaires du service de normalisation."""
from __future__ import annotations

import asyncio
import json
from datetime import timezone
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from normalizer.enrich import Enricher
from normalizer.normalize import Normalizer
from normalizer.sources import SourcesCache
from normalizer.sources.file import FileSourceRegistry

ROOT = Path(__file__).resolve().parents[3]
CONTRACTS = ROOT / "shared" / "contracts"
FIXTURES = Path(__file__).parent / "fixtures"
SOURCES = {   # identifiants de tests/fixtures/sources.json
    "linux": "3f1c2a4e-8b7d-4c21-9a55-1e2f3a4b5c61",
    "windows": "7a9e0b12-3c4d-4e5f-8a6b-7c8d9e0f1a22",
    "firewall": "b2c3d4e5-f6a7-4b8c-9d0e-1f2a3b4c5d63",
    "http": "c4d5e6f7-a8b9-4c0d-8e1f-2a3b4c5d6e74",
}
NORMALIZED = Draft202012Validator(json.loads((CONTRACTS / "normalized_event/v1/schema.json").read_text()),
                                  format_checker=FormatChecker())
DLQ = Draft202012Validator(json.loads((CONTRACTS / "dlq_message/v1/schema.json").read_text()),
                           format_checker=FormatChecker())


def make_cache(path: Path = FIXTURES / "sources.json") -> SourcesCache:
    cache = SourcesCache(FileSourceRegistry(path), refresh_s=30, max_stale_s=300)
    asyncio.run(cache.refresh())
    return cache


@pytest.fixture(scope="session")
def cache() -> SourcesCache:
    return make_cache()


@pytest.fixture(scope="session")
def normalizer(cache) -> Normalizer:
    return Normalizer(CONTRACTS, Enricher(cache, ["41.82.0.0/16"]), timezone.utc)


def raw(kind: str, payload, fmt: str | None = None, received_at: str = "2026-11-02T10:40:53.120Z",
        read_at: str | None = None, event_id: str = "e" * 64) -> dict:
    """Enveloppe raw_event/v1 telle que la produit la passerelle."""
    if not isinstance(payload, str):
        payload, fmt = json.dumps(payload, ensure_ascii=False), fmt or "json"
    event = {"contract": "raw_event/v1", "event_id": event_id,
             "source": {"id": SOURCES[kind], "type": kind, "ingestion_mode": "direct"},
             "transport": "https", "received_at": received_at, "payload_format": fmt or "text", "payload": payload}
    event["agent"] = {"name": "fluent-bit", **({"read_at": read_at} if read_at else {})}
    return event


@pytest.fixture
def norm(normalizer):
    """norm(kind, payload, …) → événement normalisé, déjà contrôlé par le schéma du contrat."""
    def run(kind, payload, **kw):
        doc = normalizer.run(json.dumps(raw(kind, payload, **kw)).encode())
        NORMALIZED.validate(doc)
        return doc
    return run
