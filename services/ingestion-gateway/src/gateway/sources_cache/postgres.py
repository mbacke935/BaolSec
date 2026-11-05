"""Lecture du référentiel des sources dans PostgreSQL (schéma config, compte en lecture seule)."""
from __future__ import annotations

import psycopg

from . import Credential, Source

QUERY = """
SELECT s.id::text, s.name, s.source_type::text, s.transport::text, s.ingestion_mode::text,
       c.credential_type::text, c.secret_hash, c.cert_fingerprint
FROM config.sources AS s
JOIN config.source_credentials AS c ON c.source_id = s.id
WHERE s.is_enabled
  AND c.revoked_at IS NULL
  AND (c.expires_at IS NULL OR c.expires_at > now())
"""


class PostgresSourceRegistry:
    def __init__(self, dsn: str):
        self._dsn = dsn

    async def load(self) -> list[Credential]:
        async with await psycopg.AsyncConnection.connect(self._dsn, connect_timeout=5) as conn:
            await conn.set_read_only(True)
            async with conn.cursor() as cur:
                await cur.execute(QUERY)
                rows = await cur.fetchall()
        return [
            Credential(
                source=Source(id=r[0], name=r[1], source_type=r[2], transport=r[3], ingestion_mode=r[4]),
                credential_type=r[5],
                secret_hash=r[6],
                cert_fingerprint=r[7],
            )
            for r in rows
        ]
