"""Sévérité normalisée des événements (C5, section 4).

Valeurs de départ, réunies ici pour être ajustées après les tests (C24 à C28).
La sévérité d'une alerte ne vient pas d'ici : elle est fixée par la règle de détection.
"""
from __future__ import annotations

SCORES = {"info": 0, "faible": 1, "moyenne": 2, "elevee": 3, "critique": 4}

# Linux et Syslog : code de sévérité 0 à 7
SYSLOG = {0: "critique", 1: "critique", 2: "critique", 3: "elevee", 4: "moyenne", 5: "faible", 6: "info", 7: "info"}

# Windows : selon l'identifiant d'événement (le niveau « Information » n'a pas de sens pour l'audit)
WINDOWS = {4625: "faible"}

# Pare-feu : selon la décision (la sévérité Syslog décrit le message, pas le risque)
FIREWALL = {"connection_denied": "faible", "connection_allowed": "info", "connection_logged": "info"}

# Application web : niveau du journal JSON
APP_LEVEL = {"emergency": "moyenne", "alert": "moyenne", "critical": "moyenne", "fatal": "moyenne",
             "error": "moyenne", "err": "moyenne", "warning": "faible", "warn": "faible"}


def from_syslog(code: int | None) -> str:
    return "info" if code is None else SYSLOG[code]


def from_windows(event_id: int) -> str:
    return WINDOWS.get(event_id, "info")


def from_firewall(action: str) -> str:
    return FIREWALL.get(action, "info")


def from_http_status(status: int) -> str:
    if status >= 500:
        return "moyenne"
    if status >= 400:
        return "faible"
    return "info"


def from_app(level: str | None, action: str, outcome: str) -> str:
    """Niveau du journal s'il est fourni ; sinon une connexion refusée vaut « faible »,
    comme un échec d'ouverture de session Windows ou une requête web en 4xx."""
    if level:
        return APP_LEVEL.get(level.lower(), "info")
    if action == "api_login" and outcome == "failure":
        return "faible"
    return "info"


def block(label: str) -> dict:
    return {"label": label, "score": SCORES[label]}
