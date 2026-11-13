"""Serveur HTTP interne : authentification, validation des commandes, codes de réponse (C5 section 6).

C17 axe 1 : GET /incidents/{id}/timeline — sérialisation de la chronologie.
"""
from __future__ import annotations

import copy
import json
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

from conftest import CONTRACTS
from incidents.health import create_app
from incidents.repositories import DatabaseUnavailable
from incidents.repositories.incidents import IncidentRow, TimelineEntry

TOKEN = "t" * 40
STATUT = json.loads((CONTRACTS / "incident_command" / "v1" / "examples" / "statut_alerte.json").read_text())
CHANGER = json.loads((CONTRACTS / "incident_command" / "v1" / "examples" / "changer_statut.json").read_text())

# ---- fakes partagés ----

INC_ID = uuid.uuid4()
NOW = datetime(2026, 11, 13, 10, 0, 0, tzinfo=timezone.utc)

FAKE_INC = IncidentRow(
    id=INC_ID, title="Test", status="ouvert", severity="moyenne",
    correlation_context={}, opened_at=NOW, last_activity_at=NOW,
    closed_at=None, assigned_to=None,
)

FAKE_ENTRIES = [
    TimelineEntry(
        id=1, incident_id=INC_ID, occurred_at=NOW, recorded_at=NOW,
        entry_type="status_change", alert_id=None, event_id=None,
        summary="Incident ouvert", justification=None, actor_id=None,
    ),
    TimelineEntry(
        id=2, incident_id=INC_ID, occurred_at=NOW, recorded_at=NOW,
        entry_type="comment", alert_id=None, event_id=None,
        summary="Premier commentaire", justification=None,
        actor_id=uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
    ),
]


@dataclass
class FakeDB:
    """Base de données factice pour les tests de la route timeline."""
    incident: IncidentRow | None = field(default_factory=lambda: FAKE_INC)
    entries: list[TimelineEntry] = field(default_factory=lambda: list(FAKE_ENTRIES))
    raises: Exception | None = None

    @asynccontextmanager
    async def connection(self):
        if self.raises:
            raise self.raises
        yield self

    async def execute(self, *a, **kw):  # interface minimale — non utilisé directement
        pass


# Monkey-patch de inc_repo pour injecter les fakes sans PostgreSQL réel
class _FakeRepo:
    def __init__(self, db: FakeDB):
        self._db = db

    async def get_incident(self, conn, iid):
        return self._db.incident

    async def list_timeline(self, conn, iid):
        return self._db.entries


class FakeCommands:
    def __init__(self):
        self.received, self.raises = [], None

    async def apply(self, cmd):
        if self.raises:
            raise self.raises
        self.received.append(cmd)
        return {"contract": "incident_command_result/v1", "command_id": cmd["command_id"], "result": "acceptee",
                "completed_at": "2026-11-12T10:00:00.000Z", "replayed": False}


@pytest.fixture
def commands():
    return FakeCommands()


@pytest.fixture
def state():
    return {"broker": True, "db": True}


@pytest.fixture
def client(commands, contracts, state):
    async def db_ready():
        return state["db"]

    app = create_app(broker_connected=lambda: state["broker"], db_ready=db_ready, commands=commands,
                     contracts=contracts, command_token=TOKEN)
    return TestClient(app)


# ---- fixture avec une vraie FakeDB pour les tests timeline ----

@pytest.fixture
def fake_db():
    return FakeDB()


@pytest.fixture
def tl_client(commands, contracts, state, fake_db, monkeypatch):
    """Client avec db= branché + inc_repo patché pour éviter PostgreSQL."""
    import incidents.repositories.incidents as _inc_repo_mod
    repo = _FakeRepo(fake_db)
    monkeypatch.setattr(_inc_repo_mod, "get_incident", repo.get_incident)
    monkeypatch.setattr(_inc_repo_mod, "list_timeline", repo.list_timeline)

    async def db_ready():
        return state["db"]

    app = create_app(broker_connected=lambda: state["broker"], db_ready=db_ready, commands=commands,
                     contracts=contracts, command_token=TOKEN, db=fake_db)
    return TestClient(app)


def post(client, body, token=TOKEN):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post("/commands", content=body if isinstance(body, bytes) else json.dumps(body), headers=headers)


