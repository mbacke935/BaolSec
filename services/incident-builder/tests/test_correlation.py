"""Tests unitaires du moteur de corrélation (C16, C3 §3.8).

Couvre :
- Extraction d'entités (valeurs génériques filtrées)
- R1 à R4 (règles de rattachement)
- E1 à E5 (exclusions)
- Cas 1 à 4 (C3 table 9)
- D5 : attaque enchaînée multi-sources → un seul incident
- D6 : même IP, cibles et comptes différents → deux incidents distincts
- max_severity, incident_title
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from incidents.correlation import (
    DEFAULT_WINDOW_MINUTES,
    CandidateIncident,
    CorrelationDecision,
    Entities,
    IncidentContext,
    MatchResult,
    correlate,
    extract_entities,
    incident_title,
    match_alert_to_incident,
    max_severity,
)

T0 = datetime(2025, 6, 15, 10, 0, 0, tzinfo=timezone.utc)


def _ctx(**kw) -> IncidentContext:
    return IncidentContext(
        users=frozenset(kw.get("users", [])),
        source_ips=frozenset(kw.get("ips", [])),
        hosts=frozenset(kw.get("hosts", [])),
        activity_families=frozenset(kw.get("families", [])),
    )


def _candidate(
    ctx: IncidentContext,
    last_activity: datetime = T0,
    opened: datetime | None = None,
    status: str = "ouvert",
    severity: str = "moyenne",
) -> CandidateIncident:
    return CandidateIncident(
        incident_id=uuid.uuid4(),
        context=ctx,
        last_activity_at=last_activity,
        opened_at=opened or last_activity,
        status=status,
        severity=severity,
    )


# ================================================================ extract_entities

class TestExtractEntities:
    def test_nominal(self):
        doc = {
            "user": {"name": "Admin"},
            "source": {"ip": "10.0.4.23"},
            "host": {"name": "PC-WIN-COMPTA"},
            "event": {"category": ["authentication"]},
        }
        e = extract_entities(doc)
        assert e.user == "admin"          # lowercase
        assert e.source_ip == "10.0.4.23"
        assert e.host == "pc-win-compta"  # lowercase
        assert e.categories == ("authentication",)

    def test_generic_values_filtered(self):
        doc = {
            "user": {"name": "SYSTEM"},
            "source": {"ip": "N/A"},
            "host": {"name": "—"},
            "event": {"category": []},
        }
        e = extract_entities(doc)
        assert e.user is None
        assert e.source_ip is None
        assert e.host is None

    def test_empty_doc(self):
        e = extract_entities({})
        assert e.user is None
        assert e.source_ip is None
        assert e.host is None
        assert e.categories == ()

    def test_activity_family(self):
        e = Entities(categories=("authentication",))
        assert e.activity_family == "authentication"
        e2 = Entities(categories=("web", "process"))
        assert e2.activity_family == "web"
        e3 = Entities(categories=())
        assert e3.activity_family is None


# ================================================================ IncidentContext

class TestIncidentContext:
    def test_to_dict_from_dict(self):
        ctx = _ctx(users=["admin"], ips=["10.0.4.23"], hosts=["pc-01"], families=["authentication"])
        d = ctx.to_dict()
        assert d == {
            "users": ["admin"],
            "source_ips": ["10.0.4.23"],
            "hosts": ["pc-01"],
            "activity_families": ["authentication"],
        }
        ctx2 = IncidentContext.from_dict(d)
        assert ctx2 == ctx

    def test_merge(self):
        ctx = _ctx(users=["admin"], ips=["10.0.4.23"])
        e = Entities(user="admin", source_ip="10.0.8.31", host="srv-01", categories=("network",))
        merged = ctx.merge(e)
        assert "admin" in merged.users
        assert "10.0.4.23" in merged.source_ips
        assert "10.0.8.31" in merged.source_ips
        assert "srv-01" in merged.hosts
        assert "network" in merged.activity_families

    def test_from_entities(self):
        e = Entities(user="admin", source_ip="10.0.4.23")
        ctx = IncidentContext.from_entities(e)
        assert ctx.users == frozenset({"admin"})
        assert ctx.source_ips == frozenset({"10.0.4.23"})


# ================================================================ match_alert_to_incident

class TestMatch:
    # --- R1 : même utilisateur + même IP source ---
    def test_r1(self):
        ctx = _ctx(users=["admin"], ips=["10.0.4.23"], hosts=["pc-01"])
        c = _candidate(ctx, last_activity=T0)
        e = Entities(user="admin", source_ip="10.0.4.23")
        r = match_alert_to_incident(e, c, "AUTH-001", now=T0 + timedelta(seconds=37))
        assert r.rule == "R1"
        assert r.common_entities == {"user": "admin", "source_ip": "10.0.4.23"}

    # --- R2 : même utilisateur + même hôte ---
    def test_r2(self):
        ctx = _ctx(users=["admin"], hosts=["pc-win-compta"])
        c = _candidate(ctx, last_activity=T0)
        e = Entities(user="admin", host="pc-win-compta", categories=("process",))
        r = match_alert_to_incident(e, c, "SYS-001", now=T0 + timedelta(minutes=15))
        assert r.rule == "R2"
        assert r.common_entities == {"user": "admin", "host": "pc-win-compta"}

    # --- R3 : même IP + même hôte ---
    def test_r3(self):
        ctx = _ctx(ips=["10.0.8.31"], hosts=["srv-linux-01"])
        c = _candidate(ctx, last_activity=T0)
        e = Entities(source_ip="10.0.8.31", host="srv-linux-01")
        r = match_alert_to_incident(e, c, "FW-001", now=T0 + timedelta(minutes=5))
        assert r.rule == "R3"

    # --- R4 : même utilisateur + activités enchaînées ---
    def test_r4_auth_to_process(self):
        ctx = _ctx(users=["svc-admin"], families=["authentication"])
        c = _candidate(ctx, last_activity=T0)
        e = Entities(user="svc-admin", categories=("process",))
        r = match_alert_to_incident(e, c, "SYS-001", now=T0 + timedelta(minutes=10))
        assert r.rule == "R4"
        assert "activity_chain" in r.common_entities

    def test_r4_web_to_host(self):
        ctx = _ctx(users=["dev"], families=["web"])
        c = _candidate(ctx, last_activity=T0)
        e = Entities(user="dev", categories=("host",))
        r = match_alert_to_incident(e, c, "SYS-001", now=T0 + timedelta(minutes=5))
        assert r.rule == "R4"

    def test_r4_no_chain(self):
        """Web → web n'est pas un enchaînement autorisé → pas de R4."""
        ctx = _ctx(users=["dev"], families=["web"])
        c = _candidate(ctx, last_activity=T0)
        e = Entities(user="dev", categories=("web",))
        r = match_alert_to_incident(e, c, "WEB-001", now=T0 + timedelta(minutes=5))
        # user seul sans chaîne valide → E1
        assert r.rule is None

    # --- E1 : IP seule ---
    def test_e1(self):
        ctx = _ctx(ips=["10.0.8.31"], hosts=["web-portal"])
        c = _candidate(ctx, last_activity=T0)
        e = Entities(source_ip="10.0.8.31", host="srv-linux-01")  # hôtes différents
        r = match_alert_to_incident(e, c, "FW-001", now=T0 + timedelta(minutes=10))
        assert r.rule is None
        assert r.exclusion == "E1"

    # --- E2 : hôte seul ---
    def test_e2(self):
        ctx = _ctx(hosts=["srv-linux-01"])
        c = _candidate(ctx, last_activity=T0)
        e = Entities(host="srv-linux-01")
        r = match_alert_to_incident(e, c, "SYS-001", now=T0 + timedelta(minutes=5))
        assert r.rule is None
        assert r.exclusion == "E2"

    # --- E3 : aucune entité commune ---
    def test_e3(self):
        ctx = _ctx(users=["alice"], ips=["192.168.1.1"])
        c = _candidate(ctx, last_activity=T0)
        e = Entities(user="bob", source_ip="10.0.0.1")
        r = match_alert_to_incident(e, c, "AUTH-001", now=T0 + timedelta(minutes=5))
        assert r.rule is None
        assert r.exclusion == "E3"

    # --- E4 : fenêtre dépassée ---
    def test_e4_window(self):
        ctx = _ctx(users=["admin"], ips=["10.0.4.23"])
        c = _candidate(ctx, last_activity=T0)
        e = Entities(user="admin", source_ip="10.0.4.23")
        r = match_alert_to_incident(e, c, "AUTH-001", now=T0 + timedelta(minutes=45))
        assert r.rule is None
        assert r.exclusion == "E4"

    def test_e4_max_duration(self):
        """Incident ouvert depuis plus de 24 h → E4 même si dernière activité récente."""
        ctx = _ctx(users=["admin"], ips=["10.0.4.23"])
        opened = T0 - timedelta(hours=25)
        c = _candidate(ctx, last_activity=T0, opened=opened)
        e = Entities(user="admin", source_ip="10.0.4.23")
        r = match_alert_to_incident(e, c, "AUTH-001", now=T0 + timedelta(minutes=5))
        assert r.rule is None
        assert r.exclusion == "E4"

    # --- E5 : incident clos ---
    def test_e5(self):
        ctx = _ctx(users=["admin"], ips=["10.0.4.23"])
        c = _candidate(ctx, last_activity=T0, status="clos")
        e = Entities(user="admin", source_ip="10.0.4.23")
        r = match_alert_to_incident(e, c, "AUTH-001", now=T0 + timedelta(minutes=5))
        assert r.rule is None
        assert r.exclusion == "E5"


