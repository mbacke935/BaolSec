"""Lecture de config.sources dans PostgreSQL (compte svc_normalisation, lecture seule, C4)."""
from __future__ import annotations

import psycopg

from . import SourceInfo

QUERY = """
SELECT id::text, name, source_type::text, host, criticality::text
FROM config.sources
"""


class PostgresSourceRegistry:
    def __init__(self, dsn: str):
        self._dsn = dsn

    async def load(self) -> list[SourceInfo]:
        async with await psycopg.AsyncConnection.connect(self._dsn, connect_timeout=5) as conn:
            await conn.set_read_only(True)
            async with conn.cursor() as cur:
                await cur.execute(QUERY)
                rows = await cur.fetchall()
        return [SourceInfo(id=r[0], name=r[1], source_type=r[2], host=r[3] or None, criticality=r[4])
                for r in rows]
