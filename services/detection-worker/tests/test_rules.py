"""Règles YAML : contrat rule/v1, conditions, index par catégorie (C12)."""
from __future__ import annotations

import pytest

from conftest import RULES, event
from detector.rules import RuleError, rule_uuid


def test_toutes_les_regles_du_depot_sont_valides(validator):
    files = sorted(RULES.glob("*.yml"))
    assert files
    codes = [validator.parse(f.read_text(encoding="utf-8")).code for f in files]
    assert len(codes) == len(set(codes))
    for f, code in zip(files, codes):
        assert f.stem == code, "le fichier porte le code de sa règle"


@pytest.mark.parametrize("text, why", [
    ("id: AUTH-009\nname: x\n", "required"),
    ("[1, 2]", "objet"),
    ("id: AUTH-009\nname: Sans seuil\nseverity: faible\ntype: window\ncategory: [authentication]\n"
     "match: {event.outcome: failure}\ngroup_by: [user.name]\nwindow: 5m\nmessage: xyz", "threshold"),
    ("id: NET-009\nname: Opérateur\nseverity: faible\ntype: simple\ncategory: [network]\n"
     "match: {source.ip: {eval: '1'}}\nmessage: xyz", ""),
    ("id: NET-009\nname: Regex\nseverity: faible\ntype: simple\ncategory: [network]\n"
     "match: {source.ip: {regex: '('}}\nmessage: xyz", "régulière"),
    ("id: NET-009\nname: Trop longue\nseverity: faible\ntype: window\ncategory: [network]\n"
     "match: {source.ip: {exists: true}}\ngroup_by: [source.ip]\nwindow: 25h\nthreshold: 3\nmessage: xyz", "24 h"),
])
def test_regles_refusees(validator, text, why):
    with pytest.raises(RuleError) as err:
        validator.parse(text)
    assert why in str(err.value)


BASE = "id: TST-001\nname: Test\nseverity: faible\ntype: simple\ncategory: [authentication]\nmessage: xyz\nmatch:\n"


@pytest.mark.parametrize("cond, doc, expected", [
    ("  event.outcome: FAILURE", {}, True),                                   # sans tenir compte de la casse
    ("  event.category: authentication", {}, True),                           # champ à plusieurs valeurs
    ("  event.outcome: [success, failure]", {}, True),
    ("  event.outcome: {not: failure}", {}, False),
    ("  user.name: {exists: true}", {}, True),
    ("  user.name: {exists: false}", {"user": None}, True),
    ("  process.command_line: {contains: ENCODED}", {"process__command_line": "ps -encodedcommand x"}, True),
    ("  process.command_line: {regex: '^ps'}", {"process__command_line": "ps -x"}, True),
    ("  destination.port: {gte: 1024}", {"destination__port": 80}, False),
    ("  destination.port: {lte: 1024}", {"destination__port": 80}, True),
    ("  http.response.status_code: [401, 403]", {"http__response__status_code": 403}, True),
])
def test_conditions(validator, cond, doc, expected):
    r = validator.parse(BASE + cond)
    extra = {k: v for k, v in doc.items() if v is not None}
    ev = event(**extra) if "user" not in doc else event(user=None)
    assert r.matches(ev) is expected


def test_index_par_categorie(rules_cache):
    auth = {r.code for r in rules_cache.candidates(["authentication"])}
    proc = {r.code for r in rules_cache.candidates(["process"])}
    net = {r.code for r in rules_cache.candidates(["network"])}
    web = {r.code for r in rules_cache.candidates(["web"])}
    assert "AUTH-001" in auth and "AUTH-002" in auth and "AUTH-003" in auth
    assert "AUTH-001" not in proc
    assert "SYS-001" in proc
    assert "FW-001" in net and "FW-002" in net
    assert "WEB-001" in web and "WEB-002" in web


def test_identifiant_postgresql_stable():
    assert rule_uuid("AUTH-001") == rule_uuid("AUTH-001") != rule_uuid("AUTH-002")


def test_huit_regles_dans_le_depot(rules_cache):
    codes = sorted(r.code for r in rules_cache.rules)
    assert codes == ["AUTH-001", "AUTH-002", "AUTH-003", "FW-001", "FW-002", "SYS-001", "WEB-001", "WEB-002"]


async def test_regle_refusee_n_empeche_pas_les_autres(validator, tmp_path):
    from detector.rules import FileRules, RulesCache
    (tmp_path / "ok.yml").write_text((RULES / "AUTH-001.yml").read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "ko.yml").write_text("id: BAD\n", encoding="utf-8")
    cache = RulesCache(FileRules(tmp_path), validator)
    await cache.refresh()
    assert [r.code for r in cache.rules] == ["AUTH-001"] and "ko.yml" in cache.rejected
