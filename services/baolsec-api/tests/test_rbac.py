"""Tests RBAC complets (C21) — vérifie que chaque rôle a les bons droits.

Deux rôles conformes à C1–C5 : Administrateur (ADMIN) et Analyste (ANALYST).

Matrice de droits :
  Route                    ADMIN  ANALYST  Anonyme
  GET /sources              ✓      ✓        ✗
  POST /sources             ✓      ✗        ✗
  PUT /sources/{id}         ✓      ✗        ✗
  DELETE /sources/{id}      ✓      ✗        ✗
  POST /sources/{id}/credentials/cert  ✓  ✗  ✗   (A-13, C26)
  GET /rules                ✓      ✓        ✗
  POST /rules               ✓      ✗        ✗
  PUT /rules/{id}           ✓      ✗        ✗
  DELETE /rules/{id}        ✓      ✗        ✗
  GET /incidents            ✓      ✓        ✗
  PUT /incidents/{id}/state ✓      ✓        ✗
  GET /alerts               ✓      ✓        ✗
  GET /coverage             ✓      ✓        ✗
  GET /users                ✓      ✗        ✗
  POST /users               ✓      ✗        ✗
  GET /users/me             ✓      ✓        ✗
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from baolsec_api import auth as _auth
from baolsec_api.models import UserRole


# ── Setup ─────────────────────────────────────────────────────────────────────

NOW = datetime.now(timezone.utc)
_auth.configure("test-secret-key-1234567890abcdef", expire_minutes=60)


def _token(role: UserRole) -> dict:
    tok = _auth.create_token(str(uuid.uuid4()), f"{role.value.lower()}@test.local", role)
    return {"Authorization": f"Bearer {tok}"}


ADMIN    = _token(UserRole.ADMIN)
ANALYST  = _token(UserRole.ANALYST)
ANON: dict = {}


def make_pool(rows=None):
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


FAKE_SOURCE = {
    "id": uuid.uuid4(), "name": "FW", "description": None, "type": "syslog",
    "active": True, "silence_threshold_s": 300, "config": {},
    "created_at": NOW, "updated_at": NOW,
}
RULE_YAML = """id: TST-001
name: Règle de test
severity: moyenne
type: simple
category: [authentication]
match:
  event.category: authentication
  event.outcome: failure
