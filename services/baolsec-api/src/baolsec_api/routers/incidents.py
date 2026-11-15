"""Routes incidents (C20), conforme à C4/C5.

Lecture : incidents.incidents, incidents.incident_timeline, incidents.incident_alerts
(+ incidents.alert_state). Écriture : commandes changer_statut / assigner / commenter
transmises au service Incidents (C5 §6), réservées à l'Analyste. L'API n'écrit
jamais directement dans le schéma incidents.

GET  /incidents · GET /incidents/{id} · GET /incidents/{id}/timeline · GET /incidents/{id}/alerts
POST /incidents/{id}/status (Analyste) · /assign (Analyste) · /comment (Analyste)
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from .. import commandclient
from ..dependencies import get_conn, get_current_user, require_role
from ..models import (
    AlertResponse, IncidentResponse, IncidentState,
    TimelineEntryResponse, TokenPayload, UserRole,
)

router = APIRouter(prefix="/incidents", tags=["incidents"])

_READ = Depends(require_role(UserRole.ANALYST, UserRole.ADMIN))
_ANALYST = Depends(require_role(UserRole.ANALYST))  # commandes réservées à l'Analyste (C5)

_INC = """id, title, NULL::text AS description, status AS state, severity,
          opened_at, closed_at, assigned_to, correlation_context AS metadata,
          opened_at AS created_at, last_activity_at AS updated_at
     FROM incidents.incidents"""


def _issuer(current: TokenPayload) -> dict[str, str]:
    return {"user_id": current.sub, "username": current.email or current.sub}


# ── Lectures ──────────────────────────────────────────────────────────────────

@router.get("", response_model=list[IncidentResponse])
async def list_incidents(
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    _user=_READ,
    state: IncidentState | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    conds, args = [], []
    if state:
        conds.append("status = %s"); args.append(state.value)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    q = f"SELECT {_INC} {where} ORDER BY last_activity_at DESC LIMIT %s OFFSET %s"
    args.extend([limit, offset])
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(q, args)
        return await cur.fetchall()


@router.get("/{incident_id}", response_model=IncidentResponse)
async def get_incident(
    incident_id: uuid.UUID,
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    _user=_READ,
):
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(f"SELECT {_INC} WHERE id = %s", (incident_id,))
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident introuvable")
    return row


@router.get("/{incident_id}/timeline", response_model=list[TimelineEntryResponse])
async def incident_timeline(
    incident_id: uuid.UUID,
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    _user=_READ,
):
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """SELECT id, incident_id, entry_type, occurred_at, summary,
                      COALESCE(justification, '{}'::jsonb) AS detail,
                      alert_id, event_id, actor_id AS user_id
                 FROM incidents.incident_timeline
                WHERE incident_id = %s ORDER BY occurred_at""",
            (incident_id,),
        )
        return await cur.fetchall()


@router.get("/{incident_id}/alerts", response_model=list[AlertResponse])
async def incident_alerts(
    incident_id: uuid.UUID,
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    _user=_READ,
):
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """SELECT a.alert_id AS id, a.rule_id, a.severity, a.status, a.assigned_to,
                      ia.incident_id, r.name AS title, '{}'::jsonb AS detail,
                      a.triggered_at AS fired_at
                 FROM incidents.incident_alerts ia
                 JOIN incidents.alert_state a ON a.alert_id = ia.alert_id
                 JOIN config.rules r ON r.id = a.rule_id
                WHERE ia.incident_id = %s ORDER BY a.triggered_at DESC""",
            (incident_id,),
        )
        return await cur.fetchall()


# ── Commandes (transmises à incident-builder, Analyste seul) ──────────────────

async def _command(command_type: str, incident_id: uuid.UUID, current: TokenPayload,
                   payload: dict, idempotency_key: str | None):
    try:
        return await commandclient.send_command(
            command_type=command_type,
            target={"incident_id": str(incident_id)},
            issued_by=_issuer(current),
            payload=payload,
            idempotency_key=idempotency_key,
        )
    except commandclient.CommandError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.post("/{incident_id}/status")
async def change_status(
    incident_id: uuid.UUID,
    body: dict,
    current: Annotated[TokenPayload, Depends(get_current_user)],
    _analyst=_ANALYST,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
):
    new_state = body.get("state") or body.get("status")
    if new_state not in {s.value for s in IncidentState}:
        raise HTTPException(status_code=422, detail="État d'incident invalide")
    # clore / rouvrir sont des commandes spécifiques ; sinon changer_statut (C5 §6).
    command_type = "clore" if new_state == "clos" else "changer_statut"
    payload = {"status": new_state}
    if body.get("comment"):
        payload["comment"] = body["comment"]
    return await _command(command_type, incident_id, current, payload, idempotency_key)


@router.post("/{incident_id}/assign")
async def assign_incident(
    incident_id: uuid.UUID,
    body: dict,
    current: Annotated[TokenPayload, Depends(get_current_user)],
    _analyst=_ANALYST,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
):
    return await _command("assigner", incident_id, current,
                          {"assigned_to": body.get("assigned_to")}, idempotency_key)


@router.post("/{incident_id}/comment")
async def comment_incident(
    incident_id: uuid.UUID,
    body: dict,
    current: Annotated[TokenPayload, Depends(get_current_user)],
    _analyst=_ANALYST,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
):
    text = (body.get("body") or body.get("comment") or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="Commentaire vide")
    return await _command("commenter", incident_id, current, {"body": text}, idempotency_key)