# ================================================================ correlate (décision globale)

class TestCorrelate:
    def test_create_when_no_candidates(self):
        e = Entities(user="admin", source_ip="10.0.4.23")
        d = correlate(e, "AUTH-001", "critique", T0, [])
        assert d.action == "create"
        assert d.incident_id is not None
        assert d.rule is None

    def test_attach_best_candidate(self):
        """Quand deux candidats matchent, celui avec le plus d'entités gagne."""
        c1 = _candidate(_ctx(users=["admin"]), last_activity=T0)
        c2 = _candidate(_ctx(users=["admin"], ips=["10.0.4.23"]), last_activity=T0)
        e = Entities(user="admin", source_ip="10.0.4.23")
        d = correlate(e, "AUTH-001", "critique", T0 + timedelta(seconds=37), [c1, c2])
        assert d.action == "attach"
        assert d.incident_id == c2.incident_id
        assert d.rule == "R1"

    def test_attach_most_recent_on_tie(self):
        """À entités égales, le plus récent gagne."""
        c1 = _candidate(_ctx(users=["admin"], ips=["10.0.4.23"]),
                         last_activity=T0 - timedelta(minutes=5))
        c2 = _candidate(_ctx(users=["admin"], ips=["10.0.4.23"]),
                         last_activity=T0)
        e = Entities(user="admin", source_ip="10.0.4.23")
        d = correlate(e, "AUTH-001", "critique", T0 + timedelta(seconds=10), [c1, c2])
        assert d.action == "attach"
        assert d.incident_id == c2.incident_id

    def test_create_when_all_excluded(self):
        """Tous les candidats écartés → création."""
        c1 = _candidate(_ctx(ips=["10.0.8.31"], hosts=["web-portal"]),
                         last_activity=T0)
        e = Entities(source_ip="10.0.8.31", host="srv-linux-01")
        d = correlate(e, "FW-001", "moyenne", T0 + timedelta(minutes=10), [c1])
        assert d.action == "create"


