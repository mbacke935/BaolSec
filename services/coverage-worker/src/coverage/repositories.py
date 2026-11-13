"""Accès PostgreSQL du service Couverture (compte svc_couverture).

Schémas lus/écrits :
  - config.sources         (SELECT) : seuils de silence et d'activité attendue
  - couverture.*           (SELECT/INSERT/UPDATE/DELETE)

La classe `Database` expose le pool de connexions. Chaque fonction reçoit
la connexion (transaction) de l'appelant pour garantir l'atomicité.
"""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import AsyncIterator

import psycopg
from psycopg_pool import AsyncConnectionPool, PoolTimeout


# ------------------------------------------------------------------ exceptions

class DatabaseUnavailable(Exception):
    """PostgreSQL injoignable, trop lent ou transaction abandonnée."""


# ------------------------------------------------------------------ pool

class Database:
    def __init__(self, dsn: str, *, max_size: int = 3, timeout_s: float = 5.0):
        self._pool = AsyncConnectionPool(dsn, min_size=1, max_size=max_size, timeout=timeout_s, open=False,
                                         kwargs={"connect_timeout": 5})

    async def open(self) -> None:
        await self._pool.open()

    async def close(self) -> None:
        await self._pool.close()

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[psycopg.AsyncConnection]:
        try:
            async with self._pool.connection() as conn:
                yield conn
        except (psycopg.OperationalError, PoolTimeout) as exc:
            raise DatabaseUnavailable(f"{type(exc).__name__} : {exc}") from exc

    async def ping(self) -> bool:
        try:
            async with self.connection() as conn:
                await conn.execute("SELECT 1")
            return True
        except DatabaseUnavailable:
            return False


# ------------------------------------------------------------------ dataclasses

@dataclass(frozen=True)
class SourceConfig:
    """Paramètres d'une source issus de config.sources."""
    id: uuid.UUID
    name: str
    silence_threshold_s: int          # délai avant SILENCIEUSE (défaut 600 s)
    expected_min_events_per_h: int | None  # min événements/heure attendus (None = pas de seuil)
    active: bool


@dataclass(frozen=True)
class CoverageStateRow:
    """État de couverture courant d'une source (couverture.coverage_state)."""
    source_id: uuid.UUID
    state: str                        # 'INCONNUE' | 'ACTIVE' | 'SILENCIEUSE' | 'FLUX_INCOMPLET' | 'DESACTIVEE'
    last_received_at: datetime | None
    last_processed_at: datetime | None
    received_count: int
    normalized_count: int
    evaluated_at: datetime | None


# ------------------------------------------------------------------ config.sources

async def list_sources(conn: psycopg.AsyncConnection) -> list[SourceConfig]:
    """Retourne toutes les sources actives et inactives (l'évaluateur décide)."""
    cur = await conn.execute(
        "SELECT id, name, silence_threshold_s, expected_min_events_per_h, active "
        "FROM config.sources ORDER BY name"
    )
    return [
        SourceConfig(id=r[0], name=r[1], silence_threshold_s=r[2],
                     expected_min_events_per_h=r[3], active=r[4])
        for r in await cur.fetchall()
    ]


async def get_source_by_name(conn: psycopg.AsyncConnection, name: str) -> SourceConfig | None:
    cur = await conn.execute(
        "SELECT id, name, silence_threshold_s, expected_min_events_per_h, active "
        "FROM config.sources WHERE name = %s",
        (name,),
    )
    row = await cur.fetchone()
    return SourceConfig(id=row[0], name=row[1], silence_threshold_s=row[2],
                        expected_min_events_per_h=row[3], active=row[4]) if row else None


# ------------------------------------------------------------------ couverture.coverage_state

async def get_coverage_state(conn: psycopg.AsyncConnection, source_id: uuid.UUID) -> CoverageStateRow | None:
    cur = await conn.execute(
        "SELECT source_id, state::text, last_received_at, last_processed_at, "
        "received_count, normalized_count, evaluated_at "
        "FROM couverture.coverage_state WHERE source_id = %s",
        (source_id,),
    )
    row = await cur.fetchone()
    if row is None:
        return None
    return CoverageStateRow(*row)


