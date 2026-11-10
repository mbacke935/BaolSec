"""Fenêtres temporelles et état des règles (C14), sans KV ni broker."""
from __future__ import annotations

from conftest import BASE_MS, event
from detector import engine

MIN = 60_000
NOW = BASE_MS + 30 * MIN


def run(rule, events, state=None, now=None):
    """Évalue les événements dans l'ordre ; sans « now », chacun est traité 1 s après sa date (temps réel)."""
    outcomes, fires = [], []
    for ev in events:
        t = now if now is not None else engine.parse_ms(ev["@timestamp"]) + 1000
        d = engine.evaluate_window(rule, ev, state, t, 120)
        outcomes.append(d.outcome)
        if d.state is not None:
            state = d.state
        if d.fire:
            fires.append(d.fire)
    return outcomes, fires, state


def burst(n, start=NOW - 9 * MIN, step=MIN, **kw):
    return [event(ts=start + i * step, **kw) for i in range(n)]


def test_quatre_echecs_aucune_alerte_cinq_une_alerte(auth001):
    outcomes, fires, _ = run(auth001, burst(4))
    assert fires == [] and outcomes == ["counted"] * 4
    outcomes, fires, _ = run(auth001, burst(5))
    assert outcomes[-1] == "fired" and len(fires) == 1
    assert fires[0]["count"] == 5 and len(fires[0]["events"]) == 5
    assert fires[0]["key"] == "admin|10.0.4.23"


def test_meme_evenement_relivre_compte_une_fois(auth001):
    evs = burst(4)
    outcomes, fires, _ = run(auth001, evs + [evs[2], evs[3]])
    assert outcomes[-2:] == ["duplicate", "duplicate"] and fires == []


def test_fenetre_glissante(auth001):
    # 3 échecs anciens, puis 4 échecs 12 min plus tard : jamais 5 dans une même fenêtre de 10 min
    old = burst(3, start=NOW - 25 * MIN)
    new = burst(4, start=NOW - 13 * MIN)
    _, fires, state = run(auth001, old + new)
    assert fires == [] and len(state["events"]) == 4


def test_une_alerte_par_rafale_puis_nouvelle_fenetre(auth001):
    first = burst(10, start=NOW - 29 * MIN, step=30_000)            # 10 échecs en 5 min
    second = burst(5, start=NOW - 15 * MIN, step=30_000)           # après la fin de la première fenêtre
    outcomes, fires, _ = run(auth001, first + second)
    assert outcomes[4] == "fired" and outcomes[5:10] == ["suppressed"] * 5
    assert len(fires) == 2
    ids = {engine.alert_id("AUTH-001", f["key"], str(f["window_start"])) for f in fires}
    assert len(ids) == 2


def test_identifiant_deterministe(auth001):
    evs = burst(5)
    _, a, _ = run(auth001, evs)
    _, b, _ = run(auth001, evs)
    assert a[0]["window_start"] == b[0]["window_start"] and a[0]["key"] == b[0]["key"]


def test_evenement_en_retard_non_compte(auth001):
    late = event(ts=NOW - 13 * MIN)        # fenêtre 10 min + tolérance 2 min dépassée
    assert engine.evaluate_window(auth001, late, None, NOW, 120).outcome == "late"
    ok = event(ts=NOW - 11 * MIN)
    assert engine.evaluate_window(auth001, ok, None, NOW, 120).outcome == "counted"


def test_source_rejouee_evaluee_sur_ses_dates(auth001):
    old = burst(5, start=BASE_MS - 400 * 24 * 60 * MIN, mode="rejeu")     # journaux d'il y a plus d'un an
    _, fires, _ = run(auth001, old)
    assert len(fires) == 1


def test_evenements_dans_le_desordre(auth001):
    evs = burst(5)
    _, fires, _ = run(auth001, [evs[4], evs[0], evs[3], evs[1], evs[2]])
    assert len(fires) == 1 and fires[0]["window_start"] == NOW - 9 * MIN


def test_champ_de_regroupement_absent(auth001):
    assert engine.evaluate_window(auth001, event(user=None), None, NOW, 120).outcome == "ignored"


def test_valeurs_distinctes(rule):
    scan = rule("id: NET-099\nname: Balayage\nseverity: moyenne\ntype: window\ncategory: [network]\n"
                "match: {event.category: network}\ngroup_by: [source.ip]\nwindow: 1m\nthreshold: 3\n"
                "distinct: destination.port\nmessage: '{count} ports'")
    same = [event(category="network", ts=NOW - 30_000 + i, destination__port=22) for i in range(5)]
    _, fires, _ = run(scan, same)
    assert fires == []
    ports = [event(category="network", ts=NOW - 30_000 + i, destination__port=p) for i, p in enumerate((22, 80, 443))]
    _, fires, _ = run(scan, ports)
    assert len(fires) == 1 and fires[0]["count"] == 3


