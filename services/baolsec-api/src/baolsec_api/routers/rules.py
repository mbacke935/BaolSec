"""Routes règles de détection (C20), schéma C4 config.rules.

GET /rules · POST /rules (ADMIN) · GET /rules/{id} · PUT /rules/{id} (ADMIN) ·
DELETE /rules/{id} = désactivation (ADMIN).

La définition versionnée (rule_versions.definition_yaml) n'est pas exposée ici ;
l'activation/désactivation et les métadonnées de config.rules le sont.
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

_READ = Depends(require_role(UserRole.ANALYST, UserRole.ADMIN))
_WRITE = Depends(require_role(UserRole.ADMIN))

_COLS = """id, name, description,
           jsonb_build_object('rule_type', rule_type) AS logic,
           severity, is_enabled AS enabled, current_version AS version,
           created_at, updated_at"""


@router.get("", response_model=list[RuleResponse])
async def list_rules(
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    _user=_READ,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    enabled_only: bool = False,
):
    q = f"SELECT {_COLS} FROM config.rules"
    if enabled_only:
        q += " WHERE is_enabled = TRUE"
    q += " ORDER BY name LIMIT %s OFFSET %s"
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(q, [limit, offset])
        return await cur.fetchall()


@router.post("", response_model=RuleResponse, status_code=status.HTTP_201_CREATED)
async def create_rule(
    body: RuleCreate,
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    _user=_WRITE,
):
    rule_type = str((body.logic or {}).get("rule_type", "simple"))
    async with conn.cursor(row_factory=dict_row) as cur:
        try:
            await cur.execute(
                f"""INSERT INTO config.rules (name, description, rule_type, severity, is_enabled)
                    VALUES (%s, %s, %s, %s, %s) RETURNING {_COLS}""",
                (body.name, body.description, rule_type,
                 body.severity.value if body.severity else "moyenne", body.enabled),
            )
        except Exception as exc:
            if "unique" in str(exc).lower():
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Nom de règle déjà utilisé")
            raise
        return await cur.fetchone()


@router.get("/{rule_id}", response_model=RuleResponse)
async def get_rule(
    rule_id: uuid.UUID,
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    _user=_READ,
):
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(f"SELECT {_COLS} FROM config.rules WHERE id = %s", (rule_id,))
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
    src = body.model_dump(exclude_none=True)
    set_parts: list[str] = []
    values: list = []
    if "enabled" in src:
        set_parts.append("is_enabled = %s"); values.append(src["enabled"])
    if "severity" in src:
        sev = src["severity"]
        set_parts.append("severity = %s"); values.append(getattr(sev, "value", sev))
    if "description" in src:
        set_parts.append("description = %s"); values.append(src["description"])
    if not set_parts:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Aucun champ à modifier")
    values.append(rule_id)
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            f"UPDATE config.rules SET {', '.join(set_parts)}, updated_at = NOW() WHERE id = %s RETURNING {_COLS}",
            values,
        )
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Règle introuvable")
    return row


@router.get("/{rule_id}/versions")
async def rule_versions(
    rule_id: uuid.UUID,
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    _user=_READ,
):
    """Historique des versions d'une règle (C4 config.rule_versions, C5)."""
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """SELECT rule_id, version, checksum, definition_yaml, created_by, created_at
                 FROM config.rule_versions WHERE rule_id = %s ORDER BY version DESC""",
            (rule_id,),
        )
        return await cur.fetchall()


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def disable_rule(
    rule_id: uuid.UUID,
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    _user=_WRITE,
):
    async with conn.cursor() as cur:
        await cur.execute(
            "UPDATE config.rules SET is_enabled = FALSE, updated_at = NOW() WHERE id = %s RETURNING id",
            (rule_id,),
        )
        if await cur.fetchone() is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Règle introuvable")
