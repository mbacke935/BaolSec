"""Tests des routes de l'API BaolSec (C20).

Stratégie : mocker le pool de connexion pour ne pas avoir besoin
d'une vraie base PostgreSQL.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from baolsec_api import auth as _auth
from baolsec_api.database import get_pool
from baolsec_api.models import IncidentState, Severity, UserRole


# ── Helpers ───────────────────────────────────────────────────────────────────

NOW = datetime.now(timezone.utc)

SOURCE_ROW = {
    "id": uuid.uuid4(),
    "name": "Firewall-A",
    "description": "Pare-feu principal",
    "type": "syslog",
    "active": True,
    "silence_threshold_s": 300,
    "config": {},
    "created_at": NOW,
    "updated_at": NOW,
}

RULE_ROW = {
    "id": uuid.uuid4(),
    "name": "Règle SSH Brute-force",
    "description": None,
    "logic": {"field": "event_type", "op": "eq", "value": "ssh_failed"},
    "severity": "ELEVE",
    "enabled": True,
    "source_type": "syslog",
    "threshold": 5,
    "window_id": None,
    "version": 1,
    "created_at": NOW,
    "updated_at": NOW,
}

INCIDENT_ROW = {
    "id": uuid.uuid4(),
    "title": "Incident test",
    "description": None,
    "state": "OUVERT",
    "severity": "MOYEN",
    "opened_at": NOW,
    "closed_at": None,
    "assigned_to": None,
    "metadata": {},
    "created_at": NOW,
    "updated_at": NOW,
}

ALERT_ROW = {
    "id": uuid.uuid4(),
    "incident_id": INCIDENT_ROW["id"],
    "rule_id": RULE_ROW["id"],
    "source_id": SOURCE_ROW["id"],
    "severity": "ELEVE",
    "title": "SSH Brute-force détecté",
    "detail": {"attempts": 10},
    "fired_at": NOW,
}

USER_ROW = {
    "id": uuid.uuid4(),
    "username": "analyst",
    "email": "analyst@test.local",
    "role": "Analyste",          # nom tel que stocké dans acces.roles (C4)
    "is_active": True,
    "created_at": NOW,
    "updated_at": NOW,
}


def make_fake_pool(rows=None):
    """Crée un pool mocké qui retourne un curseur avec les lignes données."""
    rows = rows or []
    cursor = AsyncMock()
    cursor.fetchone = AsyncMock(return_value=rows[0] if rows else None)
    cursor.fetchall = AsyncMock(return_value=list(rows))
    cursor.execute = AsyncMock()
    cursor.__aenter__ = AsyncMock(return_value=cursor)
    cursor.__aexit__ = AsyncMock(return_value=False)

    conn = MagicMock()
    conn.cursor = MagicMock(return_value=cursor)
    conn.__aenter__ = AsyncMock(return_value=conn)
    conn.__aexit__ = AsyncMock(return_value=False)

    pool = MagicMock()
    pool.connection = MagicMock(return_value=conn)
    return pool


# ── Tests Sources ─────────────────────────────────────────────────────────────

class TestSources:
    def test_list_sources_analyst(self, client, analyst_headers):
        with patch("baolsec_api.database._pool", make_fake_pool([SOURCE_ROW])):
            resp = client.get("/api/v1/sources", headers=analyst_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_list_sources_requires_auth(self, client):
        resp = client.get("/api/v1/sources")
        assert resp.status_code == 401

    def test_create_source_admin_only(self, client, analyst_headers, admin_headers):
        payload = {"name": "FW-B", "type": "syslog"}
        with patch("baolsec_api.database._pool", make_fake_pool([SOURCE_ROW])):
            resp_analyst = client.post("/api/v1/sources", json=payload, headers=analyst_headers)
            resp_admin = client.post("/api/v1/sources", json=payload, headers=admin_headers)
        assert resp_analyst.status_code == 403
        assert resp_admin.status_code == 201

    def test_get_source_not_found(self, client, analyst_headers):
        with patch("baolsec_api.database._pool", make_fake_pool([])):
            resp = client.get(f"/api/v1/sources/{uuid.uuid4()}", headers=analyst_headers)
        assert resp.status_code == 404

    def test_delete_source_analyst_forbidden(self, client, analyst_headers):
        with patch("baolsec_api.database._pool", make_fake_pool([SOURCE_ROW])):
            resp = client.delete(f"/api/v1/sources/{SOURCE_ROW['id']}", headers=analyst_headers)
        assert resp.status_code == 403


# ── Tests Règles ──────────────────────────────────────────────────────────────

class TestRules:
    def test_list_rules(self, client, analyst_headers):
        with patch("baolsec_api.database._pool", make_fake_pool([RULE_ROW])):
            resp = client.get("/api/v1/rules", headers=analyst_headers)
        assert resp.status_code == 200

    def test_create_rule_admin_only(self, client, analyst_headers, admin_headers):
        payload = {"name": "Test rule", "logic": {"op": "eq"}}
        with patch("baolsec_api.database._pool", make_fake_pool([RULE_ROW])):
            assert client.post("/api/v1/rules", json=payload, headers=analyst_headers).status_code == 403
            assert client.post("/api/v1/rules", json=payload, headers=admin_headers).status_code == 201

    def test_disable_rule_admin_only(self, client, analyst_headers, admin_headers):
        with patch("baolsec_api.database._pool", make_fake_pool([RULE_ROW])):
            assert client.delete(f"/api/v1/rules/{RULE_ROW['id']}", headers=analyst_headers).status_code == 403
            assert client.delete(f"/api/v1/rules/{RULE_ROW['id']}", headers=admin_headers).status_code == 204


# ── Tests Incidents ───────────────────────────────────────────────────────────

class TestIncidents:
    def test_list_incidents(self, client, analyst_headers):
        with patch("baolsec_api.database._pool", make_fake_pool([INCIDENT_ROW])):
            resp = client.get("/api/v1/incidents", headers=analyst_headers)
        assert resp.status_code == 200

    def test_get_incident_detail(self, client, analyst_headers):
        with patch("baolsec_api.database._pool", make_fake_pool([INCIDENT_ROW])):
            resp = client.get(f"/api/v1/incidents/{INCIDENT_ROW['id']}", headers=analyst_headers)
        assert resp.status_code == 200

    def test_update_state_analyst_allowed(self, client, analyst_headers):
        with patch("baolsec_api.database._pool", make_fake_pool([INCIDENT_ROW])):
            resp = client.post(
                f"/api/v1/incidents/{INCIDENT_ROW['id']}/status",
                json={"state": "EN_COURS"},
                headers=analyst_headers,
            )
        assert resp.status_code == 200

    def test_update_state_anonymous_forbidden(self, client):
        with patch("baolsec_api.database._pool", make_fake_pool([INCIDENT_ROW])):
            resp = client.post(
                f"/api/v1/incidents/{INCIDENT_ROW['id']}/status",
                json={"state": "EN_COURS"},
            )
        assert resp.status_code == 401

    def test_incident_timeline(self, client, analyst_headers):
        timeline_row = {
            "id": uuid.uuid4(),
            "incident_id": INCIDENT_ROW["id"],
            "entry_type": "ALERTE",
            "occurred_at": NOW,
            "detail": {},
            "source_id": None,
            "alert_id": None,
            "user_id": None,
        }
        with patch("baolsec_api.database._pool", make_fake_pool([timeline_row])):
            resp = client.get(f"/api/v1/incidents/{INCIDENT_ROW['id']}/timeline", headers=analyst_headers)
        assert resp.status_code == 200


# ── Tests Alertes ─────────────────────────────────────────────────────────────

class TestAlerts:
    def test_list_alerts(self, client, analyst_headers):
        with patch("baolsec_api.database._pool", make_fake_pool([ALERT_ROW])):
            resp = client.get("/api/v1/alerts", headers=analyst_headers)
        assert resp.status_code == 200

    def test_get_alert_not_found(self, client, analyst_headers):
        with patch("baolsec_api.database._pool", make_fake_pool([])):
            resp = client.get(f"/api/v1/alerts/{uuid.uuid4()}", headers=analyst_headers)
        assert resp.status_code == 404


# ── Tests Utilisateurs ────────────────────────────────────────────────────────

class TestUsers:
    def test_list_users_admin_only(self, client, analyst_headers, admin_headers):
        with patch("baolsec_api.database._pool", make_fake_pool([USER_ROW])):
            assert client.get("/api/v1/users", headers=analyst_headers).status_code == 403
            assert client.get("/api/v1/users", headers=admin_headers).status_code == 200

    def test_create_user_admin(self, client, admin_headers):
        with patch("baolsec_api.database._pool", make_fake_pool([USER_ROW])):
            resp = client.post(
                "/api/v1/users",
                json={"email": "new@test.local", "password": "securepassword"},
                headers=admin_headers,
            )
        assert resp.status_code == 201

    def test_get_me(self, client, analyst_headers):
        with patch("baolsec_api.database._pool", make_fake_pool([USER_ROW])):
            resp = client.get("/api/v1/users/me", headers=analyst_headers)
        assert resp.status_code == 200


# ── Tests Health ──────────────────────────────────────────────────────────────

class TestHealth:
    def test_health_no_auth(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_metrics_no_auth(self, client):
        resp = client.get("/metrics")
        assert resp.status_code == 200
        assert "baolsec_api" in resp.text
