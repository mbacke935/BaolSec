"""Routes d'administration (C20/C5) : paramètres, rôles, journal d'audit, file de rejet.

Réservées à l'Administrateur (C5/C21). Les paramètres sont dans config.settings,
l'audit dans acces.audit_log (ajout seul). La file de rejet (DLQ) est lue directement
dans le flux NATS JetStream, en lecture seule (broker.py).
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from .. import broker
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


def _validate_setting(key: str, value):
    """Contrôle des paramètres de corrélation de C3 3.8 (lus par le service Incidents)."""
    if key in ("correlation.window_minutes", "correlation.max_incident_hours"):
        if isinstance(value, bool) or not isinstance(value, int):
            raise HTTPException(status_code=422, detail="Valeur entière attendue")
        bounds = (1, 1440) if key.endswith("window_minutes") else (1, 720)
        if not bounds[0] <= value <= bounds[1]:
            raise HTTPException(status_code=422, detail=f"Valeur hors bornes ({bounds[0]} à {bounds[1]})")
    elif key == "correlation.generic_values":
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise HTTPException(status_code=422, detail="Liste de chaînes attendue")
    elif key == "correlation.activity_chains":
        if not isinstance(value, list) or not all(
            isinstance(c, list) and len(c) == 2 and all(isinstance(x, str) for x in c) for c in value
        ):
            raise HTTPException(status_code=422, detail="Liste de couples [activité, activité] attendue")
    if len(json.dumps(value)) > 10_000:
        raise HTTPException(status_code=422, detail="Valeur trop volumineuse")


@router.patch("/settings/{key}")
@router.put("/settings/{key}")
async def set_setting(
    key: str,
    body: dict,
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    current: Annotated[TokenPayload, Depends(get_current_user)],
    _admin=_ADMIN,
):
    value = body.get("value", body)
    _validate_setting(key, value)
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


# ── Rôles (C5 GET /roles) ─────────────────────────────────────────────────────

ROLE_PERMISSIONS = {
    "Administrateur": ["Gérer les utilisateurs, les sources, les règles et les paramètres",
                       "Consulter les sources et les règles", "Consulter le journal d'audit",
                       "Consulter la file de rejet", "Consulter événements, alertes et incidents (lecture)",
                       "Consulter la couverture des sources"],
    "Analyste": ["Consulter les sources et les règles (lecture)", "Rechercher les événements",
                 "Consulter et traiter les alertes et les incidents (statut, commentaire, assignation)",
                 "Consulter la couverture des sources"],
}


@router.get("/roles")
async def list_roles(conn: Annotated[AsyncConnection, Depends(get_conn)], _user=_ADMIN):
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """SELECT r.id, r.name, r.description, COUNT(u.id) FILTER (WHERE u.is_active) AS active_users
                 FROM acces.roles r LEFT JOIN acces.users u ON u.role_id = r.id
                GROUP BY r.id ORDER BY r.name""")
        rows = await cur.fetchall()
    return [{**r, "api_role": {"Administrateur": "ADMIN", "Analyste": "ANALYST"}.get(r["name"]),
             "permissions": ROLE_PERMISSIONS.get(r["name"], [])} for r in rows]


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
    domain: str | None = Query(None, description="connexion, compte, source, regle, incident, parametre"),
    actor: str | None = Query(None, max_length=200, description="Partie du nom ou de l'e-mail de l'acteur"),
):
    """Journal d'audit paginé avec filtres : domaine, acteur, résultat, action, plage de dates."""
    conds, args = [], []
    domains = {
        "connexion": "(action = 'auth.login' OR position('/auth/' in action) > 0)",
        "compte": "target_type = 'users'",
        "source": "target_type = 'sources'",
        "regle": "target_type = 'rules'",
        "incident": "target_type IN ('incidents', 'alerts')",
        "parametre": "target_type = 'settings'",
    }
    if domain:
        if domain not in domains:
            raise HTTPException(status_code=422, detail=f"Domaine inconnu : {domain}")
        conds.append(domains[domain])
    if actor:
        conds.append("actor_username ILIKE %s"); args.append(f"%{actor}%")
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


# ── File de rejet (DLQ, NATS JetStream) — lecture seule ──────────────────────

@router.get("/dlq")
async def list_dlq(
    _user=_ADMIN,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    service: str | None = None,
    reason: str | None = None,
):
    """Messages rejetés ou abandonnés, du plus récent au plus ancien (C5, C11)."""
    try:
        return await broker.dlq_list(limit=limit, offset=offset, service=service, reason=reason)
    except broker.BrokerUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail=f"File de rejet indisponible : {exc}") from exc


@router.get("/dlq/{seq}")
async def get_dlq(seq: int, _user=_ADMIN):
    """Un message rejeté avec son contenu d'origine (C5)."""
    try:
        entry = await broker.dlq_get(seq)
    except broker.BrokerUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail=f"File de rejet indisponible : {exc}") from exc
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message introuvable dans la file de rejet")
    return entry
