"""Commandes sur les incidents (C16, C5 §6) sur PostgreSQL réel — compte svc_incidents.

Ajouté lors de l'audit du 26/11/2026 : aucune commande d'incident n'était testée, et toutes
échouaient en production (insert_incident_command et add_comment absents ; réouverture refusée
par la contrainte « clos ⇔ closed_at »). Nécessite TEST_POSTGRES_DSN, comme test_alert_state.py.
"""
from __future__ import annotations

import uuid

import pytest

from incidents_support import ADMIN_DSN, RESULT, rows

pytestmark = [pytest.mark.skipif(not ADMIN_DSN, reason="TEST_POSTGRES_DSN non défini"),
              pytest.mark.asyncio(loop_scope="function")]

from incidents.commands import CommandService  # noqa: E402


def new_analyst(url: str) -> uuid.UUID:
    import psycopg
    uid = uuid.uuid4()
    with psycopg.connect(url) as c:
        c.execute("INSERT INTO acces.users (id, username, password_hash, role_id) "
                  "SELECT %s, %s, 'x', id FROM acces.roles WHERE name = 'Analyste'", (uid, f"ana-{uid.hex[:6]}"))
    return uid


def new_incident(url: str, status: str = "ouvert") -> uuid.UUID:
    import psycopg
    iid = uuid.uuid4()
    with psycopg.connect(url) as c:
        c.execute(
            "INSERT INTO incidents.incidents (id, title, status, severity, correlation_context, opened_at, "
            "last_activity_at, closed_at) VALUES (%s, 'Incident de test', %s, 'elevee', '{}', now(), now(), "
            "CASE WHEN %s = 'clos' THEN now() END)", (iid, status, status))
    return iid


def cmd(ctype: str, incident_id: uuid.UUID, issuer: uuid.UUID, payload: dict, command_id: uuid.UUID | None = None) -> dict:
    return {"contract": "incident_command/v1", "command_id": str(command_id or uuid.uuid4()), "command_type": ctype,
            "target": {"incident_id": str(incident_id)}, "issued_by": {"user_id": str(issuer), "username": "ana"},
            "issued_at": "2026-11-26T10:00:00Z", "payload": payload}


def ok(result: dict) -> dict:
    RESULT.validate(result)
    return result


def status_of(url: str, iid) -> tuple:
    return rows(url, "SELECT status::text, closed_at IS NOT NULL, assigned_to FROM incidents.incidents WHERE id = %s",
                (iid,))[0]


async def test_parcours_complet_d_un_incident(db, database):
    ana, iid = new_analyst(database), new_incident(database)
    svc = CommandService(db)

    assert ok(await svc.apply(cmd("changer_statut", iid, ana, {"status": "en_cours"})))["result"] == "acceptee"
    assert ok(await svc.apply(cmd("commenter", iid, ana, {"body": "Analyse en cours <b>x</b>"})))["result"] == "acceptee"
    assert ok(await svc.apply(cmd("assigner", iid, ana, {"assignee_id": str(ana)})))["result"] == "acceptee"
    assert status_of(database, iid) == ("en_cours", False, ana)

    assert ok(await svc.apply(cmd("clore", iid, ana, {"reason": "traité"})))["result"] == "acceptee"
    assert status_of(database, iid)[:2] == ("clos", True)

    # Réouverture : closed_at doit être effacé (contrainte incidents_check)
    assert ok(await svc.apply(cmd("rouvrir", iid, ana, {})))["result"] == "acceptee"
    assert status_of(database, iid)[:2] == ("en_cours", False)

    comments = rows(database, "SELECT body, author_id FROM incidents.incident_comments WHERE incident_id = %s", (iid,))
    assert comments == [("Analyse en cours <b>x</b>", ana)]
    timeline = rows(database, "SELECT entry_type::text, summary, justification FROM incidents.incident_timeline "
                              "WHERE incident_id = %s ORDER BY id", (iid,))
    assert [t[0] for t in timeline] == ["status_change", "comment", "status_change", "status_change", "status_change"]
    assert timeline[1][2]["body"] == "Analyse en cours <b>x</b>"          # commentaire visible dans la chronologie
    assert timeline[2][1].startswith("Assigné à ana-")                    # nom lisible, pas un UUID
    commands = rows(database, "SELECT command_type::text, result::text FROM incidents.incident_commands "
                              "WHERE incident_id = %s ORDER BY created_at", (iid,))
    assert [c[0] for c in commands] == ["changer_statut", "commenter", "assigner", "clore", "rouvrir"]
    assert {c[1] for c in commands} == {"acceptee"}
    outbox = rows(database, "SELECT count(*) FROM incidents.incident_outbox WHERE incident_id = %s", (iid,))[0][0]
    assert outbox >= 4                                                    # chaque modification est publiée


async def test_changer_statut_de_clos_vers_en_cours_efface_la_cloture(db, database):
    ana, iid = new_analyst(database), new_incident(database, "clos")
    result = ok(await CommandService(db).apply(cmd("changer_statut", iid, ana, {"status": "en_cours"})))
    assert result["result"] == "acceptee"
    assert status_of(database, iid)[:2] == ("en_cours", False)


async def test_transition_interdite_refusee_et_enregistree(db, database):
    ana, iid = new_analyst(database), new_incident(database, "ouvert")
    result = ok(await CommandService(db).apply(cmd("rouvrir", iid, ana, {})))
    assert result["result"] == "refusee" and result["error"]["code"] == "transition_interdite"
    assert rows(database, "SELECT result::text FROM incidents.incident_commands WHERE incident_id = %s",
                (iid,)) == [("refusee",)]


async def test_commande_rejouee_non_reappliquee(db, database):
    ana, iid = new_analyst(database), new_incident(database)
    svc, command_id = CommandService(db), uuid.uuid4()
    first = ok(await svc.apply(cmd("commenter", iid, ana, {"body": "une seule fois"}, command_id)))
    again = ok(await svc.apply(cmd("commenter", iid, ana, {"body": "une seule fois"}, command_id)))
    assert (first["replayed"], again["replayed"]) == (False, True)
    assert rows(database, "SELECT count(*) FROM incidents.incident_comments WHERE incident_id = %s", (iid,))[0][0] == 1
