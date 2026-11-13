"""Tests du serveur HTTP /health et /metrics du coverage-worker (C17)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from coverage.health import create_app


@pytest.fixture
def state():
    return {"broker": True, "db": True}


@pytest.fixture
def client(state):
    async def db_ready():
        return state["db"]

    app = create_app(broker_connected=lambda: state["broker"], db_ready=db_ready)
    return TestClient(app)


def test_sante_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["broker"] == "connected"
    assert body["postgresql"] == "reachable"


def test_sante_degradee_si_broker_deconnecte(client, state):
    state["broker"] = False
    r = client.get("/health")
    assert r.status_code == 503
    assert r.json()["broker"] == "disconnected"
    assert r.json()["status"] == "degraded"


def test_sante_degradee_si_postgresql_injoignable(client, state):
    state["db"] = False
    r = client.get("/health")
    assert r.status_code == 503
    assert r.json()["postgresql"] == "unreachable"


def test_metriques_exposees(client):
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "baolsec_coverage_" in r.text
