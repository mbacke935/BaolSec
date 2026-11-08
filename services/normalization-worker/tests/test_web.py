"""Application web : journal d'accès (combined, common) et journal applicatif JSON."""
from __future__ import annotations

import json

import pytest

from baolsec_common.messaging import ProcessingError

from .conftest import raw


def test_requete_servie(norm):
    d = norm("http", '83.149.9.216 - - [17/May/2015:10:05:03 +0000] "GET /images/kibana-search.png HTTP/1.1" 200 203023 "http://x/" "Mozilla/5.0"')
    assert d["event"]["outcome"] == "success" and d["event"]["type"] == ["access"]
    assert d["host"]["name"] == "web-portal"                       # config.sources.host (C10)
    assert d["baolsec"]["source"]["criticality"] == "elevee"
    assert d["baolsec"]["ip_scope"] == {"source": "public"}
    assert d["message"] == "GET /images/kibana-search.png servi (200) pour 83.149.9.216"


def test_erreur_serveur_utilisateur_authentifie(norm):
    d = norm("http", '10.0.8.31 - alice [02/Nov/2026:10:22:17 +0100] "POST /api/pay HTTP/2.0" 502 0 "-" "-"')
    assert d["@timestamp"] == "2026-11-02T09:22:17Z"
    assert d["user"]["name"] == "alice" and "user_agent" not in d
    assert d["baolsec"]["severity"]["label"] == "moyenne" and d["event"]["outcome"] == "failure"


def test_format_common_ipv6(norm):
    d = norm("http", '2001:db8::5 - - [02/Nov/2026:10:22:17 +0000] "GET / HTTP/1.1" 404 12')
    assert d["source"]["ip"] == "2001:db8::5" and d["http"]["response"]["status_code"] == 404


def test_requete_illisible_408(norm):
    d = norm("http", '10.0.8.31 - - [02/Nov/2026:10:22:17 +0000] "-" 408 0 "-" "-"')
    assert "http" in d and "method" not in d["http"].get("request", {})


def test_connexion_api_reussie(norm):
    d = norm("http", '{"ts":"2026-11-02T10:31:04.250Z","app":"portal-api","event":"login_succeeded","user":"moussa","client_ip":"41.82.10.4","level":"INFO"}')
    assert d["event"]["action"] == "api_login" and d["event"]["outcome"] == "success"
    assert d["user"]["name"] == "moussa" and d["log"]["level"] == "info"
    assert d["baolsec"]["ip_scope"] == {"source": "private"}        # 41.82.0.0/16 déclaré interne
    assert d["baolsec"]["severity"]["label"] == "info"


def test_evenement_applicatif_avec_niveau(norm):
    d = norm("http", {"timestamp": "2026-11-02T10:31:04Z", "level": "ERROR", "event": "Payment-Timeout", "message": "délai dépassé"})
    assert d["event"]["action"] == "payment_timeout" and d["event"]["category"] == ["web"]
    assert d["baolsec"]["severity"]["label"] == "moyenne" and d["message"] == "délai dépassé"


@pytest.mark.parametrize("payload", ["ligne quelconque", "{json cassé", "[1,2]"])
def test_lignes_refusees(normalizer, payload):
    with pytest.raises(ProcessingError) as err:
        normalizer.run(json.dumps(raw("http", payload)).encode())
    assert err.value.reason_code == "parse_error"