FOLLOWED = ("id: AUTH-099\nname: Échecs puis succès\nseverity: critique\ntype: window\ncategory: [authentication]\n"
            "match: {event.category: authentication, event.outcome: failure}\n"
            "followed_by: {match: {event.category: authentication, event.outcome: success}}\n"
            "group_by: [user.name, source.ip]\nwindow: 10m\nthreshold: 3\nmessage: '{count} échecs puis succès'")


def test_echecs_suivis_d_un_succes(rule):
    r = rule(FOLLOWED)
    fails = burst(3)
    success = event(ts=NOW - 5 * MIN, outcome="success")
    outcomes, fires, state = run(r, fails + [success])
    assert outcomes == ["counted"] * 3 + ["fired"]
    assert fires[0]["count"] == 3 and fires[0]["events"][-1][0] == success["event"]["id"]
    # succès relivré : pas de seconde alerte
    assert engine.evaluate_window(r, success, state, NOW, 120).outcome in ("duplicate", "suppressed")


def test_succes_sans_assez_d_echecs(rule):
    r = rule(FOLLOWED)
    _, fires, _ = run(r, burst(2) + [event(ts=NOW - 5 * MIN, outcome="success")])
    assert fires == []
    assert engine.evaluate_window(r, event(ts=NOW, outcome="success"), None, NOW, 120).outcome == "ignored"


def test_regle_simple(validator):
    from conftest import RULES
    sys001 = validator.parse((RULES / "SYS-001.yml").read_text(encoding="utf-8"))
    encoded = event(category="process", outcome="success", event__code="4688",
                    process__command_line="powershell.exe -NoP -enc SQBFAFgA")
    normal = event(category="process", outcome="success", event__code="4688",
                   process__command_line="powershell.exe -File script.ps1")
    assert engine.evaluate_simple(sys001, encoded).outcome == "fired"
    assert engine.evaluate_simple(sys001, normal).outcome == "ignored"


# ── AUTH-002 : échecs puis succès (followed_by, règle du dépôt) ──────────────

def test_auth002_echecs_puis_succes(validator):
    from conftest import RULES
    r = validator.parse((RULES / "AUTH-002.yml").read_text(encoding="utf-8"))
    fails = burst(5)
    success = event(ts=NOW - 5 * MIN, outcome="success")
    outcomes, fires, state = run(r, fails + [success])
    assert outcomes[-1] == "fired" and len(fires) == 1
    assert fires[0]["count"] == 5


def test_auth002_succes_sans_assez_echecs(validator):
    from conftest import RULES
    r = validator.parse((RULES / "AUTH-002.yml").read_text(encoding="utf-8"))
    fails = burst(4)
    success = event(ts=NOW - 5 * MIN, outcome="success")
    _, fires, _ = run(r, fails + [success])
    assert fires == []


def test_auth002_succes_relivre_pas_de_doublon(validator):
    from conftest import RULES
    r = validator.parse((RULES / "AUTH-002.yml").read_text(encoding="utf-8"))
    fails = burst(5)
    success = event(ts=NOW - 5 * MIN, outcome="success")
    _, fires, state = run(r, fails + [success])
    assert len(fires) == 1
    d = engine.evaluate_window(r, success, state, NOW, 120)
    assert d.outcome in ("duplicate", "suppressed")


# ── AUTH-003 : password spraying (distinct sur user.name) ─────────────────────

def test_auth003_quatre_comptes_distincts_alerte(validator):
    from conftest import RULES
    r = validator.parse((RULES / "AUTH-003.yml").read_text(encoding="utf-8"))
    evs = [event(ts=NOW - 4 * MIN + i * 30_000, user=f"user{i}", ip="10.0.0.99",
                 host="srv-linux-01") for i in range(4)]
    _, fires, _ = run(r, evs)
    assert len(fires) == 1 and fires[0]["count"] == 4


def test_auth003_meme_compte_ne_compte_pas_plusieurs_fois(validator):
    from conftest import RULES
    r = validator.parse((RULES / "AUTH-003.yml").read_text(encoding="utf-8"))
    evs = [event(ts=NOW - 4 * MIN + i * 30_000, user="admin", ip="10.0.0.99",
                 host="srv-linux-01") for i in range(10)]
    _, fires, _ = run(r, evs)
    assert fires == []