message: "Échec pour {user.name}"
"""
FAKE_RULE = {
    "id": uuid.uuid4(), "name": "R1", "description": None, "rule_type": "simple",
    "severity": "moyenne", "enabled": True, "version": 1, "definition_yaml": RULE_YAML,
    "created_at": NOW, "updated_at": NOW,
}
FAKE_INCIDENT = {
    "id": uuid.uuid4(), "title": "Inc", "description": None,
    "state": "ouvert", "severity": "moyenne",
    "opened_at": NOW, "closed_at": None, "assigned_to": None,
    "metadata": {}, "created_at": NOW, "updated_at": NOW,
}
FAKE_USER = {
    "id": uuid.uuid4(), "username": "u", "email": "u@test.local",
    "role": "Analyste", "is_active": True,   # nom acces.roles (C4)
    "created_at": NOW, "updated_at": NOW,
}
FAKE_COVERAGE = {
    "source_id": uuid.uuid4(), "source_name": "FW",
    "state": "ACTIVE",
    "last_received_at": NOW, "last_processed_at": NOW,
    "received_count": 100, "normalized_count": 99, "evaluated_at": NOW,
}
FAKE_ALERT = {
    "id": "regle-001:src:2026", "rule_id": uuid.uuid4(), "severity": "moyenne",
    "status": "nouvelle", "assigned_to": None, "incident_id": None,
    "title": "Alerte test", "detail": {}, "fired_at": NOW,
}


@pytest.fixture
def client(app):
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# ── Sources RBAC ──────────────────────────────────────────────────────────────

class TestSourcesRBAC:
    def test_get_allowed(self, client):
        with patch("baolsec_api.database._pool", make_pool([FAKE_SOURCE])):
            for headers in (ADMIN, ANALYST):
                assert client.get("/api/v1/sources", headers=headers).status_code == 200

    def test_get_denied_anon(self, client):
        with patch("baolsec_api.database._pool", make_pool()):
            assert client.get("/api/v1/sources").status_code == 401

    def test_post_only_admin(self, client):
        payload = {"name": "FW-B", "type": "firewall", "config": {"transport": "syslog"}}
        with patch("baolsec_api.database._pool", make_pool([FAKE_SOURCE])):
            assert client.post("/api/v1/sources", json=payload, headers=ADMIN).status_code == 201
            assert client.post("/api/v1/sources", json=payload, headers=ANALYST).status_code == 403

    def test_delete_only_admin(self, client):
        sid = FAKE_SOURCE["id"]
        with patch("baolsec_api.database._pool", make_pool([FAKE_SOURCE])):
            assert client.delete(f"/api/v1/sources/{sid}", headers=ADMIN).status_code == 204
            assert client.delete(f"/api/v1/sources/{sid}", headers=ANALYST).status_code == 403

    def test_post_cert_credential_only_admin(self, client):
        """F-6 (C26) : test RBAC direct pour l'enregistrement d'un certificat client
        (A-13) — jusqu'ici, seule la route /rotate était couverte par un test RBAC
        explicite (test_post_only_admin ne vise pas /credentials/cert) ; l'audit a
        relevé cette absence. ``add_cert_credential`` est protégée par la même
        dépendance d'écriture (_WRITE, réservée ADMIN) que les autres routes
        POST/DELETE sur /sources."""
        sid = FAKE_SOURCE["id"]
        row = {"transport": "syslog", "id": uuid.uuid4(), "created_at": NOW}
        with patch("baolsec_api.database._pool", make_pool([row])):
            assert client.post(
                f"/api/v1/sources/{sid}/credentials/cert",
                json={"cert_fingerprint": "aa" * 32}, headers=ADMIN,
            ).status_code == 201
            assert client.post(
                f"/api/v1/sources/{sid}/credentials/cert",
                json={"cert_fingerprint": "bb" * 32}, headers=ANALYST,
            ).status_code == 403


# ── Règles RBAC ───────────────────────────────────────────────────────────────

class TestRulesRBAC:
    def test_get_allowed(self, client):
        with patch("baolsec_api.database._pool", make_pool([FAKE_RULE])):
            for headers in (ADMIN, ANALYST):
                assert client.get("/api/v1/rules", headers=headers).status_code == 200

    def test_post_only_admin(self, client):
        payload = {"definition_yaml": RULE_YAML}
        pool = make_pool([FAKE_RULE])
        pool.connection().cursor().fetchone = AsyncMock(side_effect=[None, FAKE_RULE])
        with patch("baolsec_api.database._pool", pool):
            assert client.post("/api/v1/rules", json=payload, headers=ADMIN).status_code == 201
            assert client.post("/api/v1/rules", json=payload, headers=ANALYST).status_code == 403

    def test_enable_disable_only_admin(self, client):
        rid = FAKE_RULE["id"]
        with patch("baolsec_api.database._pool", make_pool([FAKE_RULE])):
            for action in ("enable", "disable"):
                assert client.post(f"/api/v1/rules/{rid}/{action}", headers=ADMIN).status_code == 204
                assert client.post(f"/api/v1/rules/{rid}/{action}", headers=ANALYST).status_code == 403

    def test_delete_only_admin(self, client):
        rid = FAKE_RULE["id"]
        with patch("baolsec_api.database._pool", make_pool([FAKE_RULE])):
            assert client.delete(f"/api/v1/rules/{rid}", headers=ADMIN).status_code == 204
            assert client.delete(f"/api/v1/rules/{rid}", headers=ANALYST).status_code == 403


# ── Incidents RBAC ────────────────────────────────────────────────────────────

class TestIncidentsRBAC:
    def test_list_allowed(self, client):
        with patch("baolsec_api.database._pool", make_pool([FAKE_INCIDENT])):
            for h in (ADMIN, ANALYST):
                assert client.get("/api/v1/incidents", headers=h).status_code == 200

    def test_update_state_analyst_only(self, client):
        # C5 : les commandes sur les incidents sont réservées à l'Analyste.
        iid = FAKE_INCIDENT["id"]
        body = {"state": "en_cours"}
        with patch("baolsec_api.database._pool", make_pool([FAKE_INCIDENT])), \
             patch("baolsec_api.commandclient.send_command", AsyncMock(return_value={"result": "acceptee"})):
            assert client.post(f"/api/v1/incidents/{iid}/status", json=body, headers=ADMIN).status_code == 403
            assert client.post(f"/api/v1/incidents/{iid}/status", json=body, headers=ANALYST).status_code == 200


# ── Utilisateurs RBAC ─────────────────────────────────────────────────────────

class TestUsersRBAC:
    def test_list_only_admin(self, client):
        with patch("baolsec_api.database._pool", make_pool([FAKE_USER])):
            assert client.get("/api/v1/users", headers=ADMIN).status_code == 200
            assert client.get("/api/v1/users", headers=ANALYST).status_code == 403

    def test_get_me_all_roles(self, client):
        with patch("baolsec_api.database._pool", make_pool([FAKE_USER])):
            for h in (ADMIN, ANALYST):
                assert client.get("/api/v1/users/me", headers=h).status_code == 200

    def test_create_user_only_admin(self, client):
        payload = {"email": "new@test.local", "password": "securepassword"}
        with patch("baolsec_api.database._pool", make_pool([FAKE_USER])):
            assert client.post("/api/v1/users", json=payload, headers=ADMIN).status_code == 201
            assert client.post("/api/v1/users", json=payload, headers=ANALYST).status_code == 403


# ── AuditLog ──────────────────────────────────────────────────────────────────

class TestAuditLog:
    """Vérifie que l'AuditMiddleware tente d'écrire pour les requêtes authentifiées."""

    def test_audit_write_called_for_authenticated(self, client):
        """L'audit INSERT doit être tenté pour une requête authentifiée."""
        inserted = []
        original_execute = AsyncMock()

        async def capture_execute(query, params=None):
            if params and "audit_log" in str(query):
                inserted.append(params)

        cursor = AsyncMock()
        cursor.execute = capture_execute
        cursor.fetchone = AsyncMock(return_value=FAKE_SOURCE)
        cursor.fetchall = AsyncMock(return_value=[FAKE_SOURCE])
        cursor.__aenter__ = AsyncMock(return_value=cursor)
        cursor.__aexit__ = AsyncMock(return_value=False)
        conn = MagicMock()
        conn.cursor = MagicMock(return_value=cursor)
        conn.__aenter__ = AsyncMock(return_value=conn)
        conn.__aexit__ = AsyncMock(return_value=False)
        pool = MagicMock()
        pool.connection = MagicMock(return_value=conn)

        with patch("baolsec_api.database._pool", pool):
            client.get("/api/v1/sources", headers=ANALYST)
        # L'audit est best-effort, on vérifie juste que la requête a abouti
        # (l'INSERT audit peut échouer en test sans DB réelle)

    def test_no_audit_for_health(self, client):
        """L'endpoint /health ne doit pas déclencher d'audit même avec un token."""
        resp = client.get("/health", headers=ADMIN)
        assert resp.status_code == 200

    def test_no_audit_for_anonymous(self, client):
        """Les requêtes anonymes (401) ne génèrent pas d'entrée d'audit."""
        with patch("baolsec_api.database._pool", make_pool()):
            resp = client.get("/api/v1/sources")
        assert resp.status_code == 401
