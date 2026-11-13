"""Requêtes SQL sur incidents.alert_state, incidents.incident_commands et acces.users (C4 5.1 et 5.3).

Chaque fonction reçoit la connexion (donc la transaction) de l'appelant : c'est lui qui décide de ce qui forme
une seule transaction (C3 4.6 : « message non acquitté si la transaction échoue »).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

import psycopg
from psycopg import errors
from psycopg.types.json import Jsonb

from ..alert_state import SEVERITIES, STATUSES, Alert, rule_uuid
from . import UnknownRule

COLUMNS = "alert_id, rule_id, severity::text, triggered_at, status::text, assigned_to, status_changed_at, created_at"
MAX_PAGE_SIZE = 100


@dataclass(frozen=True)
class AlertRow:
    alert_id: str
    rule_id: uuid.UUID
    severity: str
    triggered_at: datetime
    status: str
    assigned_to: uuid.UUID | None
    status_changed_at: datetime
    created_at: datetime


@dataclass(frozen=True)
class StoredCommand:
    command_id: uuid.UUID
    command_type: str
    alert_id: str | None
    issued_by: uuid.UUID
    payload: dict | None
    result: str
    error: str | None
    completed_at: datetime


@dataclass(frozen=True)
class AlertFilter:
    status: str | None = None
    severity: str | None = None
    rule_code: str | None = None
    assigned_to: uuid.UUID | None = None
    triggered_from: datetime | None = None       # incluse
    triggered_to: datetime | None = None         # incluse


@dataclass(frozen=True)
class Page:
    items: list[AlertRow]
    total: int
    page: int
    size: int


# ------------------------------------------------------------------ écriture

async def insert_alert(conn: psycopg.AsyncConnection, alert: Alert) -> bool:
    """Crée l'état « nouvelle » de l'alerte. False si l'alert_id existe déjà (doublon, rien n'est modifié)."""
    try:
        cur = await conn.execute(
            "INSERT INTO incidents.alert_state (alert_id, rule_id, severity, triggered_at) "
            "VALUES (%s, %s, %s::config.severity, %s) ON CONFLICT (alert_id) DO NOTHING",
            (alert.alert_id, alert.rule_id, alert.severity, alert.triggered_at))
    except errors.ForeignKeyViolation as exc:
        raise UnknownRule(f"règle {alert.rule_code} ({alert.rule_id}) absente de config.rules") from exc
    return cur.rowcount == 1


async def lock_alert(conn: psycopg.AsyncConnection, alert_id: str) -> AlertRow | None:
    """Lit l'alerte en posant un verrou de ligne : les commandes sur une même alerte passent l'une après l'autre."""
    cur = await conn.execute(f"SELECT {COLUMNS} FROM incidents.alert_state WHERE alert_id = %s FOR UPDATE", (alert_id,))
    row = await cur.fetchone()
    return AlertRow(*row) if row else None


async def update_alert(conn: psycopg.AsyncConnection, alert_id: str, status: str, assigned_to: uuid.UUID | None,
                       changed_at: datetime) -> None:
    await conn.execute(
        "UPDATE incidents.alert_state SET status = %s::incidents.alert_status, assigned_to = %s, status_changed_at = %s "
        "WHERE alert_id = %s", (status, assigned_to, changed_at, alert_id))


async def user_is_active(conn: psycopg.AsyncConnection, user_id: uuid.UUID) -> bool | None:
    """None : utilisateur inconnu ; sinon l'état de son compte."""
    cur = await conn.execute("SELECT is_active FROM acces.users WHERE id = %s", (user_id,))
    row = await cur.fetchone()
    return None if row is None else bool(row[0])


async def find_command(conn: psycopg.AsyncConnection, command_id: uuid.UUID) -> StoredCommand | None:
    cur = await conn.execute(
        "SELECT command_id, command_type::text, alert_id, issued_by, payload, result::text, error, completed_at "
        "FROM incidents.incident_commands WHERE command_id = %s", (command_id,))
    row = await cur.fetchone()
    return StoredCommand(*row) if row else None