# ── FW-001 : blocages pare-feu répétés ────────────────────────────────────────

def test_fw001_vingt_blocages_alerte(validator):
    from conftest import RULES
    r = validator.parse((RULES / "FW-001.yml").read_text(encoding="utf-8"))
    evs = [event(ts=NOW - 4 * MIN + i * 10_000, category="network", outcome="failure",
                 ip="192.168.1.100", user=None, host=None) for i in range(20)]
    _, fires, _ = run(r, evs)
    assert len(fires) == 1 and fires[0]["count"] == 20


def test_fw001_dix_neuf_blocages_pas_alerte(validator):
    from conftest import RULES
    r = validator.parse((RULES / "FW-001.yml").read_text(encoding="utf-8"))
    evs = [event(ts=NOW - 4 * MIN + i * 10_000, category="network", outcome="failure",
                 ip="192.168.1.100", user=None, host=None) for i in range(19)]
    _, fires, _ = run(r, evs)
    assert fires == []


# ── FW-002 : balayage de ports (distinct sur destination.port) ────────────────

def test_fw002_dix_ports_distincts_alerte(validator):
    from conftest import RULES
    r = validator.parse((RULES / "FW-002.yml").read_text(encoding="utf-8"))
    evs = [event(ts=NOW - 90_000 + i * 5_000, category="network", outcome="failure",
                 ip="10.0.0.50", user=None, host=None,
                 destination__port=p) for i, p in enumerate(range(22, 32))]
    _, fires, _ = run(r, evs)
    assert len(fires) == 1 and fires[0]["count"] == 10


def test_fw002_meme_port_ne_compte_pas(validator):
    from conftest import RULES
    r = validator.parse((RULES / "FW-002.yml").read_text(encoding="utf-8"))
    evs = [event(ts=NOW - 90_000 + i * 5_000, category="network", outcome="failure",
                 ip="10.0.0.50", user=None, host=None,
                 destination__port=22) for i in range(20)]
    _, fires, _ = run(r, evs)
    assert fires == []


# ── WEB-001 : force brute web (401/403) ──────────────────────────────────────

def test_web001_quinze_erreurs_403_alerte(validator):
    from conftest import RULES
    r = validator.parse((RULES / "WEB-001.yml").read_text(encoding="utf-8"))
    evs = [event(ts=NOW - 4 * MIN + i * 10_000, category="web", outcome="failure",
                 ip="172.16.0.10", user=None, host=None,
                 http__response__status_code=403) for i in range(15)]
    _, fires, _ = run(r, evs)
    assert len(fires) == 1


def test_web001_mix_401_403_alerte(validator):
    from conftest import RULES
    r = validator.parse((RULES / "WEB-001.yml").read_text(encoding="utf-8"))
    evs = []
    for i in range(15):
        code = 401 if i % 2 == 0 else 403
        evs.append(event(ts=NOW - 4 * MIN + i * 10_000, category="web", outcome="failure",
                         ip="172.16.0.10", user=None, host=None,
                         http__response__status_code=code))
    _, fires, _ = run(r, evs)
    assert len(fires) == 1


def test_web001_quatorze_pas_alerte(validator):
    from conftest import RULES
    r = validator.parse((RULES / "WEB-001.yml").read_text(encoding="utf-8"))
    evs = [event(ts=NOW - 4 * MIN + i * 10_000, category="web", outcome="failure",
                 ip="172.16.0.10", user=None, host=None,
                 http__response__status_code=401) for i in range(14)]
    _, fires, _ = run(r, evs)
    assert fires == []


# ── WEB-002 : scan de chemins (404) ──────────────────────────────────────────

def test_web002_trente_erreurs_404_alerte(validator):
    from conftest import RULES
    r = validator.parse((RULES / "WEB-002.yml").read_text(encoding="utf-8"))
    evs = [event(ts=NOW - 90_000 + i * 2_000, category="web", outcome="failure",
                 ip="172.16.0.20", user=None, host=None,
                 http__response__status_code=404) for i in range(30)]
    _, fires, _ = run(r, evs)
    assert len(fires) == 1 and fires[0]["count"] == 30


def test_web002_vingt_neuf_pas_alerte(validator):
    from conftest import RULES
    r = validator.parse((RULES / "WEB-002.yml").read_text(encoding="utf-8"))
    evs = [event(ts=NOW - 90_000 + i * 2_000, category="web", outcome="failure",
                 ip="172.16.0.20", user=None, host=None,
                 http__response__status_code=404) for i in range(29)]
    _, fires, _ = run(r, evs)
    assert fires == []