def test_sante_ok(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok", "broker": "connected", "postgresql": "reachable"}


def test_sante_degradee_si_postgresql_injoignable(client, state):
    state["db"] = False
    r = client.get("/health")
    assert r.status_code == 503 and r.json()["postgresql"] == "unreachable"


def test_metriques_exposees(client):
    r = client.get("/metrics")
    assert r.status_code == 200 and "baolsec_incidents_" in r.text


@pytest.mark.parametrize("token", [None, "", "mauvais", "t" * 39, "t" * 41])
def test_commande_sans_secret_valide_refusee(client, commands, token):
    assert post(client, STATUT, token=token).status_code == 401
    assert commands.received == []


def test_secret_au_mauvais_format_refuse(client):
    r = client.post("/commands", json=STATUT, headers={"Authorization": TOKEN})
    assert r.status_code == 401


def test_commande_acceptee_renvoie_le_resultat(client, commands):
    r = post(client, STATUT)
    assert r.status_code == 200 and r.json()["result"] == "acceptee" and r.json()["command_id"] == STATUT["command_id"]
    assert commands.received == [STATUT]


def test_corps_illisible(client):
    assert post(client, b"{pas du json").status_code == 400


@pytest.mark.parametrize("mutate", [
    lambda c: c.pop("command_id"),
    lambda c: c.update(command_id="abc"),
    lambda c: c["payload"].update(status="terminee"),
    lambda c: c["target"].update(incident_id=str(uuid.uuid4())),       # alerte ET incident
    lambda c: c.update(extra=1),
])
def test_commande_non_conforme(client, commands, mutate):
    cmd = copy.deepcopy(STATUT)
    mutate(cmd)
    r = post(client, cmd)
    assert r.status_code == 400 and r.headers["content-type"].startswith("application/problem+json")
    assert "incident_command/v1" in r.json()["title"] and commands.received == []



def test_base_indisponible_demande_de_renvoyer_la_commande(client, commands):
    commands.raises = DatabaseUnavailable("coupure")
    r = post(client, STATUT)
    assert r.status_code == 503 and "même command_id" in r.json()["detail"]


def test_erreur_interne_ne_divulgue_pas_le_detail(client, commands):
    commands.raises = RuntimeError("secret interne : mot de passe=hunter2")
    r = post(client, STATUT)
    assert r.status_code == 500 and "hunter2" not in r.text


# ======================================================================
# GET /incidents/{id}/timeline — C17 axe 1
# ======================================================================

def tl_get(client, iid=None, token=TOKEN):
    iid = iid or str(INC_ID)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.get(f"/incidents/{iid}/timeline", headers=headers)


def test_timeline_ok(tl_client):
    r = tl_get(tl_client)
    assert r.status_code == 200
    body = r.json()
    assert body["incident_id"] == str(INC_ID)
    assert body["count"] == 2
    assert len(body["entries"]) == 2
    e0, e1 = body["entries"]
    assert e0["id"] == 1 and e0["entry_type"] == "status_change"
    assert e1["id"] == 2 and e1["actor_id"] == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    # champs optionnels absents si None
    assert "alert_id" not in e0
    assert "justification" not in e0


def test_timeline_dates_en_utc_iso(tl_client):
    r = tl_get(tl_client)
    entry = r.json()["entries"][0]
    assert entry["occurred_at"].endswith("Z"), "occurred_at doit être ISO 8601 UTC avec suffixe Z"
    assert entry["recorded_at"].endswith("Z")


def test_timeline_vide(tl_client, fake_db):
    fake_db.entries = []
    r = tl_get(tl_client)
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 0 and body["entries"] == []


def test_timeline_incident_introuvable(tl_client, fake_db):
    fake_db.incident = None
    r = tl_get(tl_client)
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")


def test_timeline_uuid_invalide(tl_client):
    r = tl_get(tl_client, iid="pas-un-uuid")
    assert r.status_code == 400
    assert r.headers["content-type"].startswith("application/problem+json")


@pytest.mark.parametrize("token", [None, "", "mauvais", "t" * 39, "t" * 41])
def test_timeline_sans_token_valide(tl_client, token):
    r = tl_get(tl_client, token=token)
    assert r.status_code == 401


def test_timeline_base_indisponible(tl_client, fake_db):
    fake_db.raises = DatabaseUnavailable("coupure")
    r = tl_get(tl_client)
    assert r.status_code == 503
    assert r.headers["content-type"].startswith("application/problem+json")


def test_timeline_sans_db_configure(client):
    """Si create_app est appelé sans db=, la route renvoie 503."""
    r = tl_get(client)
    assert r.status_code == 503
