"""Routes incidents (C20).

GET  /incidents                     → liste paginée
GET  /incidents/{id}                → détail
GET  /incidents/{id}/timeline       → chronologie (relayé à incident-builder)
GET  /incidents/{id}/alerts         → alertes de l'incident
POST /incidents/{id}/status         → changer l'état (C5)
"""
from __future__ import annotations

import uuid
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from ..dependencies import get_conn, require_role
from ..models import (
    AlertResponse, IncidentResponse, IncidentState,
    IncidentStateUpdate, TimelineEntryResponse, UserRole,
)

router = APIRouter(prefix="/incidents", tags=["incidents"])

_READ  = Depends(require_role(UserRole.ANALYST, UserRole.ADMIN))
_WRITE = Depends(require_role(UserRole.ANALYST, UserRole.ADMIN))


@router.get("", response_model=list[IncidentResponse])
async def list_incidents(
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    _user=_READ,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    state: IncidentState | None = None,
):
    q = "SELECT * FROM incidents.incidents"
    args: list = []
    if state:
        q += " WHERE state = %s"
        args.append(state.value)
    q += " ORDER BY opened_at DESC LIMIT %s OFFSET %s"
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
        await cur.execute("SELECT * FROM incidents.incidents WHERE id = %s", (incident_id,))
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident introuvable")
    return row


@router.get("/{incident_id}/timeline", response_model=list[TimelineEntryResponse])
async def get_timeline(
    incident_id: uuid.UUID,
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    _user=_READ,
):
    """Lit la chronologie directement depuis PostgreSQL."""
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT * FROM incidents.timeline WHERE incident_id = %s ORDER BY occurred_at",
            (incident_id,),
        )
        return await cur.fetchall()


@router.get("/{incident_id}/alerts", response_model=list[AlertResponse])
async def get_incident_alerts(
    incident_id: uuid.UUID,
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    _user=_READ,
):
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT * FROM incidents.alerts WHERE incident_id = %s ORDER BY fired_at DESC",
            (incident_id,),
        )
        return await cur.fetchall()


@router.post("/{incident_id}/status", response_model=IncidentResponse)
async def update_status(
    incident_id: uuid.UUID,
    body: IncidentStateUpdate,
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    _user=_WRITE,
):
    async with conn.cursor(row_factory=dict_row) as cur:
        # Changer l'état
        await cur.execute(
            """UPDATE incidents.incidents
               SET state = %s, updated_at = NOW(),
                   closed_at = CASE WHEN %s IN ('CLOS', 'RESOLU', 'FAUX_POSITIF') THEN NOW() ELSE closed_at END
               WHERE id = %s RETURNING *""",
            (body.state.value, body.state.value, incident_id),
        )
        row = await cur.fetchone()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident introuvable")
        # Enregistrer dans la timeline si commentaire
        if body.comment:
            await cur.execute(
                """INSERT INTO incidents.timeline (incident_id, entry_type, occurred_at, detail)
                   VALUES (%s, 'CHANGEMENT_ETAT', NOW(), %s)""",
                (incident_id, __import__("json").dumps({"state": body.state.value, "comment": body.comment})),
            )
    return row