async def insert_command(conn: psycopg.AsyncConnection, *, command_id: uuid.UUID, command_type: str, alert_id: str,
                         issued_by: uuid.UUID, payload: dict, result: str, error: str | None, at: datetime) -> None:
    await conn.execute(
        "INSERT INTO incidents.incident_commands (command_id, command_type, alert_id, issued_by, payload, result, "
        "error, created_at, completed_at) VALUES (%s, %s::incidents.command_type, %s, %s, %s, "
        "%s::incidents.command_result, %s, %s, %s)",
        (command_id, command_type, alert_id, issued_by, Jsonb(payload), result, error, at, at))


# ------------------------------------------------------------------ consultation

async def get_alert(conn: psycopg.AsyncConnection, alert_id: str) -> AlertRow | None:
    cur = await conn.execute(f"SELECT {COLUMNS} FROM incidents.alert_state WHERE alert_id = %s", (alert_id,))
    row = await cur.fetchone()
    return AlertRow(*row) if row else None


def _where(f: AlertFilter) -> tuple[str, list]:
    clauses: list[str] = []
    params: list = []
    if f.status is not None:
        if f.status not in STATUSES:
            raise ValueError(f"statut inconnu : {f.status}")
        clauses.append("status = %s::incidents.alert_status")
        params.append(f.status)
    if f.severity is not None:
        if f.severity not in SEVERITIES:
            raise ValueError(f"sévérité inconnue : {f.severity}")
        clauses.append("severity = %s::config.severity")
        params.append(f.severity)
    if f.rule_code is not None:
        clauses.append("rule_id = %s")
        params.append(rule_uuid(f.rule_code))
    if f.assigned_to is not None:
        clauses.append("assigned_to = %s")
        params.append(f.assigned_to)
    if f.triggered_from is not None:
        clauses.append("triggered_at >= %s")
        params.append(f.triggered_from)
    if f.triggered_to is not None:
        clauses.append("triggered_at <= %s")
        params.append(f.triggered_to)
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


async def list_alerts(conn: psycopg.AsyncConnection, f: AlertFilter | None = None, *, page: int = 1,
                      size: int = 25) -> Page:
    """Alertes les plus récentes d'abord (index status, triggered_at), filtrées et paginées (C5 : 25 par défaut, 100 au plus)."""
    if page < 1 or not 1 <= size <= MAX_PAGE_SIZE:
        raise ValueError(f"page ≥ 1 et taille entre 1 et {MAX_PAGE_SIZE}")
    where, params = _where(f or AlertFilter())
    total = (await (await conn.execute(f"SELECT count(*) FROM incidents.alert_state{where}", params)).fetchone())[0]
    cur = await conn.execute(
        f"SELECT {COLUMNS} FROM incidents.alert_state{where} ORDER BY triggered_at DESC, alert_id "
        f"LIMIT %s OFFSET %s", [*params, size, (page - 1) * size])
    return Page([AlertRow(*r) for r in await cur.fetchall()], total, page, size)


async def count_alerts(conn: psycopg.AsyncConnection) -> dict:
    """Compteurs du tableau de bord : par statut, par sévérité, et par sévérité parmi les alertes non clôturées."""
    cur = await conn.execute("SELECT status::text, severity::text, count(*) FROM incidents.alert_state GROUP BY 1, 2")
    by_status = {s: 0 for s in STATUSES}
    by_severity = {s: 0 for s in SEVERITIES}
    open_by_severity = {s: 0 for s in SEVERITIES}
    for status, severity, n in await cur.fetchall():
        by_status[status] += n
        by_severity[severity] += n
        if status != "cloturee":
            open_by_severity[severity] += n
    return {"total": sum(by_status.values()), "by_status": by_status, "by_severity": by_severity,
            "open_by_severity": open_by_severity}
