"""Routes règles de détection (C20).

GET    /rules          → liste
POST   /rules          → créer (ADMIN)
GET    /rules/{id}     → détail
PUT    /rules/{id}     → modifier (ADMIN)
DELETE /rules/{id}     → désactiver (ADMIN)
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from ..dependencies import get_conn, require_role
from ..models import RuleCreate, RuleResponse, RuleUpdate, UserRole

router = APIRouter(prefix="/rules", tags=["rules"])

_READ  = Depends(require_role(UserRole.ANALYST, UserRole.ADMIN))
_WRITE = Depends(require_role(UserRole.ADMIN))


@router.get("", response_model=list[RuleResponse])
async def list_rules(
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    _user=_READ,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    enabled_only: bool = False,
):
    q = "SELECT * FROM config.detection_rules"
    args: list = []
    if enabled_only:
        q += " WHERE enabled = TRUE"
    q += " ORDER BY name LIMIT %s OFFSET %s"
    args.extend([limit, offset])
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(q, args)
        return await cur.fetchall()


@router.post("", response_model=RuleResponse, status_code=status.HTTP_201_CREATED)
async def create_rule(
    body: RuleCreate,
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    _user=_WRITE,
):
    import json
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """INSERT INTO config.detection_rules
               (name, description, enabled, severity, source_type, logic, threshold, window_id)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING *""",
            (
                body.name, body.description, body.enabled,
                body.severity.value if body.severity else None,
                body.source_type, json.dumps(body.logic),
                body.threshold, body.window_id,
            ),
        )
        return await cur.fetchone()


@router.get("/{rule_id}", response_model=RuleResponse)
async def get_rule(
    rule_id: uuid.UUID,
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    _user=_READ,
):
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("SELECT * FROM config.detection_rules WHERE id = %s", (rule_id,))
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Règle introuvable")
    return row


@router.put("/{rule_id}", response_model=RuleResponse)
async def update_rule(
    rule_id: uuid.UUID,
    body: RuleUpdate,
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    _user=_WRITE,
):
    import json
    updates = {k: v for k, v in body.model_dump(exclude_none=True).items()}
    if not updates:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Aucun champ à modifier")
    # Sérialiser severity et logic
    if "severity" in updates and updates["severity"] is not None:
        updates["severity"] = updates["severity"].value if hasattr(updates["severity"], "value") else updates["severity"]
    if "logic" in updates:
        updates["logic"] = json.dumps(updates["logic"])
    set_clause = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values()) + [rule_id]
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            f"UPDATE config.detection_rules SET {set_clause}, updated_at = NOW() WHERE id = %s RETURNING *",
            values,
        )
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Règle introuvable")
    return row


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def disable_rule(
    rule_id: uuid.UUID,
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    _user=_WRITE,
):
    async with conn.cursor() as cur:
        await cur.execute(
            "UPDATE config.detection_rules SET enabled = FALSE, updated_at = NOW() WHERE id = %s RETURNING id",
            (rule_id,),
        )
        if await cur.fetchone() is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Règle introuvable")
