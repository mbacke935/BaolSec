"""Accès PostgreSQL du service Incidents (compte svc_incidents).

`Database` fournit des connexions d'un pool ; chaque `async with db.connection()` est une transaction,
validée à la sortie du bloc et annulée si une exception en sort. Les requêtes sont dans alerts.py.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import psycopg
from psycopg_pool import AsyncConnectionPool, PoolTimeout


class DatabaseUnavailable(Exception):
    """PostgreSQL injoignable, trop lent ou transaction abandonnée par le serveur : l'opération peut être refaite."""


class UnknownRule(Exception):
    """L'alerte vise une règle absente de config.rules (clé étrangère)."""


class Database:
    def __init__(self, dsn: str, *, max_size: int = 5, timeout_s: float = 5.0):
        self._pool = AsyncConnectionPool(dsn, min_size=1, max_size=max_size, timeout=timeout_s, open=False,
                                         kwargs={"connect_timeout": 5})

    async def open(self) -> None:
        """Ouvre le pool sans attendre : une base absente au démarrage ne bloque pas le service."""
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


__all__ = ["Database", "DatabaseUnavailable", "UnknownRule"]
