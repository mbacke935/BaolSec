"""Modèle d'alerte : extraction depuis alert/v1, identifiant de règle, sévérités conservées."""
from __future__ import annotations

import re
import uuid

import pytest

from conftest import EXAMPLE, ROOT, alert_doc
from incidents.alert_state import RULE_NAMESPACE, AlertRejected, parse_alert, rule_uuid


def test_exemple_du_contrat_est_conforme(contracts):
    assert contracts.alert_errors(EXAMPLE) is None


def test_champs_conserves():
    a = parse_alert(EXAMPLE)
    assert a.alert_id == EXAMPLE["event"]["id"] and len(a.alert_id) == 64
    assert a.rule_code == EXAMPLE["rule"]["id"] == "AUTH-001"
    assert a.severity == EXAMPLE["baolsec"]["severity"]["label"] == "critique"
    assert a.triggered_at.utcoffset().total_seconds() == 0              # horodatage conservé en UTC
    assert a.triggered_at.isoformat().replace("+00:00", "Z").startswith(EXAMPLE["@timestamp"][:19])


def test_identifiant_de_regle_deterministe():
    assert parse_alert(EXAMPLE).rule_id == uuid.uuid5(RULE_NAMESPACE, "AUTH-001") == rule_uuid("AUTH-001")
    assert rule_uuid("AUTH-001") != rule_uuid("AUTH-002")


def test_espace_de_noms_identique_chez_detection_et_chargeur_de_regles():
    """Trois copies de la même constante : une divergence ferait échouer la clé étrangère vers config.rules."""
    pattern = re.compile(r'RULE_NAMESPACE\s*=\s*uuid\.UUID\(\s*"([0-9a-f-]{36})"')
    for path in ("services/detection-worker/src/detector/rules/model.py", "infrastructure/database/load_rules.py"):
        found = pattern.search((ROOT / path).read_text(encoding="utf-8"))
        assert found, f"constante introuvable dans {path}"
        assert uuid.UUID(found.group(1)) == RULE_NAMESPACE, path


@pytest.mark.parametrize("severity", ["faible", "moyenne", "elevee", "critique"])
def test_sevérités_conservees(severity, contracts):
    doc = alert_doc(severity=severity)
    doc["baolsec"]["severity"]["score"] = {"faible": 1, "moyenne": 2, "elevee": 3, "critique": 4}[severity]
    assert contracts.alert_errors(doc) is None
    assert parse_alert(doc).severity == severity


def test_severite_info_refusee_car_absente_de_config_severity():
    doc = alert_doc(severity="info")
    doc["baolsec"]["severity"]["score"] = 0
    with pytest.raises(AlertRejected, match="info"):
        parse_alert(doc)
