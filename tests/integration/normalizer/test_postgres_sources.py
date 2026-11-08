"""Lecture du référentiel des sources dans PostgreSQL pour l'enrichissement (C10 ; C4, section 5.2).

Nécessite TEST_POSTGRES_DSN : connexion administrateur à un serveur PostgreSQL de test.
Sans elle, le test est ignoré. Il crée puis supprime la base baolsec_normalizer_test.
"""
from __future__ import annotations

import os
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest

from normalizer.sources import SourcesCache
from normalizer.sources.postgres import PostgresSourceRegistry

ADMIN_DSN = os.environ.get("TEST_POSTGRES_DSN")
DB, ROLE = "baolsec_normalizer_test", "svc_normalisation_test"
pytestmark = pytest.mark.skipif(not ADMIN_DSN, reason="TEST_POSTGRES_DSN non défini")

SCHEMA = f"""
CREATE SCHEMA config;
CREATE TYPE config.source_type AS ENUM ('linux', 'windows', 'firewall', 'http');
CREATE TYPE config.transport AS ENUM ('https', 'syslog');
CREATE TYPE config.ingestion_mode AS ENUM ('direct', 'rejeu');
CREATE TYPE config.criticality AS ENUM ('faible', 'moyenne', 'elevee', 'critique');
CREATE TABLE config.sources (
  id uuid PRIMARY KEY, name text NOT NULL UNIQUE, source_type config.source_type NOT NULL,
  transport config.transport NOT NULL, ingestion_mode config.ingestion_mode NOT NULL DEFAULT 'direct',
  host text, criticality config.criticality, silence_threshold_s integer NOT NULL DEFAULT 600,
  expected_min_events_per_h integer, is_enabled boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now());
INSERT INTO config.sources (id, name, source_type, transport, host, criticality, is_enabled) VALUES
 ('11111111-1111-4111-8111-111111111111', 'SRV-LINUX-01', 'linux', 'https', 'srv-linux-01', 'critique', true),
 ('22222222-2222-4222-8222-222222222222', 'FW-EDGE-01', 'firewall', 'https', NULL, NULL, true),
 ('33333333-3333-4333-8333-333333333333', 'ANCIEN', 'linux', 'https', NULL, 'faible', false);
CREATE ROLE {ROLE} LOGIN PASSWORD 'test';
GRANT USAGE ON SCHEMA config TO {ROLE};
GRANT SELECT ON config.sources TO {ROLE};
"""


def with_db(dsn: str, db: str, user: str | None = None, password: str | None = None) -> str:
    parts = urlsplit(dsn)
    netloc = parts.netloc
    if user:
        netloc = f"{user}:{password}@{parts.hostname}" + (f":{parts.port}" if parts.port else "")
    return urlunsplit((parts.scheme, netloc, f"/{db}", parts.query, ""))


@pytest.fixture
def database():
    with psycopg.connect(ADMIN_DSN, autocommit=True) as admin:
        admin.execute(f"DROP DATABASE IF EXISTS {DB}")
        admin.execute(f"DROP ROLE IF EXISTS {ROLE}")
        admin.execute(f"CREATE DATABASE {DB}")
    with psycopg.connect(with_db(ADMIN_DSN, DB), autocommit=True) as conn:
        conn.execute(SCHEMA)
    yield with_db(ADMIN_DSN, DB, ROLE, "test")
    with psycopg.connect(ADMIN_DSN, autocommit=True) as admin:
        admin.execute(f"DROP DATABASE IF EXISTS {DB} WITH (FORCE)")
        admin.execute(f"DROP ROLE IF EXISTS {ROLE}")


async def test_nom_hote_et_criticite(database):
    cache = SourcesCache(PostgresSourceRegistry(database), refresh_s=30, max_stale_s=300)
    await cache.refresh()
    linux = cache.get("11111111-1111-4111-8111-111111111111")
    assert (linux.name, linux.host, linux.criticality) == ("SRV-LINUX-01", "srv-linux-01", "critique")
    fw = cache.get("22222222-2222-4222-8222-222222222222")
    assert fw.host is None and fw.criticality is None
    # Une source désactivée reste connue : un événement déjà accepté est encore enrichi.
    assert cache.get("33333333-3333-4333-8333-333333333333").name == "ANCIEN"


async def test_compte_en_lecture_seule(database):
    async with await psycopg.AsyncConnection.connect(database) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            await conn.execute("UPDATE config.sources SET criticality = 'faible'")
