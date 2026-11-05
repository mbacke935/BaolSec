"""Référentiel des sources lu dans un fichier JSON (tests et développement avant le déploiement de PostgreSQL).

Mêmes colonnes que config.sources et config.source_credentials (C4) ; mêmes règles de validité.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from . import Credential, Source


def _valid(cred: dict, now: datetime) -> bool:
    if cred.get("revoked_at"):
        return False
    exp = cred.get("expires_at")
    return not exp or datetime.fromisoformat(exp.replace("Z", "+00:00")) > now


class FileSourceRegistry:
    def __init__(self, path: Path):
        self._path = path

    async def load(self) -> list[Credential]:
        data = json.loads(self._path.read_text(encoding="utf-8"))
        now = datetime.now(timezone.utc)
        out: list[Credential] = []
        for s in data["sources"]:
            if not s.get("is_enabled", True):
                continue
            src = Source(
                id=s["id"], name=s["name"], source_type=s["source_type"],
                transport=s["transport"], ingestion_mode=s.get("ingestion_mode", "direct"),
            )
            for c in s.get("credentials", []):
                if _valid(c, now):
                    out.append(Credential(src, c["credential_type"], c.get("secret_hash"), c.get("cert_fingerprint")))
        return out
