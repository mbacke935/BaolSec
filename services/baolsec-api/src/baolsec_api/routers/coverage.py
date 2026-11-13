"""Routes état de couverture (C20).

GET  /coverage           → état courant par source
GET  /coverage/{id}      → détail d'une source (état + règles affectées)
GET  /coverage/history   → historique des changements
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from ..dependencies import get_conn, require_role
from ..models import CoverageStateResponse, UserRole

router = APIRouter(prefix="/coverage", tags=["coverage"])

_READ = Depends(require_role(UserRole.ANALYST, UserRole.ADMIN))


@router.get("", response_model=list[CoverageStateResponse])
async def list_coverage(
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    _user=_READ,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT * FROM couverture.coverage_state ORDER BY last_seen_at DESC NULLS LAST LIMIT %s OFFSET %s",
            (limit, offset),
        )
        return await cur.fetchall()


@router.get("/history")
async def coverage_history(
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    _user=_READ,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    source_id: uuid.UUID | None = None,
):
    conds = []
    args: list = []
    if source_id:
        conds.append("source_id = %s"); args.append(source_id)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    q = f"SELECT * FROM couverture.coverage_state_history {where} ORDER BY changed_at DESC LIMIT %s OFFSET %s"
    args.extend([limit, offset])
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(q, args)
        return await cur.fetchall()


@router.get("/{source_id}", response_model=CoverageStateResponse)
async def get_coverage(
    source_id: uuid.UUID,
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    _user=_READ,
):
    from fastapi import HTTPException, status
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT * FROM couverture.coverage_state WHERE source_id = %s",
            (source_id,),
        )
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Couverture introuvable pour cette source")
    return row
