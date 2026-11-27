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

# Forme renvoyée par config.rules + version courante (C4) : la définition YAML fait foi (EF-05).
RULE_ROW = {
    "id": uuid.uuid4(),
    "name": "Règle de test",
    "description": None,
    "rule_type": "simple",
    "severity": "moyenne",
    "enabled": True,
    "version": 1,
    "definition_yaml": RULE_YAML,
    "created_at": NOW,
    "updated_at": NOW,
}

INCIDENT_ROW = {
    "id": uuid.uuid4(),
    "title": "Incident test",
    "description": None,
    "state": "ouvert",
    "severity": "moyenne",
    "opened_at": NOW,
    "closed_at": None,
    "assigned_to": None,
    "metadata": {},
    "created_at": NOW,
    "updated_at": NOW,
}

# AlertResponse (C4) : alert_id texte + état de triage (incidents.alert_state).
ALERT_ROW = {
    "id": "auth-001:srv-auth-01:2026",
    "rule_id": RULE_ROW["id"],
    "severity": "elevee",
    "status": "nouvelle",
    "assigned_to": None,
    "incident_id": INCIDENT_ROW["id"],
    "title": "Échecs de connexion répétés",
    "detail": {},
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


def make_fake_pool_with_conflict(select_row, insert_exception):
    """Pool mocké pour les tests F-3 (C26) : la 1re requête exécutée (le SELECT de
    vérification d'existence) réussit et renvoie `select_row` via fetchone(), puis
    toute requête suivante (l'INSERT) lève `insert_exception` — simulant la violation
    de contrainte unique que PostgreSQL renverrait réellement pour un identifiant actif
    en doublon (index partiels de la migration 0004_credentials_unicite)."""
    cursor = AsyncMock()
    cursor.fetchone = AsyncMock(return_value=select_row)
    cursor.fetchall = AsyncMock(return_value=[select_row] if select_row else [])
    call_count = {"n": 0}

    async def _execute(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] >= 2:
            raise insert_exception

    cursor.execute = AsyncMock(side_effect=_execute)
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
        # Réponse paginée (C20 Page[SourceResponse]) : {items, total, limit, offset}
        assert isinstance(data["items"], list) and data["items"][0]["name"] == SOURCE_ROW["name"]

    def test_list_sources_requires_auth(self, client):
        with patch("baolsec_api.database._pool", make_fake_pool([])):
            resp = client.get("/api/v1/sources")
        assert resp.status_code == 401

    def test_create_source_admin_only(self, client, analyst_headers, admin_headers):
        payload = {"name": "FW-B", "type": "firewall", "config": {"transport": "syslog"}}
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

    def test_rotate_credential_prefixe_bsk_et_ne_revoque_pas(self, client, admin_headers, analyst_headers):
        """A-03 : le jeton généré porte le préfixe bsk_ (cohérent avec gateway.auth.generate_token,
        vérifié par la passerelle), et la rotation ne doit plus émettre de révocation des jetons
        existants dans la même opération (rotation en deux temps, C7)."""
        credential_row = {"id": uuid.uuid4(), "created_at": NOW}
        fake_pool = make_fake_pool([credential_row])
        cursor = fake_pool.connection().cursor()
        with patch("baolsec_api.database._pool", fake_pool):
            resp_analyst = client.post(
                f"/api/v1/sources/{SOURCE_ROW['id']}/credentials/rotate", headers=analyst_headers)
            resp = client.post(
                f"/api/v1/sources/{SOURCE_ROW['id']}/credentials/rotate", headers=admin_headers)
        assert resp_analyst.status_code == 403                 # écriture réservée ADMIN
        assert resp.status_code == 201
        body = resp.json()
        assert body["token"].startswith("bsk_")
        executed_sql = " ".join(str(c.args[0]) for c in cursor.execute.call_args_list if c.args)
        assert "revoked_at = NOW()" not in executed_sql, (
            "la rotation ne doit plus révoquer automatiquement les jetons existants (A-03)"
        )
        assert "INSERT INTO config.source_credentials" in executed_sql

    def test_revoke_credential_204(self, client, admin_headers):
        credential_id = uuid.uuid4()
        with patch("baolsec_api.database._pool", make_fake_pool([{"id": credential_id}])):
            resp = client.delete(
                f"/api/v1/sources/{SOURCE_ROW['id']}/credentials/{credential_id}", headers=admin_headers)
        assert resp.status_code == 204

    def test_revoke_credential_introuvable_404(self, client, admin_headers):
        with patch("baolsec_api.database._pool", make_fake_pool([])):
            resp = client.delete(
                f"/api/v1/sources/{SOURCE_ROW['id']}/credentials/{uuid.uuid4()}", headers=admin_headers)
        assert resp.status_code == 404

    def test_add_cert_credential_normalise_et_stocke_empreinte(self, client, admin_headers):
        """A-13 : une empreinte de certificat fournie avec des ':' et des majuscules est
        normalisée (minuscules, sans séparateur) avant stockage — forme lue par la
        Gateway (gateway.sources_cache.normalize_fingerprint)."""
        credential_id = uuid.uuid4()
        raw_fp = "AA:BB:CC:DD:" + "00:" * 27 + "EE"   # 32 octets en hex séparés par ':' = 64 car.
        row = {"transport": "syslog", "id": credential_id, "created_at": NOW}
        fake_pool = make_fake_pool([row])
        cursor = fake_pool.connection().cursor()
        with patch("baolsec_api.database._pool", fake_pool):
            resp = client.post(
                f"/api/v1/sources/{SOURCE_ROW['id']}/credentials/cert",
                json={"cert_fingerprint": raw_fp}, headers=admin_headers)
        assert resp.status_code == 201
        body = resp.json()
        assert body["cert_fingerprint"] == raw_fp.replace(":", "").lower()
        assert ":" not in body["cert_fingerprint"]
        executed_sql = " ".join(str(c.args[0]) for c in cursor.execute.call_args_list if c.args)
        assert "'client_cert'" in executed_sql or "client_cert" in executed_sql

    def test_add_cert_credential_refuse_fingerprint_invalide(self, client, admin_headers):
        row = {"transport": "syslog", "id": uuid.uuid4(), "created_at": NOW}
        with patch("baolsec_api.database._pool", make_fake_pool([row])):
            resp = client.post(
                f"/api/v1/sources/{SOURCE_ROW['id']}/credentials/cert",
                json={"cert_fingerprint": "pas-une-empreinte"}, headers=admin_headers)
        assert resp.status_code == 422

    def test_add_cert_credential_refuse_source_https(self, client, admin_headers):
        """Un certificat client ne s'applique qu'aux sources Syslog (A-13)."""
        row = {"transport": "https", "id": uuid.uuid4(), "created_at": NOW}
        with patch("baolsec_api.database._pool", make_fake_pool([row])):
            resp = client.post(
                f"/api/v1/sources/{SOURCE_ROW['id']}/credentials/cert",
                json={"cert_fingerprint": "aa" * 32}, headers=admin_headers)
        assert resp.status_code == 422

    def test_add_cert_credential_source_introuvable_404(self, client, admin_headers):
        with patch("baolsec_api.database._pool", make_fake_pool([])):
            resp = client.post(
                f"/api/v1/sources/{uuid.uuid4()}/credentials/cert",
                json={"cert_fingerprint": "aa" * 32}, headers=admin_headers)
        assert resp.status_code == 404

    def test_add_cert_credential_doublon_actif_renvoie_409(self, client, admin_headers):
        """F-3 (C26) : une empreinte déjà associée à un identifiant ACTIF — qu'il
        s'agisse de la même source ou d'une autre, l'index partiel ne distingue pas —
        est désormais refusée avec 409 plutôt que d'être acceptée en silence (ce qui,
        combiné au cache de la passerelle qui écrase silencieusement une entrée en
        cas de collision, aurait pu mal attribuer des événements à la mauvaise
        source). Simulé en forçant l'INSERT à lever la violation de contrainte unique
        que PostgreSQL renverrait réellement pour uq_source_credentials_cert_fingerprint_active."""
        select_row = {"transport": "syslog"}
        exc = Exception(
            'duplicate key value violates unique constraint '
            '"uq_source_credentials_cert_fingerprint_active"'
        )
        fake_pool = make_fake_pool_with_conflict(select_row, exc)
        with patch("baolsec_api.database._pool", fake_pool):
            resp = client.post(
                f"/api/v1/sources/{SOURCE_ROW['id']}/credentials/cert",
                json={"cert_fingerprint": "aa" * 32}, headers=admin_headers)
        assert resp.status_code == 409
        assert "empreinte" in resp.json()["detail"].lower()

    def test_rotate_credential_doublon_secret_hash_renvoie_409(self, client, admin_headers):
        """F-3 (C26) : par symétrie avec le cas certificat, une collision de
        secret_hash actif — extrêmement improbable vu l'aléa de
        secrets.token_urlsafe(32), mais désormais empêchée par
        uq_source_credentials_secret_hash_active — est refusée avec 409 plutôt que de
        provoquer une erreur 500 non gérée si elle survenait malgré tout."""
        select_row = {"id": uuid.uuid4()}
        exc = Exception(
            'duplicate key value violates unique constraint '
            '"uq_source_credentials_secret_hash_active"'
        )
        fake_pool = make_fake_pool_with_conflict(select_row, exc)
        with patch("baolsec_api.database._pool", fake_pool):
            resp = client.post(
                f"/api/v1/sources/{SOURCE_ROW['id']}/credentials/rotate", headers=admin_headers)
        assert resp.status_code == 409

    def test_add_cert_credential_reutilisation_apres_revocation_201(self, client, admin_headers):
        """F-3 (C26) : l'unicité introduite par la migration 0004 est scopée aux
        identifiants ACTIFS (revoked_at IS NULL) — après révocation explicite du
        titulaire précédent d'une empreinte, cette empreinte doit redevenir
        disponible pour un nouvel enregistrement (cohérent avec le cycle de vie de
        révocation déjà en place, A-03). Ce test, basé sur un pool mocké, ne peut pas
        vérifier le comportement réel de l'index partiel (seule une vraie base
        PostgreSQL le peut, cf. caveat de la migration) ; il fige seulement le
        comportement attendu côté API : révoquer puis réenregistrer la même empreinte
        n'est pas bloqué par le code applicatif lui-même."""
        credential_id = uuid.uuid4()
        fingerprint = "bb" * 32
        with patch("baolsec_api.database._pool", make_fake_pool([{"id": credential_id}])):
            resp_revoke = client.delete(
                f"/api/v1/sources/{SOURCE_ROW['id']}/credentials/{credential_id}",
                headers=admin_headers)
        assert resp_revoke.status_code == 204

        row = {"transport": "syslog", "id": uuid.uuid4(), "created_at": NOW}
        with patch("baolsec_api.database._pool", make_fake_pool([row])):
            resp_readd = client.post(
                f"/api/v1/sources/{SOURCE_ROW['id']}/credentials/cert",
                json={"cert_fingerprint": fingerprint}, headers=admin_headers)
        assert resp_readd.status_code == 201


# ── Tests Règles ──────────────────────────────────────────────────────────────

class TestRules:
    def test_list_rules(self, client, analyst_headers):
        with patch("baolsec_api.database._pool", make_fake_pool([RULE_ROW])):
            resp = client.get("/api/v1/rules", headers=analyst_headers)
        assert resp.status_code == 200
        item = resp.json()["items"][0]
        assert item["code"] == "TST-001"                       # lu dans la définition YAML
        assert item["category"] == ["authentication"]
        assert item["logic"]["match"]["event.outcome"] == "failure"

    def test_create_rule_admin_only(self, client, analyst_headers, admin_headers):
        payload = {"definition_yaml": RULE_YAML}
        pool = make_fake_pool([RULE_ROW])
        cursor = pool.connection().cursor()
        # 1er fetchone : contrôle d'unicité (aucune règle existante) ; 2e : relecture de la règle créée
        cursor.fetchone = AsyncMock(side_effect=[None, RULE_ROW])
        with patch("baolsec_api.database._pool", pool):
            assert client.post("/api/v1/rules", json=payload, headers=analyst_headers).status_code == 403
            resp = client.post("/api/v1/rules", json=payload, headers=admin_headers)
        assert resp.status_code == 201
        sql = " ".join(str(c.args[0]) for c in cursor.execute.call_args_list if c.args)
        assert "INSERT INTO config.rule_versions" in sql      # la définition est versionnée
        assert "INSERT INTO config.rules" in sql

    def test_create_rule_refuse_definition_invalide(self, client, admin_headers):
        """EF-05 : une définition non conforme au contrat rule/v1 est refusée (422), jamais enregistrée."""
        with patch("baolsec_api.database._pool", make_fake_pool([RULE_ROW])):
            resp = client.post("/api/v1/rules", json={"definition_yaml": "id: X\nname: incomplète"},
                               headers=admin_headers)
        assert resp.status_code == 422
        assert "rule/v1" in resp.json()["detail"]

    def test_create_rule_refuse_regex_invalide(self, client, admin_headers):
        bad = RULE_YAML.replace("event.outcome: failure", "event.outcome: {regex: '(['}")
        with patch("baolsec_api.database._pool", make_fake_pool([RULE_ROW])):
            resp = client.post("/api/v1/rules", json={"definition_yaml": bad}, headers=admin_headers)
        assert resp.status_code == 422
        assert "expression régulière" in resp.json()["detail"]

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
        # La commande est transmise au service Incidents : on mocke le client HTTP.
        with patch("baolsec_api.database._pool", make_fake_pool([INCIDENT_ROW])), \
             patch("baolsec_api.commandclient.send_command", AsyncMock(return_value={"result": "acceptee"})):
            resp = client.post(
                f"/api/v1/incidents/{INCIDENT_ROW['id']}/status",
                json={"state": "en_cours"},
                headers=analyst_headers,
            )
        assert resp.status_code == 200

    def test_update_state_anonymous_forbidden(self, client):
        with patch("baolsec_api.database._pool", make_fake_pool([INCIDENT_ROW])):
            resp = client.post(
                f"/api/v1/incidents/{INCIDENT_ROW['id']}/status",
                json={"state": "en_cours"},
            )
        assert resp.status_code == 401

    def test_incident_timeline(self, client, analyst_headers):
        timeline_row = {
            "id": 1,
            "incident_id": INCIDENT_ROW["id"],
            "entry_type": "alert",
            "occurred_at": NOW,
            "summary": "Alerte rattachée",
            "detail": {},
            "alert_id": None,
            "event_id": None,
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
