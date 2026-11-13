"""Requêtes SQL sur incidents.incidents, incidents.incident_alerts et incidents.incident_timeline (C16).

Même principe que alerts.py : chaque fonction reçoit la connexion (transaction) de l'appelant.
Le verrou de ligne (FOR UPDATE) sur l'incident garantit la sérialisation des rattachements concurrents.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

import psycopg
from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb

from ..correlation import CandidateIncident, IncidentContext


class _UNSET:
    """Sentinel pour distinguer « non passé » de None (assigned_to = None veut dire désassigner)."""


# ------------------------------------------------------------------ dataclasses

@dataclass(frozen=True)
class IncidentRow:
    id: uuid.UUID
    title: str
    status: str
    severity: str
    correlation_context: dict
    opened_at: datetime
    last_activity_at: datetime
    closed_at: datetime | None
    assigned_to: uuid.UUID | None


INC_COLUMNS = (
    "id, title, status::text, severity::text, correlation_context, "
    "opened_at, last_activity_at, closed_at, assigned_to"
)


@dataclass(frozen=True)
class AttachmentRow:
    incident_id: uuid.UUID
    alert_id: str
    attached_at: datetime
    criteria: dict


@dataclass(frozen=True)
class TimelineEntry:
    id: int
    incident_id: uuid.UUID
    occurred_at: datetime
    recorded_at: datetime
    entry_type: str
    alert_id: str | None
    event_id: str | None
    summary: str
    justification: dict | None
    actor_id: uuid.UUID | None


# ------------------------------------------------------------------ incidents : candidats

async def find_candidates(
    conn: psycopg.AsyncConnection,
    since: datetime,
    max_opened_at: datetime,
) -> list[CandidateIncident]:
    """Incidents ouverts ou en cours dont la dernière activité est récente (fenêtre configurable).

    Le résultat n'est PAS verrouillé : l'appelant verrouille l'incident choisi avec lock_incident.
    """
    cur = await conn.execute(
        f"SELECT {INC_COLUMNS} FROM incidents.incidents "
        "WHERE status IN ('ouvert', 'en_cours') "
        "AND last_activity_at >= %s "
        "AND opened_at >= %s "
        "ORDER BY last_activity_at DESC",
        (since, max_opened_at),
    )
    rows = await cur.fetchall()
    return [
        CandidateIncident(
            incident_id=r[0],
            context=IncidentContext.from_dict(r[4]),
            last_activity_at=r[6],
            opened_at=r[5],
            status=r[2],
            severity=r[3],
        )
        for r in rows
    ]


# ------------------------------------------------------------------ incidents : verrou

async def lock_incident(conn: psycopg.AsyncConnection, incident_id: uuid.UUID) -> IncidentRow | None:
    """Verrouille l'incident pour mise à jour (rattachement ou commande)."""
    cur = await conn.execute(
        f"SELECT {INC_COLUMNS} FROM incidents.incidents WHERE id = %s FOR UPDATE",
        (incident_id,),
    )
    row = await cur.fetchone()
    return IncidentRow(*row) if row else None


# ------------------------------------------------------------------ incidents : écriture

async def create_incident(
    conn: psycopg.AsyncConnection,
    *,
    incident_id: uuid.UUID,
    title: str,
    severity: str,
    context: IncidentContext,
    opened_at: datetime,
) -> IncidentRow:
    """Crée un incident avec le statut « ouvert »."""
    ctx = Jsonb(context.to_dict())
    await conn.execute(
        "INSERT INTO incidents.incidents (id, title, status, severity, correlation_context, opened_at, last_activity_at) "
        "VALUES (%s, %s, 'ouvert'::incidents.incident_status, %s::config.severity, %s, %s, %s)",
        (incident_id, title, severity, ctx, opened_at, opened_at),
    )
    return IncidentRow(
        id=incident_id, title=title, status="ouvert", severity=severity,
        correlation_context=context.to_dict(), opened_at=opened_at,
        last_activity_at=opened_at, closed_at=None, assigned_to=None,
    )


async def update_incident(
    conn: psycopg.AsyncConnection,
    incident_id: uuid.UUID,
    *,
    severity: str | None = None,
    context: IncidentContext | None = None,
    last_activity_at: datetime | None = None,
    status: str | None = None,
    closed_at: datetime | None = None,
    assigned_to: uuid.UUID | None | type[_UNSET] = _UNSET,
) -> None:
    """Met à jour un ou plusieurs champs de l'incident (déjà verrouillé)."""
    sets: list[str] = []
    params: list = []
    if severity is not None:
        sets.append("severity = %s::config.severity")
        params.append(severity)
    if context is not None:
        sets.append("correlation_context = %s")
        params.append(Jsonb(context.to_dict()))
    if last_activity_at is not None:
        sets.append("last_activity_at = %s")
        params.append(last_activity_at)
    if status is not None:
        sets.append("status = %s::incidents.incident_status")
        params.append(status)
    if closed_at is not None:
        sets.append("closed_at = %s")
        params.append(closed_at)
    if assigned_to is not _UNSET:
        sets.append("assigned_to = %s")
        params.append(assigned_to)
    if not sets:
        return
    params.append(incident_id)
    await conn.execute(
        f"UPDATE incidents.incidents SET {', '.join(sets)} WHERE id = %s", params
    )


