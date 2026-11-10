#!/usr/bin/env python3
"""Copie le référentiel de développement (infrastructure/tls/dev/sources.json) dans config.sources.

Développement uniquement. Peut être relancé : une source existante est mise à jour, un identifiant
déjà présent n'est pas recopié. La passerelle et la normalisation peuvent ainsi lire indifféremment
le fichier ou la base (GATEWAY_SOURCE_REGISTRY, NORMALIZER_SOURCE_REGISTRY).

Variables : DATABASE_ADMIN_URL ; SOURCES_FILE (défaut infrastructure/tls/dev/sources.json).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[2]

UPSERT = """
INSERT INTO config.sources (id, name, source_type, transport, ingestion_mode, host, criticality, is_enabled)
VALUES (%(id)s, %(name)s, %(source_type)s, %(transport)s, %(ingestion_mode)s, %(host)s, %(criticality)s, %(is_enabled)s)
ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, source_type = EXCLUDED.source_type,
  transport = EXCLUDED.transport, ingestion_mode = EXCLUDED.ingestion_mode, host = EXCLUDED.host,
  criticality = EXCLUDED.criticality, is_enabled = EXCLUDED.is_enabled, updated_at = now()
"""
CREDENTIAL = """
INSERT INTO config.source_credentials (source_id, credential_type, secret_hash, cert_fingerprint)
SELECT %(source_id)s, %(credential_type)s, %(secret_hash)s, %(cert_fingerprint)s
WHERE NOT EXISTS (
  SELECT 1 FROM config.source_credentials
  WHERE source_id = %(source_id)s AND revoked_at IS NULL
    AND (secret_hash = %(secret_hash)s OR cert_fingerprint = %(cert_fingerprint)s))
"""


def main() -> int:
    url = os.environ.get("DATABASE_ADMIN_URL", "").replace("postgresql+psycopg://", "postgresql://", 1)
    path = Path(os.environ.get("SOURCES_FILE", ROOT / "infrastructure" / "tls" / "dev" / "sources.json"))
    if not url:
        print("DATABASE_ADMIN_URL manquant", file=sys.stderr)
        return 1
    if not path.exists():
        print(f"{path} absent : lancer d'abord make gateway-dev", file=sys.stderr)
        return 1
    sources = json.loads(path.read_text(encoding="utf-8"))["sources"]
    with psycopg.connect(url) as conn:
        for s in sources:
            conn.execute(UPSERT, {"host": None, "criticality": None, "ingestion_mode": "direct", "is_enabled": True, **s})
            for c in s.get("credentials", []):
                conn.execute(CREDENTIAL, {"source_id": s["id"], "credential_type": c["credential_type"],
                                          "secret_hash": c.get("secret_hash"), "cert_fingerprint": c.get("cert_fingerprint")})
    print(f"{len(sources)} source(s) copiée(s) dans config.sources")
    return 0


if __name__ == "__main__":
    sys.exit(main())
