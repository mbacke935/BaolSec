"""Dépendances FastAPI partagées (C20).

Fournit :
  - get_conn()   : connexion psycopg depuis le pool
  - get_current_user() : utilisateur authentifié via JWT (C21)
  - require_role() : vérification du rôle
"""
from __future__ import annotations

from typing import Annotated, AsyncGenerator

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from .auth import decode_token
from .database import get_pool
from .models import TokenPayload, UserRole

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_conn() -> AsyncGenerator:
    """Fournit une connexion async psycopg depuis le pool global."""
    pool = get_pool()
    async with pool.connection() as conn:
        yield conn


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
) -> TokenPayload:
    """Vérifie le JWT et retourne le payload."""
    payload = decode_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide ou expiré",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


def require_role(*roles: UserRole):
    """Renvoie un Depends qui vérifie que l'utilisateur a l'un des rôles donnés."""

    async def _check(current: Annotated[TokenPayload, Depends(get_current_user)]) -> TokenPayload:
        if current.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Rôle requis : {', '.join(r.value for r in roles)}",
            )
        return current

    return _check


async def paginate(
    conn,
    select_sql: str,
    count_sql: str,
    args: list,
    limit: int,
    offset: int,
) -> dict:
    """Exécute une requête paginée et retourne {items, total, limit, offset}."""
    async with conn.cursor() as cur:
        await cur.execute(count_sql, args)
        row = await cur.fetchone()
        total = row[0] if row else 0

        await cur.execute(f"{select_sql} LIMIT %s OFFSET %s", args + [limit, offset])
        rows = await cur.fetchall()
        cols = [d.name for d in cur.description]
        items = [dict(zip(cols, r)) for r in rows]

    return {"items": items, "total": total, "limit": limit, "offset": offset}
