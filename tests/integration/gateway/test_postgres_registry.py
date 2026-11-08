"""Lecture du référentiel des sources dans PostgreSQL (colonnes de C4, section 5.2).

Nécessite TEST_POSTGRES_DSN : connexion administrateur à un serveur PostgreSQL de test,
par exemple postgresql://postgres:postgres@localhost:5432/postgres. Sans elle, le test est ignoré.
Le test crée puis supprime la base baolsec_gateway_test ; il ne touche à aucune autre base.
"""
from __future__ import annotations

import os
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest

from gateway.auth import hash_token
from gateway.sources_cache import SourcesCache
from gateway.sources_cache.postgres import PostgresSourceRegistry

ADMIN_DSN = os.environ.get("TEST_POSTGRES_DSN")
DB = "baolsec_gateway_test"
pytestmark = pytest.mark.skipif(not ADMIN_DSN, reason="TEST_POSTGRES_DSN non défini")

SCHEMA = """
CREATE SCHEMA config;
CREATE TYPE config.source_type AS ENUM ('linux', 'windows', 'firewall', 'http');
CREATE TYPE config.transport AS ENUM ('https', 'syslog');
CREATE TYPE config.ingestion_mode AS ENUM ('direct', 'rejeu');
CREATE TYPE config.credential_type AS ENUM ('token', 'client_cert');
CREATE TYPE config.criticality AS ENUM ('faible', 'moyenne', 'elevee', 'critique');
CREATE TABLE config.sources (
  id uuid PRIMARY KEY, name text NOT NULL UNIQUE, source_type config.source_type NOT NULL,
  transport config.transport NOT NULL, ingestion_mode config.ingestion_mode NOT NULL DEFAULT 'direct',
  host text, criticality config.criticality, silence_threshold_s integer NOT NULL DEFAULT 600, expected_min_events_per_h integer,
  is_enabled boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE config.source_credentials (
  id uuid PRIMARY KEY, source_id uuid NOT NULL REFERENCES config.sources(id),
  credential_type config.credential_type NOT NULL, secret_hash text, cert_fingerprint text UNIQUE,
  created_at timestamptz NOT NULL DEFAULT now(), expires_at timestamptz, revoked_at timestamptz);
CREATE ROLE svc_passerelle_test LOGIN PASSWORD 'test';
GRANT USAGE ON SCHEMA config TO svc_passerelle_test;
GRANT SELECT ON config.sources, config.source_credentials TO svc_passerelle_test;
"""

SOURCES = """
INSERT INTO config.sources (id, name, source_type, transport, is_enabled) VALUES
 ('11111111-1111-4111-8111-111111111111', 'srv-linux-01', 'linux', 'https', true),
 ('22222222-2222-4222-8222-222222222222', 'fw-edge-01', 'firewall', 'syslog', true),
 ('33333333-3333-4333-8333-333333333333', 'ancien', 'linux', 'https', false)
"""

CREDENTIALS = """
INSERT INTO config.source_credentials (id, source_id, credential_type, secret_hash, cert_fingerprint, expires_at, revoked_at) VALUES
 (gen_random_uuid(), '11111111-1111-4111-8111-111111111111', 'token', %(valid)s, NULL, NULL, NULL),
 (gen_random_uuid(), '11111111-1111-4111-8111-111111111111', 'token', %(revoked)s, NULL, NULL, now()),
 (gen_random_uuid(), '11111111-1111-4111-8111-111111111111', 'token', %(expired)s, NULL, now() - interval '1 day', NULL),
 (gen_random_uuid(), '22222222-2222-4222-8222-222222222222', 'client_cert', NULL, 'AB:CD:EF', NULL, NULL),
 (gen_random_uuid(), '33333333-3333-4333-8333-333333333333', 'token', %(disabled)s, NULL, NULL, NULL)
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
        admin.execute("DROP ROLE IF EXISTS svc_passerelle_test")
        admin.execute(f"CREATE DATABASE {DB}")
    with psycopg.connect(with_db(ADMIN_DSN, DB), autocommit=True) as conn:
        conn.execute(SCHEMA)
        conn.execute(SOURCES)
        conn.execute(CREDENTIALS, {"valid": hash_token("bsk_valide"), "revoked": hash_token("bsk_revoque"),
                            "expired": hash_token("bsk_expire"), "disabled": hash_token("bsk_desactive")})
    yield with_db(ADMIN_DSN, DB, "svc_passerelle_test", "test")
    with psycopg.connect(ADMIN_DSN, autocommit=True) as admin:
        admin.execute(f"DROP DATABASE IF EXISTS {DB} WITH (FORCE)")
        admin.execute("DROP ROLE IF EXISTS svc_passerelle_test")


async def test_seuls_les_identifiants_valides_sont_charges(database):
    cache = SourcesCache(PostgresSourceRegistry(database), refresh_s=30, max_stale_s=300)
    await cache.refresh()
    linux = cache.by_token_hash(hash_token("bsk_valide"))
    assert linux is not None and linux.name == "srv-linux-01" and linux.source_type == "linux"
    assert linux.ingestion_mode == "direct" and linux.transport == "https"
    for refused in ("bsk_revoque", "bsk_expire", "bsk_desactive"):
        assert cache.by_token_hash(hash_token(refused)) is None, refused
    fw = cache.by_fingerprint("abcdef")
    assert fw is not None and fw.transport == "syslog"


async def test_compte_en_lecture_seule(database):
    async with await psycopg.AsyncConnection.connect(database) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            await conn.execute("UPDATE config.sources SET is_enabled = false")
