"""Alertes conformes au contrat alert/v1 (C5)."""
from __future__ import annotations

import json

from jsonschema import Draft202012Validator, FormatChecker

from conftest import CONTRACTS, event
from detector import alert, engine
from test_engine import NOW, burst

VALIDATOR = Draft202012Validator(json.loads((CONTRACTS / "alert" / "v1" / "schema.json").read_text()),
                                 format_checker=FormatChecker())


def fire(auth001, evs):
    state = None
    for ev in evs:
        d = engine.evaluate_window(auth001, ev, state, NOW, 120)
        state = d.state or state
        if d.fire:
            return d.fire


def test_alerte_conforme_et_explicable(auth001):
    evs = burst(5)
    doc = alert.build(auth001, fire(auth001, evs))
    VALIDATOR.validate(doc)
    assert doc["rule"] == {"id": "AUTH-001", "name": "Force brute sur un compte", "version": "1"}
    assert doc["baolsec"]["severity"] == {"label": "elevee", "score": 3}
    assert doc["baolsec"]["alert"]["event_ids"] == [e["event"]["id"] for e in evs]
    assert doc["message"] == "5 échecs d'authentification en 10 min pour admin depuis 10.0.4.23"
    assert doc["user"] == {"name": "admin"} and doc["source"] == {"ip": "10.0.4.23"}
    assert doc["related"]["hosts"] == ["srv-linux-01"]
    assert doc["@timestamp"] == evs[-1]["@timestamp"]


def test_identifiant_de_l_alerte(auth001):
    doc = alert.build(auth001, fire(auth001, burst(5)))
    assert doc["event"]["id"] == engine.alert_id("AUTH-001", "admin|10.0.4.23", doc["baolsec"]["alert"]["window_start"])


def test_alerte_simple_conforme(validator):
    from conftest import RULES
    sys001 = validator.parse((RULES / "SYS-001.yml").read_text(encoding="utf-8"))
    ev = event(category="process", outcome="success", event__code="4688", user="admin", host="PC-WIN-COMPTA",
               process__command_line="powershell -enc SQBFAFgA")
    doc = alert.build(sys001, engine.evaluate_simple(sys001, ev).fire)
    VALIDATOR.validate(doc)
    assert doc["message"] == "PowerShell lancé avec une commande encodée par admin sur PC-WIN-COMPTA"
