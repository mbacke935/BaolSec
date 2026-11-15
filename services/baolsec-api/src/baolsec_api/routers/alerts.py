"""Routes alertes (C20), conforme à C4/C5.

Lecture : état de triage dans incidents.alert_state (le document d'alerte immuable
reste dans OpenSearch, interrogeable via /search/alerts).
Écriture : commandes statut_alerte / assigner_alerte transmises au service
Incidents (C5 §6), réservées à l'Analyste.

GET  /alerts · GET /alerts/{id}
POST /alerts/{id}/status  (Analyste) · POST /alerts/{id}/assign (Analyste)
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from .. import commandclient
from ..dependencies import get_conn, get_current_user, require_role
from ..models import AlertResponse, AlertStatus, TokenPayload, UserRole

router = APIRouter(prefix="/alerts", tags=["alerts"])

_READ = Depends(require_role(UserRole.ANALYST, UserRole.ADMIN))
_ANALYST = Depends(require_role(UserRole.ANALYST))  # commandes réservées à l'Analyste (C5)

_COLS = """a.alert_id AS id, a.rule_id, a.severity, a.status, a.assigned_to,
           ia.incident_id, r.name AS title, '{}'::jsonb AS detail,
           a.triggered_at AS fired_at
      FROM incidents.alert_state a
      JOIN config.rules r ON r.id = a.rule_id
      LEFT JOIN incidents.incident_alerts ia ON ia.alert_id = a.alert_id"""


def _issuer(current: TokenPayload) -> dict[str, str]:
    return {"user_id": current.sub, "username": current.email or current.sub}


@router.get("", response_model=list[AlertResponse])
async def list_alerts(
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    _user=_READ,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    rule_id: uuid.UUID | None = None,
    alert_status: AlertStatus | None = None,
):
    conds, args = [], []
    if rule_id:
        conds.append("a.rule_id = %s"); args.append(rule_id)
    if alert_status:
        conds.append("a.status = %s"); args.append(alert_status.value)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    q = f"SELECT {_COLS} {where} ORDER BY a.triggered_at DESC LIMIT %s OFFSET %s"
    args.extend([limit, offset])
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(q, args)
        return await cur.fetchall()


@router.get("/{alert_id}", response_model=AlertResponse)
async def get_alert(
    alert_id: str,
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    _user=_READ,
):
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(f"SELECT {_COLS} WHERE a.alert_id = %s", (alert_id,))
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alerte introuvable")
    return row


@router.post("/{alert_id}/status")
async def change_alert_status(
    alert_id: str,
    body: dict,
    current: Annotated[TokenPayload, Depends(get_current_user)],
    _analyst=_ANALYST,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
):
    new_status = body.get("status")
    if new_status not in {s.value for s in AlertStatus}:
        raise HTTPException(status_code=422, detail="Statut d'alerte invalide")
    try:
        return await commandclient.send_command(
            command_type="statut_alerte",
            target={"alert_id": alert_id},
            issued_by=_issuer(current),
            payload={"status": new_status},
            idempotency_key=idempotency_key,
        )
    except commandclient.CommandError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.post("/{alert_id}/assign")
async def assign_alert(
    alert_id: str,
    body: dict,
    current: Annotated[TokenPayload, Depends(get_current_user)],
    _analyst=_ANALYST,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
):
    try:
        return await commandclient.send_command(
            command_type="assigner_alerte",
            target={"alert_id": alert_id},
            issued_by=_issuer(current),
            payload={"assigned_to": body.get("assigned_to")},
            idempotency_key=idempotency_key,
        )
    except commandclient.CommandError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)
