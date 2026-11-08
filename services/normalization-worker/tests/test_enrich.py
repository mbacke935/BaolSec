"""Enrichissement (C10) : nom et criticité de la source, hôte de repli, classement des adresses IP."""
from __future__ import annotations

import json
from datetime import timezone

import pytest

from normalizer.enrich import Enricher
from normalizer.normalize import Normalizer

from .conftest import CONTRACTS, NORMALIZED, make_cache, raw


@pytest.fixture(scope="module")
def enricher():
    return Enricher(make_cache(), ["41.82.0.0/16", "2c0f:f000::/32"])


@pytest.mark.parametrize("ip,scope", [
    ("10.1.2.3", "private"), ("172.31.255.1", "private"), ("192.168.1.1", "private"), ("100.64.0.9", "private"),
    ("127.0.0.1", "private"), ("169.254.10.10", "private"), ("224.0.0.251", "private"),
    ("172.32.0.1", "public"), ("8.8.8.8", "public"), ("41.82.10.4", "private"), ("41.83.0.1", "public"),
    ("::1", "private"), ("fd00::1", "private"), ("fe80::1", "private"), ("2001:4860::8888", "public"),
    ("2c0f:f000::1", "private"), ("::ffff:10.0.0.1", "private"),
])
def test_classement_des_adresses(enricher, ip, scope):
    assert enricher.scope(ip) == scope


def test_nom_criticite_et_hote(norm):
    d = norm("http", '10.0.8.31 - - [02/Nov/2026:10:22:17 +0000] "GET / HTTP/1.1" 200 5 "-" "-"')
    assert d["baolsec"]["source"]["name"] == "WEB-PORTAL" and d["baolsec"]["source"]["criticality"] == "elevee"
    assert d["host"]["name"] == "web-portal" and d["related"]["hosts"] == ["web-portal"]


def test_hote_du_journal_prioritaire(norm):
    d = norm("linux", "Nov  2 10:40:52 autre-nom sshd[1]: Failed password for root from 10.0.0.1 port 1 ssh2")
    assert d["host"]["name"] == "autre-nom"           # le journal nomme la machine : rien n'est remplacé
    assert "criticality" not in d["baolsec"]["source"]   # non renseignée par l'Administrateur


def test_source_absente_du_referentiel(normalizer):
    event = raw("linux", "Nov  2 10:40:52 srv sshd[1]: Failed password for root from 10.0.0.1 port 1 ssh2")
    event["source"]["id"] = "00000000-0000-4000-8000-000000000000"
    doc = normalizer.run(json.dumps(event).encode())
    NORMALIZED.validate(doc)
    assert "name" not in doc["baolsec"]["source"]


def test_pare_feu_sans_hote_declare(tmp_path):
    path = tmp_path / "sources.json"
    path.write_text(json.dumps({"sources": [{"id": "b2c3d4e5-f6a7-4b8c-9d0e-1f2a3b4c5d63", "name": "FW-SANS-HOTE",
                                             "source_type": "firewall"}]}))
    n = Normalizer(CONTRACTS, Enricher(make_cache(path)), timezone.utc)
    doc = n.run(json.dumps(raw("firewall", "<134>Jul  3 19:10:30 filterlog[1]: 6,,,1,em0,match,block,in,4,0x0,,64,0,0,DF,6,tcp,60,10.0.0.2,8.8.8.8,1000,53,0",
                               received_at="2026-07-03T19:10:31Z")).encode())
    assert doc["observer"]["name"] == "FW-SANS-HOTE"
