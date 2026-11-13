"""Routes de gestion des sources (C20).

GET    /sources          → liste paginée (ANALYST, ADMIN)
POST   /sources          → créer (ADMIN)
GET    /sources/{id}     → détail (ANALYST, ADMIN)
PUT    /sources/{id}     → modifier (ADMIN)
DELETE /sources/{id}     → désactiver (ADMIN)
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from ..dependencies import get_conn, require_role
from ..models import SourceCreate, SourceResponse, SourceUpdate, UserRole

router = APIRouter(prefix="/sources", tags=["sources"])

_READ  = Depends(require_role(UserRole.ANALYST, UserRole.ADMIN))
_WRITE = Depends(require_role(UserRole.ADMIN))


@router.get("", response_model=list[SourceResponse])
async def list_sources(
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    _user=_READ,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    active_only: bool = False,
):
    q = "SELECT * FROM config.sources"
    args: list = []
    if active_only:
        q += " WHERE active = TRUE"
    q += " ORDER BY name LIMIT %s OFFSET %s"
    args.extend([limit, offset])
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(q, args)
        return await cur.fetchall()


@router.post("", response_model=SourceResponse, status_code=status.HTTP_201_CREATED)
async def create_source(
    body: SourceCreate,
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    _user=_WRITE,
):
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """INSERT INTO config.sources (name, description, type, active, silence_threshold_s, config)
               VALUES (%s, %s, %s, %s, %s, %s)
               RETURNING *""",
            (body.name, body.description, body.type, body.active, body.silence_threshold_s,
             __import__("json").dumps(body.config)),
        )
        return await cur.fetchone()


@router.get("/{source_id}", response_model=SourceResponse)
async def get_source(
    source_id: uuid.UUID,
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    _user=_READ,
):
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("SELECT * FROM config.sources WHERE id = %s", (source_id,))
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source introuvable")
    return row


@router.put("/{source_id}", response_model=SourceResponse)
async def update_source(
    source_id: uuid.UUID,
    body: SourceUpdate,
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    _user=_WRITE,
):
    updates = {k: v for k, v in body.model_dump(exclude_none=True).items()}
    if not updates:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Aucun champ à modifier")
    if "config" in updates:
        updates["config"] = __import__("json").dumps(updates["config"])
    set_clause = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values()) + [source_id]
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            f"UPDATE config.sources SET {set_clause}, updated_at = NOW() WHERE id = %s RETURNING *",
            values,
        )
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source introuvable")
    return row


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def disable_source(
    source_id: uuid.UUID,
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    _user=_WRITE,
):
    async with conn.cursor() as cur:
        await cur.execute(
            "UPDATE config.sources SET active = FALSE, updated_at = NOW() WHERE id = %s RETURNING id",
            (source_id,),
        )
        if await cur.fetchone() is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source introuvable")