# ------------------------------------------------------------------ incident_alerts

async def attach_alert(
    conn: psycopg.AsyncConnection,
    *,
    incident_id: uuid.UUID,
    alert_id: str,
    criteria: dict,
    attached_at: datetime,
) -> bool:
    """Rattache l'alerte à l'incident. Retourne False si l'alerte est déjà rattachée (UNIQUE sur alert_id)."""
    try:
        await conn.execute(
            "INSERT INTO incidents.incident_alerts (incident_id, alert_id, attached_at, criteria) "
            "VALUES (%s, %s, %s, %s)",
            (incident_id, alert_id, attached_at, Jsonb(criteria)),
        )
        return True
    except UniqueViolation:
        return False


async def get_alert_incident(conn: psycopg.AsyncConnection, alert_id: str) -> uuid.UUID | None:
    """Retourne l'incident auquel l'alerte est rattachée, ou None."""
    cur = await conn.execute(
        "SELECT incident_id FROM incidents.incident_alerts WHERE alert_id = %s", (alert_id,)
    )
    row = await cur.fetchone()
    return row[0] if row else None


# ------------------------------------------------------------------ incident_timeline

async def add_timeline_entry(
    conn: psycopg.AsyncConnection,
    *,
    incident_id: uuid.UUID,
    occurred_at: datetime,
    entry_type: str,
    summary: str,
    alert_id: str | None = None,
    event_id: str | None = None,
    justification: dict | None = None,
    actor_id: uuid.UUID | None = None,
) -> int:
    """Ajoute une entrée dans la timeline de l'incident. Retourne l'ID généré."""
    cur = await conn.execute(
        "INSERT INTO incidents.incident_timeline "
        "(incident_id, occurred_at, entry_type, alert_id, event_id, summary, justification, actor_id) "
        "VALUES (%s, %s, %s::incidents.entry_type, %s, %s, %s, %s, %s) RETURNING id",
        (incident_id, occurred_at, entry_type, alert_id, event_id, summary,
         Jsonb(justification) if justification else None, actor_id),
    )
    return (await cur.fetchone())[0]


# ------------------------------------------------------------------ consultation

async def get_incident(conn: psycopg.AsyncConnection, incident_id: uuid.UUID) -> IncidentRow | None:
    cur = await conn.execute(
        f"SELECT {INC_COLUMNS} FROM incidents.incidents WHERE id = %s", (incident_id,)
    )
    row = await cur.fetchone()
    return IncidentRow(*row) if row else None


async def list_incident_alerts(conn: psycopg.AsyncConnection, incident_id: uuid.UUID) -> list[AttachmentRow]:
    cur = await conn.execute(
        "SELECT incident_id, alert_id, attached_at, criteria "
        "FROM incidents.incident_alerts WHERE incident_id = %s ORDER BY attached_at",
        (incident_id,),
    )
    return [AttachmentRow(*r) for r in await cur.fetchall()]


async def list_timeline(conn: psycopg.AsyncConnection, incident_id: uuid.UUID) -> list[TimelineEntry]:
    cur = await conn.execute(
        "SELECT id, incident_id, occurred_at, recorded_at, entry_type::text, alert_id, event_id, "
        "summary, justification, actor_id "
        "FROM incidents.incident_timeline WHERE incident_id = %s ORDER BY occurred_at, id",
        (incident_id,),
    )
    return [TimelineEntry(*r) for r in await cur.fetchall()]


async def count_incidents(conn: psycopg.AsyncConnection) -> dict:
    """Compteurs pour le tableau de bord : par statut et par sévérité."""
    cur = await conn.execute(
        "SELECT status::text, severity::text, count(*) FROM incidents.incidents GROUP BY 1, 2"
    )
    by_status: dict[str, int] = {"ouvert": 0, "en_cours": 0, "clos": 0}
    by_severity: dict[str, int] = {"faible": 0, "moyenne": 0, "elevee": 0, "critique": 0}
    for status, severity, n in await cur.fetchall():
        by_status[status] = by_status.get(status, 0) + n
        by_severity[severity] = by_severity.get(severity, 0) + n
    return {"total": sum(by_status.values()), "by_status": by_status, "by_severity": by_severity}
