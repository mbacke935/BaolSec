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
    AlertResponse, IncidentResponse, IncidentState, Severity,
    TimelineEntryResponse, TokenPayload, UserRole,
)

router = APIRouter(prefix="/incidents", tags=["incidents"])

_READ = Depends(require_role(UserRole.ANALYST, UserRole.ADMIN))
_ANALYST = Depends(require_role(UserRole.ANALYST))  # commandes réservées à l'Analyste (C5)

_INC = """i.id, i.title, NULL::text AS description, i.status AS state, i.severity,
          i.opened_at, i.closed_at, i.assigned_to, u.username AS assigned_to_name,
          (SELECT COUNT(*) FROM incidents.incident_alerts ia WHERE ia.incident_id = i.id)::int AS alert_count,
          i.correlation_context AS metadata,
          i.opened_at AS created_at, i.last_activity_at AS updated_at
     FROM incidents.incidents i
     LEFT JOIN acces.users u ON u.id = i.assigned_to"""


def _issuer(current: TokenPayload) -> dict[str, str]:
    return {"user_id": current.sub, "username": current.email or current.sub}


# ── Lectures ──────────────────────────────────────────────────────────────────

@router.get("", response_model=list[IncidentResponse])
async def list_incidents(
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    _user=_READ,
    state: IncidentState | None = None,
    severity: Severity | None = None,
    assigned_to_me: bool = False,
    active_only: bool = False,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current: Annotated[TokenPayload, Depends(get_current_user)] = None,
):
    conds, args = [], []
    if state:
        conds.append("i.status = %s"); args.append(state.value)
    if active_only:
        conds.append("i.status <> 'clos'")
    if severity:
        conds.append("i.severity = %s"); args.append(severity.value)
    if assigned_to_me and current is not None:
        conds.append("i.assigned_to = %s"); args.append(current.sub)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    q = f"SELECT {_INC} {where} ORDER BY i.last_activity_at DESC LIMIT %s OFFSET %s"
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
        await cur.execute(f"SELECT {_INC} WHERE i.id = %s", (incident_id,))
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
            """SELECT t.id, t.incident_id, t.entry_type, t.occurred_at, t.summary,
                      COALESCE(t.justification, '{}'::jsonb) AS detail,
                      t.alert_id, t.event_id, t.actor_id AS user_id, u.username AS user_name
                 FROM incidents.incident_timeline t
                 LEFT JOIN acces.users u ON u.id = t.actor_id
                WHERE t.incident_id = %s ORDER BY t.occurred_at, t.id""",
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
                      ia.incident_id, r.name AS title, ia.criteria AS detail,
                      a.triggered_at AS fired_at, substring(rv.definition_yaml from '(?n)^id:[[:space:]]*([A-Z]{2,6}-[0-9]{3})') AS rule_code,
                      u.username AS assigned_to_name
                 FROM incidents.incident_alerts ia
                 JOIN incidents.alert_state a ON a.alert_id = ia.alert_id
                 JOIN config.rules r ON r.id = a.rule_id
                 LEFT JOIN config.rule_versions rv ON rv.rule_id = r.id AND rv.version = r.current_version
                 LEFT JOIN acces.users u ON u.id = a.assigned_to
                WHERE ia.incident_id = %s ORDER BY a.triggered_at DESC""",
            (incident_id,),
        )
        return await cur.fetchall()


@router.get("/{incident_id}/comments")
async def incident_comments(
    incident_id: uuid.UUID,
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    _user=_READ,
):
    """Commentaires des analystes (C5 : « consulter un incident : … commentaires »)."""
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """SELECT c.id, c.incident_id, c.author_id, u.username AS author_name, c.body, c.created_at
                 FROM incidents.incident_comments c LEFT JOIN acces.users u ON u.id = c.author_id
                WHERE c.incident_id = %s ORDER BY c.created_at""",
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
    comment = (body.get("comment") or "").strip()
    # Charges utiles exactes du contrat incident_command/v1 (additionalProperties: false) :
    # clore → {reason?}, changer_statut → {status}. Un commentaire saisi avec un changement de
    # statut autre que la clôture devient une commande « commenter » distincte, envoyée après.
    if new_state == "clos":
        payload = {"reason": comment[:2000]} if comment else {}
        return await _command("clore", incident_id, current, payload, idempotency_key)
    result = await _command("changer_statut", incident_id, current, {"status": new_state}, idempotency_key)
    if comment and result.get("result") == "acceptee":
        comment_key = str(uuid.uuid5(uuid.UUID(idempotency_key), "comment")) if commandclient.is_uuid(idempotency_key) else None
        await _command("commenter", incident_id, current, {"body": comment[:10000]}, comment_key)
    return result



@router.post("/{incident_id}/assign")
async def assign_incident(
    incident_id: uuid.UUID,
    body: dict,
    current: Annotated[TokenPayload, Depends(get_current_user)],
    _analyst=_ANALYST,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
):
    return await _command("assigner", incident_id, current,
                          {"assignee_id": commandclient.assignee_from(body)}, idempotency_key)


@router.post("/{incident_id}/comments")
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


@router.post("/{incident_id}/close")
async def close_incident(
    incident_id: uuid.UUID,
    current: Annotated[TokenPayload, Depends(get_current_user)],
    body: dict | None = None,
    _analyst=_ANALYST,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
):
    reason = ((body or {}).get("reason") or (body or {}).get("comment") or "").strip()
    return await _command("clore", incident_id, current, {"reason": reason[:2000]} if reason else {},
                          idempotency_key)


@router.post("/{incident_id}/reopen")
async def reopen_incident(
    incident_id: uuid.UUID,
    current: Annotated[TokenPayload, Depends(get_current_user)],
    body: dict | None = None,
    _analyst=_ANALYST,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
):
    reason = ((body or {}).get("reason") or (body or {}).get("comment") or "").strip()
    return await _command("rouvrir", incident_id, current, {"reason": reason[:2000]} if reason else {},
                          idempotency_key)
