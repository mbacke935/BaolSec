"""Routes état de couverture (C20), schéma C4 couverture.*.

GET /coverage · GET /coverage/history · GET /coverage/{source_id}.
L'état courant vient de couverture.coverage_state ; les compteurs sont agrégés
depuis couverture.coverage_stats ; le nom de la source vient de config.sources.
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from ..dependencies import get_conn, require_role
from ..models import CoverageStateResponse, UserRole

router = APIRouter(prefix="/coverage", tags=["coverage"])

_READ = Depends(require_role(UserRole.ANALYST, UserRole.ADMIN))

_SELECT = """
SELECT cs.source_id, s.name AS source_name, cs.state,
       cs.last_received_at, cs.last_normalized_at AS last_processed_at,
       COALESCE(st.received, 0) AS received_count,
       COALESCE(st.normalized, 0) AS normalized_count,
       cs.last_evaluated_at AS evaluated_at
  FROM couverture.coverage_state cs
  JOIN config.sources s ON s.id = cs.source_id
  LEFT JOIN (SELECT source_id, SUM(received_count) AS received, SUM(normalized_count) AS normalized
               FROM couverture.coverage_stats GROUP BY source_id) st ON st.source_id = cs.source_id
"""


@router.get("", response_model=list[CoverageStateResponse])
async def list_coverage(
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    _user=_READ,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(_SELECT + " ORDER BY s.name LIMIT %s OFFSET %s", (limit, offset))
        return await cur.fetchall()


@router.get("/history")
async def coverage_history(
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    _user=_READ,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    source_id: uuid.UUID | None = None,
):
    conds, args = [], []
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
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(_SELECT + " WHERE cs.source_id = %s", (source_id,))
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Couverture introuvable pour cette source")
    return row
