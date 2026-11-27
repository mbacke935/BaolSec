"""Commandes de l'API sur les alertes et les incidents (C5 section 6, C3 4.6, C16).

Une commande est traitée dans une seule transaction PostgreSQL :
1. verrou de la ligne cible : deux commandes sur la même alerte/incident passent l'une après l'autre ;
2. command_id déjà enregistré dans incident_commands : le résultat enregistré est renvoyé (replayed = true), sans
   réapplication. Un command_id réutilisé pour une autre commande est refusé ;
3. la décision vient de alert_state.lifecycle ou des transitions d'incident ; l'état et la commande sont écrits ensemble.

Ne sont pas enregistrés, faute de ligne à laquelle rattacher la commande (clés étrangères de incident_commands) :
alerte/incident inconnu, auteur inconnu ou désactivé.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Callable

from .. import metrics
from ..alert_state import STATUSES, Refused, State, assign, change_status
from ..repositories import Database
from ..repositories import alerts as repo
from ..repositories import incidents as inc_repo

ALERT_COMMANDS = frozenset({"statut_alerte", "assigner_alerte"})
INCIDENT_COMMANDS = frozenset({"changer_statut", "commenter", "clore", "rouvrir", "assigner"})

# Transitions d'incident (C3 4.6, C16)
INCIDENT_TRANSITIONS: dict[str, set[str]] = {
    "ouvert":   {"en_cours", "clos"},
    "en_cours": {"ouvert", "clos"},
    "clos":     {"en_cours"},
}
INCIDENT_STATUSES = frozenset({"ouvert", "en_cours", "clos"})
STATUS_LABELS = {"ouvert": "ouvert", "en_cours": "en cours", "clos": "clos"}


def iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def result_doc(command_id: str, result: str, completed_at: datetime, replayed: bool, error: dict | None = None) -> dict:
    doc = {"contract": "incident_command_result/v1", "command_id": command_id, "result": result,
           "completed_at": iso(completed_at), "replayed": replayed}
    if error is not None:
        doc["error"] = error
    return doc


class CommandService:
    def __init__(self, db: Database, clock: Callable[[], datetime] | None = None):
        self._db = db
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    async def apply(self, cmd: dict) -> dict:
        """`cmd` est un incident_command/v1 déjà validé. Renvoie un incident_command_result/v1.

        DatabaseUnavailable si PostgreSQL ne répond pas (rien n'est alors enregistré :
        l'appelant peut renvoyer la même commande, même command_id).
        """
        ctype = cmd["command_type"]
        if ctype in ALERT_COMMANDS:
            return await self._apply_alert_command(cmd, ctype)
        return await self._apply_incident_command(cmd, ctype)

    # ---- commandes sur les alertes (statut_alerte, assigner_alerte) ----

    async def _apply_alert_command(self, cmd: dict, ctype: str) -> dict:
        raw_id, alert_id = cmd["command_id"], cmd["target"]["alert_id"]
        command_id, issuer = uuid.UUID(raw_id), uuid.UUID(cmd["issued_by"]["user_id"])
        payload, now = cmd["payload"], self._clock()

        async with self._db.connection() as conn:
            alert = await repo.lock_alert(conn, alert_id)
            if alert is None:
                return self._refused(raw_id, "cible_introuvable", f"alerte {alert_id} inconnue", now, ctype)

            stored = await repo.find_command(conn, command_id)
            if stored is not None:
                if (stored.command_type, stored.alert_id, stored.issued_by, stored.payload) != (ctype, alert_id, issuer, payload):
                    return self._refused(raw_id, "donnees_invalides", "command_id déjà utilisé pour une autre commande",
                                         now, ctype)
                metrics.REPLAYS.inc()
                error = json.loads(stored.error) if stored.error else None
                return result_doc(raw_id, stored.result, stored.completed_at, True, error)

            if await repo.user_is_active(conn, issuer) is not True:
                return self._refused(raw_id, "donnees_invalides", "auteur de la commande inconnu ou désactivé", now, ctype)

            current = State(alert.status, alert.assigned_to)
            try:
                new = await self._decide_alert(conn, ctype, current, payload, issuer)
                error = None
            except Refused as refusal:
                new, error = None, {"code": refusal.code, "message": refusal.message}

            if new is not None:
                await repo.update_alert(conn, alert_id, new.status, new.assigned_to, now)
            outcome = "acceptee" if new is not None else "refusee"
            await repo.insert_command(conn, command_id=command_id, command_type=ctype, alert_id=alert_id,
                                      issued_by=issuer, payload=payload, result=outcome,
                                      error=json.dumps(error, ensure_ascii=False) if error else None, at=now)
        metrics.COMMANDS.labels(ctype, outcome).inc()
        return result_doc(raw_id, outcome, now, False, error)

    # ---- commandes sur les incidents (C16) ----

    async def _apply_incident_command(self, cmd: dict, ctype: str) -> dict:
        raw_id, incident_id_str = cmd["command_id"], cmd["target"]["incident_id"]
        command_id, issuer = uuid.UUID(raw_id), uuid.UUID(cmd["issued_by"]["user_id"])
        incident_id = uuid.UUID(incident_id_str)
        payload, now = cmd.get("payload") or {}, self._clock()

        async with self._db.connection() as conn:
            inc = await inc_repo.lock_incident(conn, incident_id)
            if inc is None:
                return self._refused(raw_id, "cible_introuvable", f"incident {incident_id} inconnu", now, ctype)

            stored = await repo.find_command(conn, command_id)
            if stored is not None:
                metrics.REPLAYS.inc()
                error = json.loads(stored.error) if stored.error else None
                return result_doc(raw_id, stored.result, stored.completed_at, True, error)

            if await repo.user_is_active(conn, issuer) is not True:
                return self._refused(raw_id, "donnees_invalides", "auteur de la commande inconnu ou désactivé", now, ctype)

            try:
                await self._decide_incident(conn, ctype, inc, payload, issuer, now)
                error, outcome = None, "acceptee"
            except Refused as refusal:
                error = {"code": refusal.code, "message": refusal.message}
                outcome = "refusee"

            await inc_repo.insert_incident_command(
                conn, command_id=command_id, command_type=ctype, incident_id=incident_id,
                issued_by=issuer, payload=payload, result=outcome,
                error=json.dumps(error, ensure_ascii=False) if error else None, at=now,
            )
        metrics.COMMANDS.labels(ctype, outcome).inc()
        return result_doc(raw_id, outcome, now, False, error)

    async def _decide_incident(self, conn, ctype: str, inc, payload: dict, issuer: uuid.UUID, now: datetime) -> None:
        """Applique la commande d'incident. Lève Refused si non autorisée."""
        if ctype == "changer_statut":
            target = payload["status"]
            if target not in INCIDENT_STATUSES:
                raise Refused("donnees_invalides", f"statut inconnu : {target}")
            allowed = INCIDENT_TRANSITIONS.get(inc.status, set())
            if target not in allowed:
                raise Refused("transition_interdite", f"{inc.status} → {target} interdit")
            closed_at = now if target == "clos" else None
            await inc_repo.update_incident(conn, inc.id, status=target, closed_at=closed_at, last_activity_at=now)
            await inc_repo.add_timeline_entry(
                conn, incident_id=inc.id, occurred_at=now, entry_type="status_change",
                summary=f"Statut : {STATUS_LABELS[inc.status]} → {STATUS_LABELS[target]}", actor_id=issuer,
            )

        elif ctype == "commenter":
            body = payload["body"]
            comment_id = await inc_repo.add_comment(conn, incident_id=inc.id, author_id=issuer, body=body,
                                                    created_at=now)
            await inc_repo.update_incident(conn, inc.id, last_activity_at=now)
            # Le texte est repris dans la chronologie (EF-08) : l'interface l'affiche échappé (ES-06).
            await inc_repo.add_timeline_entry(
                conn, incident_id=inc.id, occurred_at=now, entry_type="comment",
                summary="Commentaire ajouté", actor_id=issuer,
                justification={"comment_id": str(comment_id), "body": body},
            )

        elif ctype == "clore":
            if inc.status == "clos":
                raise Refused("transition_interdite", "incident déjà clos")
            await inc_repo.update_incident(conn, inc.id, status="clos", closed_at=now, last_activity_at=now)
            await inc_repo.add_timeline_entry(
                conn, incident_id=inc.id, occurred_at=now, entry_type="status_change",
                summary="Incident clos", actor_id=issuer,
                justification={"reason": payload["reason"]} if payload.get("reason") else None,
            )

        elif ctype == "rouvrir":
            if inc.status != "clos":
                raise Refused("transition_interdite", f"incident non clos (statut actuel : {inc.status})")
            await inc_repo.update_incident(conn, inc.id, status="en_cours", closed_at=None, last_activity_at=now)
            await inc_repo.add_timeline_entry(
                conn, incident_id=inc.id, occurred_at=now, entry_type="status_change",
                summary="Incident rouvert (clos → en cours)", actor_id=issuer,
                justification={"reason": payload["reason"]} if payload.get("reason") else None,
            )

        elif ctype == "assigner":
            assignee = None if payload.get("assignee_id") is None else uuid.UUID(payload["assignee_id"])
            if assignee is not None:
                state = await repo.user_is_active(conn, assignee)
                if state is None:
                    raise Refused("donnees_invalides", f"analyste {assignee} inconnu")
                if state is False:
                    raise Refused("donnees_invalides", f"compte de l'analyste {assignee} désactivé")
            await inc_repo.update_incident(conn, inc.id, assigned_to=assignee, last_activity_at=now)
            label = (await inc_repo.username_of(conn, assignee) or str(assignee)) if assignee else "personne"
            await inc_repo.add_timeline_entry(
                conn, incident_id=inc.id, occurred_at=now, entry_type="status_change",
                summary=f"Assigné à {label}", actor_id=issuer,
            )

    async def _decide_alert(self, conn, ctype: str, current: State, payload: dict, issuer: uuid.UUID) -> State:
        if ctype == "statut_alerte":
            target = payload["status"]
            if target not in STATUSES:
                raise Refused("donnees_invalides", f"statut inconnu : {target}")
            return change_status(current, target, issuer)
        assignee = None if payload["assignee_id"] is None else uuid.UUID(payload["assignee_id"])
        if assignee is not None:
            state = await repo.user_is_active(conn, assignee)
            if state is None:
                raise Refused("donnees_invalides", f"analyste {assignee} inconnu")
            if state is False:
                raise Refused("donnees_invalides", f"compte de l'analyste {assignee} désactivé")
        return assign(current, assignee)

    def _refused(self, command_id: str, code: str, message: str, now: datetime, ctype: str) -> dict:
        """Refus non enregistré (voir l'en-tête du module)."""
        metrics.COMMANDS.labels(ctype, "refusee").inc()
        return result_doc(command_id, "refusee", now, False, {"code": code, "message": message})
