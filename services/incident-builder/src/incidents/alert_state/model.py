"""Alerte reçue (alert/v1, C5) réduite à ce que conserve incidents.alert_state (C4 5.3).

Le document complet (règle, événements justificatifs, message) reste dans OpenSearch et ne change plus (EF-06) :
alert_state ne garde que les copies nécessaires pour trier et filtrer en SQL (RG-07), plus l'état de traitement.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

# Même espace de noms que detection-worker (detector/rules/model.py) et que le chargeur de règles
# (infrastructure/database/load_rules.py) : config.rules.id = UUID v5 (espace, code de la règle).
# tests/test_alert.py vérifie que les trois copies restent identiques.
RULE_NAMESPACE = uuid.UUID("6f1c0d5e-2b7a-5c3e-9a41-baa15ec00001")

STATUSES = ("nouvelle", "en_cours", "cloturee")
# Valeurs de config.severity (C4). Le contrat alert/v1 admet aussi « info » ; aucune règle n'en produit (rule/v1).
SEVERITIES = ("faible", "moyenne", "elevee", "critique")


class AlertRejected(ValueError):
    """Alerte conforme au contrat mais que alert_state ne peut pas conserver."""


def rule_uuid(code: str) -> uuid.UUID:
    return uuid.uuid5(RULE_NAMESPACE, code)


@dataclass(frozen=True)
class Alert:
    alert_id: str
    rule_code: str
    severity: str
    triggered_at: datetime
    doc: dict | None = None  # document alert/v1 complet, conservé pour la corrélation (C16)

    @property
    def rule_id(self) -> uuid.UUID:
        return rule_uuid(self.rule_code)


def parse_alert(doc: dict) -> Alert:
    """Extrait les champs conservés d'un document alert/v1 déjà validé par le contrat."""
    label = doc["baolsec"]["severity"]["label"]
    if label not in SEVERITIES:
        raise AlertRejected(f"sévérité « {label} » non conservée par alert_state (valeurs admises : {', '.join(SEVERITIES)})")
    return Alert(
        alert_id=doc["event"]["id"],
        rule_code=doc["rule"]["id"],
        severity=label,
        triggered_at=datetime.fromisoformat(doc["@timestamp"].replace("Z", "+00:00")),
        doc=doc,
    )
