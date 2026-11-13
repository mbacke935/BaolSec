"""État des alertes, commandes et consultation sur PostgreSQL réel (C15) — compte svc_incidents.

Nécessite TEST_POSTGRES_DSN : connexion administrateur au serveur PostgreSQL, par exemple
postgresql://postgres:<mot de passe>@localhost:5432/postgres (make test-incidents la construit depuis .env).
La base baolsec_incidents_test est créée puis supprimée ; la base baolsec n'est pas touchée.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

import psycopg
import pytest

from incidents_support import (ADMIN_DSN, alert_document, assign_command, command, rows, status_command, RESULT)

pytestmark = [pytest.mark.skipif(not ADMIN_DSN, reason="TEST_POSTGRES_DSN non défini"),
              pytest.mark.asyncio(loop_scope="function")]

from incidents.alert_state import parse_alert, rule_uuid                      # noqa: E402
from incidents.commands import CommandService, NotSupported                    # noqa: E402
from incidents.consumer import PostgresAlertSink                               # noqa: E402
from incidents.repositories import Database, DatabaseUnavailable, UnknownRule  # noqa: E402
from incidents.repositories import alerts as repo                              # noqa: E402


async def make_alert(db, **kw) -> str:
    doc = alert_document(**kw)
    assert await PostgresAlertSink(db).record(parse_alert(doc))
    return doc["event"]["id"]


async def state(db, alert_id):
    async with db.connection() as conn:
        return await repo.get_alert(conn, alert_id)


def valid(result: dict) -> dict:
    RESULT.validate(result)
    return result


# ------------------------------------------------------------------ création idempotente

async def test_le_service_tourne_sous_le_compte_svc_incidents(db):
    async with db.connection() as conn:
        assert (await (await conn.execute("SELECT current_user")).fetchone())[0] == "svc_incidents"


async def test_alerte_enregistree_nouvelle_sans_assigne(db):
    doc = alert_document(severity="critique")
    assert await PostgresAlertSink(db).record(parse_alert(doc)) is True
    row = await state(db, doc["event"]["id"])
    assert (row.status, row.assigned_to, row.severity) == ("nouvelle", None, "critique")
    assert row.rule_id == rule_uuid("AUTH-001")
    assert row.triggered_at == datetime.fromisoformat(doc["@timestamp"].replace("Z", "+00:00"))
    assert row.status_changed_at is not None and row.created_at is not None


async def test_meme_alerte_deux_fois_une_seule_ligne(db, database):
    doc = alert_document()
    sink = PostgresAlertSink(db)
    assert await sink.record(parse_alert(doc)) is True
    assert await sink.record(parse_alert(doc)) is False
    assert rows(database, "SELECT count(*) FROM incidents.alert_state WHERE alert_id = %s", (doc["event"]["id"],)) == [(1,)]


async def test_doublon_n_ecrase_pas_l_etat_de_traitement(db, database):
    analyst = new_analyst(database)
    doc = alert_document()
    sink = PostgresAlertSink(db)
    await sink.record(parse_alert(doc))
    await CommandService(db).apply(status_command(doc["event"]["id"], analyst, "en_cours"))
    assert await sink.record(parse_alert(doc)) is False            # republication de l'alerte
    row = await state(db, doc["event"]["id"])
    assert (row.status, row.assigned_to) == ("en_cours", analyst)


async def test_regle_inconnue_leve_unknown_rule_et_la_connexion_reste_utilisable(db):
    doc = alert_document(rule="ZZZ-999")
    with pytest.raises(UnknownRule, match="ZZZ-999"):
        await PostgresAlertSink(db).record(parse_alert(doc))
    assert await make_alert(db)                                   # la transaction annulée n'a rien bloqué
    assert await state(db, doc["event"]["id"]) is None


# ------------------------------------------------------------------ commandes

def new_analyst(database, *, active=True) -> uuid.UUID:
    from incidents_support import new_user
    return new_user(database, active=active)


async def test_prise_en_charge_enregistre_l_etat_et_la_commande(db, database):
    ana, aid = new_analyst(database), await make_alert(db)
    cmd = status_command(aid, ana, "en_cours")
    r = valid(await CommandService(db).apply(cmd))
    assert (r["result"], r["replayed"], "error" in r) == ("acceptee", False, False)
    row = await state(db, aid)
    assert (row.status, row.assigned_to) == ("en_cours", ana) and row.status_changed_at > row.created_at
    [(ctype, alert, issuer, payload, result, error)] = rows(
        database, "SELECT command_type::text, alert_id, issued_by, payload, result::text, error FROM incidents.incident_commands "
                  "WHERE command_id = %s", (cmd["command_id"],))
    assert (ctype, alert, issuer, payload, result, error) == ("statut_alerte", aid, ana, {"status": "en_cours"}, "acceptee", None)


async def test_commande_rejouee_renvoie_le_meme_resultat_sans_reappliquer(db, database):
    ana, aid, svc = new_analyst(database), await make_alert(db), None
    svc = CommandService(db)
    first = status_command(aid, ana, "en_cours")
    r1 = valid(await svc.apply(first))
    assert (await svc.apply(status_command(aid, ana, "cloturee")))["result"] == "acceptee"
    r2 = valid(await svc.apply(first))                              # rejeu de la première commande
    assert r2["replayed"] is True and r2["result"] == "acceptee" and r2["completed_at"] == r1["completed_at"]
    assert (await state(db, aid)).status == "cloturee"              # l'état n'est pas revenu à « en_cours »
    assert rows(database, "SELECT count(*) FROM incidents.incident_commands WHERE alert_id = %s", (aid,)) == [(2,)]


async def test_refus_enregistre_et_rejoue_a_l_identique(db, database):
    ana, aid, svc = new_analyst(database), await make_alert(db), None
    svc = CommandService(db)
    cmd = status_command(aid, ana, "nouvelle")                      # déjà « nouvelle »
    r1 = valid(await svc.apply(cmd))
    assert r1["result"] == "refusee" and r1["error"]["code"] == "transition_interdite" and r1["replayed"] is False
    r2 = valid(await svc.apply(cmd))
    assert r2["replayed"] is True and r2["error"] == r1["error"] and r2["completed_at"] == r1["completed_at"]
    assert rows(database, "SELECT result::text FROM incidents.incident_commands WHERE command_id = %s",
                (cmd["command_id"],)) == [("refusee",)]


async def test_command_id_reutilise_pour_une_autre_commande_est_refuse(db, database):
    ana, aid = new_analyst(database), await make_alert(db)
    svc, cid = CommandService(db), uuid.uuid4()
    await svc.apply(status_command(aid, ana, "en_cours", cid))
    r = valid(await svc.apply(status_command(aid, ana, "cloturee", cid)))
    assert r["result"] == "refusee" and r["error"]["code"] == "donnees_invalides" and r["replayed"] is False
    assert (await state(db, aid)).status == "en_cours"
    assert rows(database, "SELECT payload FROM incidents.incident_commands WHERE command_id = %s", (cid,)) == [({"status": "en_cours"},)]


async def test_alerte_inconnue_refusee_et_non_enregistree(db, database):
    ana = new_analyst(database)
    cmd = status_command("0" * 64, ana, "en_cours")
    r = valid(await CommandService(db).apply(cmd))
    assert r["result"] == "refusee" and r["error"]["code"] == "cible_introuvable"
    assert rows(database, "SELECT count(*) FROM incidents.incident_commands WHERE command_id = %s", (cmd["command_id"],)) == [(0,)]


@pytest.mark.parametrize("issuer_kind", ["inconnu", "desactive"])
async def test_auteur_inconnu_ou_desactive_refuse_sans_modifier_l_alerte(db, database, issuer_kind):
    issuer = uuid.uuid4() if issuer_kind == "inconnu" else new_analyst(database, active=False)
    aid = await make_alert(db)
    cmd = status_command(aid, issuer, "en_cours")
    r = valid(await CommandService(db).apply(cmd))
    assert r["result"] == "refusee" and r["error"]["code"] == "donnees_invalides"
    assert (await state(db, aid)).status == "nouvelle"
    assert rows(database, "SELECT count(*) FROM incidents.incident_commands WHERE command_id = %s", (cmd["command_id"],)) == [(0,)]


async def test_assigner_une_alerte_nouvelle_puis_retirer_l_assigne(db, database):
    ana, bob, aid = new_analyst(database), new_analyst(database), await make_alert(db)
    svc = CommandService(db)
    assert valid(await svc.apply(assign_command(aid, ana, bob)))["result"] == "acceptee"
    row = await state(db, aid)
    assert (row.status, row.assigned_to) == ("en_cours", bob)
    assert valid(await svc.apply(assign_command(aid, ana, None)))["result"] == "acceptee"
    row = await state(db, aid)
    assert (row.status, row.assigned_to) == ("nouvelle", None)


@pytest.mark.parametrize("kind,code", [("inconnu", "donnees_invalides"), ("desactive", "donnees_invalides")])
async def test_assigner_un_analyste_inconnu_ou_desactive_refuse_et_enregistre(db, database, kind, code):
    ana, aid = new_analyst(database), await make_alert(db)
    assignee = uuid.uuid4() if kind == "inconnu" else new_analyst(database, active=False)
    cmd = assign_command(aid, ana, assignee)
    r = valid(await CommandService(db).apply(cmd))
    assert r["result"] == "refusee" and r["error"]["code"] == code
    assert (await state(db, aid)).status == "nouvelle"
    assert rows(database, "SELECT result::text FROM incidents.incident_commands WHERE command_id = %s",
                (cmd["command_id"],)) == [("refusee",)]


async def test_alerte_cloturee_non_assignable_puis_reouverte(db, database):
    ana, bob, aid = new_analyst(database), new_analyst(database), await make_alert(db)
    svc = CommandService(db)
    await svc.apply(status_command(aid, ana, "en_cours"))
    await svc.apply(status_command(aid, ana, "cloturee"))
    r = valid(await svc.apply(assign_command(aid, bob, bob)))
    assert r["result"] == "refusee" and "rouvrir" in r["error"]["message"]
    assert valid(await svc.apply(status_command(aid, bob, "en_cours")))["result"] == "acceptee"
    row = await state(db, aid)
    assert (row.status, row.assigned_to) == ("en_cours", bob)


async def test_commande_d_incident_non_prise_en_charge(db, database):
    cmd = command("clore", "x", uuid.uuid4(), {})
    cmd["target"] = {"incident_id": str(uuid.uuid4())}
    with pytest.raises(NotSupported, match="C16"):
        await CommandService(db).apply(cmd)


async def test_deux_analystes_agissent_en_meme_temps_un_seul_gagne(db, database):
    ana, bob, aid = new_analyst(database), new_analyst(database), await make_alert(db)
    svc = CommandService(db)
    results = await asyncio.gather(svc.apply(status_command(aid, ana, "en_cours")),
                                   svc.apply(status_command(aid, bob, "en_cours")))
    for r in results:
        valid(r)
    assert sorted(r["result"] for r in results) == ["acceptee", "refusee"]
    winner = ana if results[0]["result"] == "acceptee" else bob
    row = await state(db, aid)
    assert (row.status, row.assigned_to) == ("en_cours", winner)
    assert rows(database, "SELECT count(*) FROM incidents.incident_commands WHERE alert_id = %s", (aid,)) == [(2,)]


async def test_meme_commande_envoyee_cinq_fois_en_parallele_appliquee_une_fois(db, database):
    ana, aid = new_analyst(database), await make_alert(db)
    cmd = status_command(aid, ana, "en_cours")
    svc = CommandService(db)
    results = await asyncio.gather(*(svc.apply(cmd) for _ in range(5)))
    assert all(valid(r)["result"] == "acceptee" for r in results)
    assert sorted(r["replayed"] for r in results) == [False, True, True, True, True]
    assert len({r["completed_at"] for r in results}) == 1
    assert rows(database, "SELECT count(*) FROM incidents.incident_commands WHERE alert_id = %s", (aid,)) == [(1,)]


async def test_le_compte_du_service_n_a_pas_plus_de_droits_que_necessaire(db):
    async with db.connection() as conn:
        for sql in ("DELETE FROM incidents.alert_state", "UPDATE acces.users SET is_active = false",
                    "SELECT password_hash FROM acces.users", "INSERT INTO config.settings (key, value) VALUES ('x', '1')"):
            with pytest.raises(Exception, match="permission denied"):
                async with conn.transaction():
                    await conn.execute(sql)


# ------------------------------------------------------------------ consultation

def purge_2030(database) -> None:
    """Supprime (compte administrateur) les alertes de test datées de 2030 : chaque test repart de six alertes connues."""
    period = "triggered_at >= '2030-01-01' AND triggered_at < '2031-01-01'"
    with psycopg.connect(database) as c:
        c.execute(f"DELETE FROM incidents.incident_commands WHERE alert_id IN (SELECT alert_id FROM incidents.alert_state WHERE {period})")
        c.execute(f"DELETE FROM incidents.alert_state WHERE {period}")


@pytest.fixture
async def seeded(db, database):
    """Alertes réparties sur 2 règles, 3 sévérités et 3 statuts, datées du 5 janvier 2030."""
    purge_2030(database)
    ana = new_analyst(database)
    svc = CommandService(db)
    spec = [("AUTH-001", "critique", "2030-01-05T10:00:00Z", None), ("AUTH-001", "elevee", "2030-01-05T11:00:00Z", "en_cours"),
            ("AUTH-001", "elevee", "2030-01-05T12:00:00Z", "cloturee"), ("SYS-001", "moyenne", "2030-01-05T13:00:00Z", None),
            ("SYS-001", "critique", "2030-01-05T14:00:00Z", "en_cours"), ("SYS-001", "faible", "2030-01-05T15:00:00Z", None)]
    ids = []
    for rule, severity, at, target in spec:
        aid = await make_alert(db, rule=rule, severity=severity, at=at)
        if target:
            await svc.apply(status_command(aid, ana, "en_cours"))
            if target == "cloturee":
                await svc.apply(status_command(aid, ana, "cloturee"))
        ids.append(aid)
    yield ana, ids
    purge_2030(database)


JAN5 = dict(triggered_from=datetime(2030, 1, 5, tzinfo=timezone.utc), triggered_to=datetime(2030, 1, 6, tzinfo=timezone.utc))


async def listing(db, **filters) -> repo.Page:
    async with db.connection() as conn:
        return await repo.list_alerts(conn, repo.AlertFilter(**JAN5, **filters), size=100)


async def test_consultation_les_plus_recentes_d_abord(db, seeded):
    _, ids = seeded
    page = await listing(db)
    assert [a.alert_id for a in page.items] == list(reversed(ids)) and page.total == 6


@pytest.mark.parametrize("filters,expected", [
    (dict(status="nouvelle"), [0, 3, 5]), (dict(status="en_cours"), [1, 4]), (dict(status="cloturee"), [2]),
    (dict(severity="critique"), [0, 4]), (dict(rule_code="SYS-001"), [3, 4, 5]),
    (dict(rule_code="AUTH-001", severity="elevee"), [1, 2]), (dict(status="nouvelle", severity="critique"), [0]), (dict(status="cloturee", severity="critique"), []),
])
async def test_consultation_par_statut_regle_et_severite(db, seeded, filters, expected):
    _, ids = seeded
    page = await listing(db, **filters)
    assert sorted(a.alert_id for a in page.items) == sorted(ids[i] for i in expected) and page.total == len(expected)


async def test_consultation_par_assigne_et_par_date(db, seeded):
    ana, ids = seeded
    assert {a.alert_id for a in (await listing(db, assigned_to=ana)).items} == {ids[1], ids[2], ids[4]}
    async with db.connection() as conn:
        page = await repo.list_alerts(conn, repo.AlertFilter(
            triggered_from=datetime(2030, 1, 5, 11, tzinfo=timezone.utc), triggered_to=datetime(2030, 1, 5, 13, tzinfo=timezone.utc)))
    assert [a.alert_id for a in page.items] == [ids[3], ids[2], ids[1]]       # bornes incluses


async def test_pagination_et_limites(db, seeded):
    _, ids = seeded
    async with db.connection() as conn:
        f = repo.AlertFilter(**JAN5)
        p1 = await repo.list_alerts(conn, f, page=1, size=4)
        p2 = await repo.list_alerts(conn, f, page=2, size=4)
        assert (len(p1.items), len(p2.items), p1.total, p2.total) == (4, 2, 6, 6)
        assert [a.alert_id for a in p1.items + p2.items] == list(reversed(ids))
        for bad in (dict(page=0), dict(size=0), dict(size=101)):
            with pytest.raises(ValueError):
                await repo.list_alerts(conn, f, **bad)
        with pytest.raises(ValueError, match="statut"):
            await repo.list_alerts(conn, repo.AlertFilter(status="terminee"))


async def test_compteurs_du_tableau_de_bord(db, seeded):
    async with db.connection() as conn:
        c = await repo.count_alerts(conn)
    assert set(c["by_status"]) == {"nouvelle", "en_cours", "cloturee"} and set(c["by_severity"]) == {"faible", "moyenne", "elevee", "critique"}
    assert sum(c["by_status"].values()) == sum(c["by_severity"].values()) == c["total"]
    assert c["total"] >= 6 and c["open_by_severity"]["elevee"] <= c["by_severity"]["elevee"]
    assert all(c["open_by_severity"][s] <= c["by_severity"][s] for s in c["by_severity"])


# ------------------------------------------------------------------ indisponibilité de la base

async def test_base_injoignable_signalee_sans_bloquer_le_service():
    pool = Database("postgresql://svc_incidents@127.0.0.1:1/baolsec", max_size=1, timeout_s=0.5)
    await pool.open()
    try:
        assert await pool.ping() is False
        with pytest.raises(DatabaseUnavailable):
            await PostgresAlertSink(pool).record(parse_alert(alert_document()))
    finally:
        await pool.close()
