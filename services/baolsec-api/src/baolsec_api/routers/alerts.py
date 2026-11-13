"""Routes alertes (C20).

GET  /alerts           → liste paginée (toutes alertes ou filtre par règle/source)
GET  /alerts/{id}      → détail
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from ..dependencies import get_conn, require_role
from ..models import AlertResponse, UserRole

router = APIRouter(prefix="/alerts", tags=["alerts"])

_READ = Depends(require_role(UserRole.ANALYST, UserRole.ADMIN))


@router.get("", response_model=list[AlertResponse])
async def list_alerts(
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    _user=_READ,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    rule_id: uuid.UUID | None = None,
    source_id: uuid.UUID | None = None,
):
    conds = []
    args: list = []
    if rule_id:
        conds.append("rule_id = %s"); args.append(rule_id)
    if source_id:
        conds.append("source_id = %s"); args.append(source_id)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    q = f"SELECT * FROM incidents.alerts {where} ORDER BY fired_at DESC LIMIT %s OFFSET %s"
    args.extend([limit, offset])
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(q, args)
        return await cur.fetchall()


@router.get("/{alert_id}", response_model=AlertResponse)
async def get_alert(
    alert_id: uuid.UUID,
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    _user=_READ,
):
    from fastapi import HTTPException, status
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("SELECT * FROM incidents.alerts WHERE id = %s", (alert_id,))
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alerte introuvable")
    return row
