"""Cycle de vie d'une alerte : statuts, transitions et attribution (EF-06, C4 5.3, C5 section 6).

Fonctions pures, sans accès à la base : elles décident, la couche commandes applique et enregistre.

Statuts : nouvelle → en_cours → cloturee. Règles :
- une alerte « nouvelle » n'a pas d'analyste ; une alerte « en_cours » en a toujours un ;
- l'analyste qui passe une alerte en cours en devient l'assigné ; en la remettant « nouvelle », il s'en défait ;
- assigner une alerte nouvelle la prend en charge (elle passe en cours) ; retirer l'assigné d'une alerte en cours la remet dans la file ;
- une alerte clôturée garde son dernier assigné et ne peut plus être assignée : il faut d'abord la rouvrir ;
- redemander l'état actuel est refusé, pour que deux analystes qui agissent en même temps voient le conflit.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

TRANSITIONS: dict[str, frozenset[str]] = {
    "nouvelle": frozenset({"en_cours", "cloturee"}),     # prise en charge, ou clôture directe (bruit, doublon évident)
    "en_cours": frozenset({"nouvelle", "cloturee"}),     # retour dans la file, ou fin d'analyse
    "cloturee": frozenset({"en_cours"}),                 # réouverture (clôture faite par erreur)
}


class Refused(Exception):
    """Commande refusée. `code` est un code de incident_command_result/v1."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class State:
    status: str
    assigned_to: uuid.UUID | None


def change_status(current: State, target: str, issuer: uuid.UUID) -> State:
    if target == current.status:
        raise Refused("transition_interdite", f"l'alerte est déjà « {target} »")
    if target not in TRANSITIONS[current.status]:
        raise Refused("transition_interdite", f"passage de « {current.status} » à « {target} » interdit")
    if target == "en_cours":
        return State("en_cours", issuer)
    if target == "nouvelle":
        return State("nouvelle", None)
    return State("cloturee", current.assigned_to)


def assign(current: State, assignee: uuid.UUID | None) -> State:
    if current.status == "cloturee":
        raise Refused("transition_interdite", "alerte clôturée : la rouvrir avant de l'assigner")
    if assignee is None:
        if current.assigned_to is None:
            raise Refused("transition_interdite", "l'alerte n'a pas d'analyste assigné")
        return State("nouvelle", None)
    if assignee == current.assigned_to:
        raise Refused("transition_interdite", "l'alerte est déjà assignée à cet analyste")
    return State("en_cours", assignee)