async def upsert_coverage_state(
    conn: psycopg.AsyncConnection,
    *,
    source_id: uuid.UUID,
    state: str,
    last_received_at: datetime | None = None,
    last_processed_at: datetime | None = None,
    received_count: int = 0,
    normalized_count: int = 0,
    evaluated_at: datetime | None = None,
) -> None:
    """Crée ou met à jour l'état de couverture d'une source."""
    await conn.execute(
        """
        INSERT INTO couverture.coverage_state
            (source_id, state, last_received_at, last_processed_at,
             received_count, normalized_count, evaluated_at)
        VALUES (%s, %s::couverture.coverage_state_enum, %s, %s, %s, %s, %s)
        ON CONFLICT (source_id) DO UPDATE SET
            state             = EXCLUDED.state,
            last_received_at  = COALESCE(EXCLUDED.last_received_at, couverture.coverage_state.last_received_at),
            last_processed_at = COALESCE(EXCLUDED.last_processed_at, couverture.coverage_state.last_processed_at),
            received_count    = EXCLUDED.received_count,
            normalized_count  = EXCLUDED.normalized_count,
            evaluated_at      = EXCLUDED.evaluated_at
        """,
        (source_id, state, last_received_at, last_processed_at,
         received_count, normalized_count, evaluated_at),
    )


async def bump_received(
    conn: psycopg.AsyncConnection,
    *,
    source_id: uuid.UUID,
    received_at: datetime,
) -> None:
    """Incrémente received_count et met à jour last_received_at (ReceptionTracker)."""
    await conn.execute(
        """
        INSERT INTO couverture.coverage_state
            (source_id, state, last_received_at, received_count, normalized_count)
        VALUES (%s, 'INCONNUE'::couverture.coverage_state_enum, %s, 1, 0)
        ON CONFLICT (source_id) DO UPDATE SET
            last_received_at = GREATEST(EXCLUDED.last_received_at, couverture.coverage_state.last_received_at),
            received_count   = couverture.coverage_state.received_count + 1
        """,
        (source_id, received_at),
    )


async def bump_processed(
    conn: psycopg.AsyncConnection,
    *,
    source_id: uuid.UUID,
    processed_at: datetime,
) -> None:
    """Incrémente normalized_count et met à jour last_processed_at (ProcessingTracker)."""
    await conn.execute(
        """
        INSERT INTO couverture.coverage_state
            (source_id, state, last_processed_at, received_count, normalized_count)
        VALUES (%s, 'INCONNUE'::couverture.coverage_state_enum, %s, 0, 1)
        ON CONFLICT (source_id) DO UPDATE SET
            last_processed_at = GREATEST(EXCLUDED.last_processed_at, couverture.coverage_state.last_processed_at),
            normalized_count  = couverture.coverage_state.normalized_count + 1
        """,
        (source_id, processed_at),
    )


# ------------------------------------------------------------------ couverture.coverage_state_history

async def insert_state_history(
    conn: psycopg.AsyncConnection,
    *,
    source_id: uuid.UUID,
    previous_state: str | None,
    new_state: str,
    reason: str,
    changed_at: datetime,
) -> None:
    """Enregistre une transition d'état dans l'historique."""
    await conn.execute(
        "INSERT INTO couverture.coverage_state_history "
        "(source_id, previous_state, new_state, reason, changed_at) "
        "VALUES (%s, %s::couverture.coverage_state_enum, %s::couverture.coverage_state_enum, %s, %s)",
        (source_id, previous_state, new_state, reason, changed_at),
    )


# ------------------------------------------------------------------ couverture.coverage_affected_rules

async def upsert_affected_rules(
    conn: psycopg.AsyncConnection,
    *,
    source_id: uuid.UUID,
    rule_ids: list[str],
    evaluated_at: datetime,
) -> None:
    """Remplace la liste des règles affectées par l'état dégradé d'une source."""
    await conn.execute(
        "DELETE FROM couverture.coverage_affected_rules WHERE source_id = %s",
        (source_id,),
    )
    if rule_ids:
        await conn.executemany(
            "INSERT INTO couverture.coverage_affected_rules (source_id, rule_id, affected_at) "
            "VALUES (%s, %s, %s)",
            [(source_id, rid, evaluated_at) for rid in rule_ids],
        )


__all__ = [
    "Database", "DatabaseUnavailable",
    "SourceConfig", "CoverageStateRow",
    "list_sources", "get_source_by_name",
    "get_coverage_state", "upsert_coverage_state",
    "bump_received", "bump_processed",
    "insert_state_history", "upsert_affected_rules",
]
