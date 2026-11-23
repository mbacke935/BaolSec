"""Routes d'administration (C20/C5) : paramètres, journal d'audit, file de rejet.

Réservées à l'Administrateur (C5/C21). Les paramètres sont dans config.settings,
l'audit dans acces.audit_log. La file de rejet (DLQ) vit dans NATS JetStream : sa
consultation via l'API nécessite le client broker, non câblé dans cette brique.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from ..dependencies import get_conn, get_current_user, paginate, require_role
from ..models import Page, TokenPayload, UserRole

router = APIRouter(tags=["administration"])

_ADMIN = Depends(require_role(UserRole.ADMIN))


# ── Paramètres (config.settings) ──────────────────────────────────────────────

@router.get("/settings")
async def list_settings(conn: Annotated[AsyncConnection, Depends(get_conn)], _user=_ADMIN):
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("SELECT key, value, updated_at FROM config.settings ORDER BY key")
        return await cur.fetchall()


@router.put("/settings/{key}")
async def set_setting(
    key: str,
    body: dict,
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    current: Annotated[TokenPayload, Depends(get_current_user)],
    _admin=_ADMIN,
):
    value = body.get("value", body)
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """INSERT INTO config.settings (key, value, updated_by, updated_at)
               VALUES (%s, %s, %s, NOW())
               ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value,
                   updated_by = EXCLUDED.updated_by, updated_at = NOW()
               RETURNING key, value, updated_at""",
            (key, json.dumps(value), current.sub),
        )
        return await cur.fetchone()


# ── Journal d'audit (acces.audit_log) ─────────────────────────────────────────

_AUDIT_COLS = ("id, occurred_at, actor_id, actor_username, action, "
               "target_type, target_id, outcome, details, client_ip")
_AUDIT_FROM = "FROM acces.audit_log"
_AUDIT_COUNT = "SELECT COUNT(*) AS count FROM acces.audit_log"


@router.get("/audit")
async def list_audit(
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    _user=_ADMIN,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    # Filtres enrichis
    outcome: str | None = None,
    action: str | None = None,
    actor_id: uuid.UUID | None = None,
    occurred_after: datetime | None = None,
    occurred_before: datetime | None = None,
):
    """Journal d'audit paginé avec filtres : outcome, action, actor_id, plage de dates."""
    conds, args = [], []
    if outcome:
        conds.append("outcome = %s"); args.append(outcome)
    if action:
        conds.append("action ILIKE %s"); args.append(f"%{action}%")
    if actor_id:
        conds.append("actor_id = %s"); args.append(actor_id)
    if occurred_after:
        conds.append("occurred_at >= %s"); args.append(occurred_after)
    if occurred_before:
        conds.append("occurred_at <= %s"); args.append(occurred_before)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""

    select_sql = f"SELECT {_AUDIT_COLS} {_AUDIT_FROM} {where} ORDER BY occurred_at DESC"
    count_sql = f"{_AUDIT_COUNT} {where}"
    return await paginate(conn, select_sql, count_sql, args, limit, offset)


# ── File de rejet (DLQ, NATS JetStream) ───────────────────────────────────────

@router.get("/dlq")
async def list_dlq(_user=_ADMIN):
    return {
        "items": [],
        "note": ("La file de rejet (DLQ) est un flux NATS JetStream ; sa consultation "
                 "et sa reprise via l'API nécessitent le client broker, à câbler dans "
                 "cette brique (C5 §file de rejet)."),
    }
