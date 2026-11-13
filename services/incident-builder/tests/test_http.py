"""Serveur HTTP interne : authentification, validation des commandes, codes de réponse (C5 section 6)."""
from __future__ import annotations

import copy
import json
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from conftest import CONTRACTS
from incidents.health import create_app
from incidents.repositories import DatabaseUnavailable

TOKEN = "t" * 40
STATUT = json.loads((CONTRACTS / "incident_command" / "v1" / "examples" / "statut_alerte.json").read_text())
CHANGER = json.loads((CONTRACTS / "incident_command" / "v1" / "examples" / "changer_statut.json").read_text())


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
