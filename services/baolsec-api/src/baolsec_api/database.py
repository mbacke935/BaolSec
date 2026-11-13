"""Pool de connexions PostgreSQL pour l'API (C20)."""
from __future__ import annotations

from psycopg_pool import AsyncConnectionPool

_pool: AsyncConnectionPool | None = None


def get_pool() -> AsyncConnectionPool:
    if _pool is None:
        raise RuntimeError("Pool non initialisé — appeler init_pool() au démarrage")
    return _pool


async def init_pool(dsn: str, max_size: int = 10, timeout_s: float = 5.0) -> None:
    global _pool
    _pool = AsyncConnectionPool(
        conninfo=dsn,
        max_size=max_size,
        open=False,
        kwargs={"autocommit": True, "row_factory": None},
    )
    await _pool.open(wait=True, timeout=timeout_s * 5)


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