# ================================================================ cas de test C3 table 9

class TestCasC3:
    def test_cas1_r1(self):
        """Force brute admin/10.0.4.23/PC-WIN-COMPTA + 37s connexion réussie admin/10.0.4.23 → R1."""
        ctx = _ctx(users=["admin"], ips=["10.0.4.23"], hosts=["pc-win-compta"], families=["authentication"])
        c = _candidate(ctx, last_activity=T0, severity="critique")
        e = Entities(user="admin", source_ip="10.0.4.23", categories=("authentication",))
        d = correlate(e, "AUTH-002", "elevee", T0 + timedelta(seconds=37), [c])
        assert d.action == "attach"
        assert d.rule == "R1"
        assert d.incident_id == c.incident_id

    def test_cas2_e1(self):
        """Web 10.0.8.31/WEB-PORTAL + 10min SSH 10.0.8.31/SRV-LINUX-01 → E1 (IP seule, hôtes différents)."""
        ctx = _ctx(ips=["10.0.8.31"], hosts=["web-portal"], families=["web"])
        c = _candidate(ctx, last_activity=T0)
        e = Entities(source_ip="10.0.8.31", host="srv-linux-01", categories=("network",))
        d = correlate(e, "FW-001", "moyenne", T0 + timedelta(minutes=10), [c])
        assert d.action == "create"

    def test_cas3_r2(self):
        """Force brute admin/PC-WIN-COMPTA + 15min PowerShell admin/PC-WIN-COMPTA → R2."""
        ctx = _ctx(users=["admin"], hosts=["pc-win-compta"], families=["authentication"])
        c = _candidate(ctx, last_activity=T0, severity="critique")
        e = Entities(user="admin", host="pc-win-compta", categories=("process",))
        d = correlate(e, "SYS-001", "elevee", T0 + timedelta(minutes=15), [c])
        assert d.action == "attach"
        assert d.rule == "R2"

    def test_cas4_e4(self):
        """Même que cas 1, mais 45 min → E4 (fenêtre dépassée)."""
        ctx = _ctx(users=["admin"], ips=["10.0.4.23"], hosts=["pc-win-compta"], families=["authentication"])
        c = _candidate(ctx, last_activity=T0, severity="critique")
        e = Entities(user="admin", source_ip="10.0.4.23", categories=("authentication",))
        d = correlate(e, "AUTH-002", "elevee", T0 + timedelta(minutes=45), [c])
        assert d.action == "create"


# ================================================================ D5 et D6

class TestDemonstrations:
    def test_d5_chained_attack_one_incident(self):
        """D5 : attaque enchaînée multi-sources → un seul incident, chaque rattachement montre sa règle."""
        # 1. Première alerte : force brute admin/10.0.4.23/PC-WIN-COMPTA
        e1 = Entities(user="admin", source_ip="10.0.4.23", host="pc-win-compta", categories=("authentication",))
        d1 = correlate(e1, "AUTH-001", "critique", T0, [])
        assert d1.action == "create"

        # 2. Seconde alerte : connexion réussie admin/10.0.4.23 → R1
        c = _candidate(d1.new_context, last_activity=T0, opened=T0, severity="critique")
        c = CandidateIncident(incident_id=d1.incident_id, context=d1.new_context,
                               last_activity_at=T0, opened_at=T0, status="ouvert", severity="critique")
        e2 = Entities(user="admin", source_ip="10.0.4.23", categories=("authentication",))
        d2 = correlate(e2, "AUTH-002", "elevee", T0 + timedelta(seconds=37), [c])
        assert d2.action == "attach"
        assert d2.incident_id == d1.incident_id
        assert d2.rule == "R1"

        # 3. Troisième : PowerShell admin/PC-WIN-COMPTA → R2
        ctx3 = d2.new_context
        c3 = CandidateIncident(incident_id=d1.incident_id, context=ctx3,
                                last_activity_at=T0 + timedelta(seconds=37), opened_at=T0,
                                status="ouvert", severity="critique")
        e3 = Entities(user="admin", host="pc-win-compta", categories=("process",))
        d3 = correlate(e3, "SYS-001", "elevee", T0 + timedelta(minutes=5), [c3])
        assert d3.action == "attach"
        assert d3.incident_id == d1.incident_id
        assert d3.rule == "R2"

    def test_d6_same_ip_different_targets(self):
        """D6 : même IP, cibles et comptes différents → deux incidents distincts (E1)."""
        # Incident 1 : alice/10.0.8.31/SRV-A
        e1 = Entities(user="alice", source_ip="10.0.8.31", host="srv-a", categories=("authentication",))
        d1 = correlate(e1, "AUTH-001", "elevee", T0, [])
        assert d1.action == "create"

        # Alerte 2 : bob/10.0.8.31/SRV-B → seule l'IP est commune → E1 → nouvel incident
        c1 = CandidateIncident(incident_id=d1.incident_id, context=d1.new_context,
                                last_activity_at=T0, opened_at=T0, status="ouvert", severity="elevee")
        e2 = Entities(user="bob", source_ip="10.0.8.31", host="srv-b", categories=("authentication",))
        d2 = correlate(e2, "AUTH-001", "elevee", T0 + timedelta(minutes=5), [c1])
        assert d2.action == "create"
        assert d2.incident_id != d1.incident_id


# ================================================================ helpers

class TestHelpers:
    def test_max_severity(self):
        assert max_severity("faible", "critique") == "critique"
        assert max_severity("critique", "faible") == "critique"
        assert max_severity("moyenne", "elevee") == "elevee"
        assert max_severity("elevee", "elevee") == "elevee"

    def test_incident_title(self):
        e = Entities(user="admin", source_ip="10.0.4.23", host="pc-win-compta")
        t = incident_title(e, "AUTH-001")
        assert "AUTH-001" in t
        assert "admin" in t
        assert "10.0.4.23" in t

    def test_incident_title_ip_only(self):
        e = Entities(source_ip="10.0.8.31")
        t = incident_title(e, "FW-001")
        assert "FW-001" in t
        assert "10.0.8.31" in t
