"""Tests des corrections et compléments de l'audit du 26/11/2026 (C26, journal d'audit B01–B24).

Chaque test vise un défaut constaté en exécution réelle (PostgreSQL et NATS locaux) ; il échouait
ou n'avait pas d'objet avant la correction correspondante.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from baolsec_api import auth as _auth
from baolsec_api.auth import hash_password
from baolsec_api.middleware.security import TokenBucket

from test_routes import SOURCE_ROW, make_fake_pool

NOW = datetime.now(timezone.utc)


def _pool_with(fetchone=None, execute=None):
    pool = make_fake_pool([])
    conn = pool.connection()
    cursor = conn.cursor()
    if fetchone is not None:
        cursor.fetchone = AsyncMock(side_effect=fetchone) if isinstance(fetchone, list) else AsyncMock(return_value=fetchone)
    if execute is not None:
        cursor.execute = execute
    conn.execute = AsyncMock()
    return pool, conn, cursor


# ── ES-05 : protection de l'API ───────────────────────────────────────────────

class TestProtection:
    def test_en_tetes_de_securite(self, client, analyst_headers):
        with patch("baolsec_api.database._pool", make_fake_pool([SOURCE_ROW])):
            resp = client.get("/api/v1/sources", headers=analyst_headers)
        assert resp.headers["x-content-type-options"] == "nosniff"
        assert resp.headers["x-frame-options"] == "DENY"
        assert "default-src 'none'" in resp.headers["content-security-policy"]

    def test_corps_trop_volumineux_413(self, client, admin_headers):
        big = b'{"name":"' + b"a" * 2_000_000 + b'"}'
        resp = client.post("/api/v1/sources", content=big,
                           headers={**admin_headers, "Content-Type": "application/json"})
        assert resp.status_code == 413

    def test_seau_a_jetons(self):
        bucket = TokenBucket(per_minute=3, burst=3)
        assert [bucket.take("ip", now=0.0) for _ in range(3)] == [0.0, 0.0, 0.0]
        assert bucket.take("ip", now=0.0) > 0                 # 4e requête immédiate : refusée
        assert bucket.take("ip", now=21.0) == 0.0             # un jeton revenu après 20 s
        assert bucket.take("autre-ip", now=0.0) == 0.0         # limite par adresse

    def test_limitation_connexion_429(self, app):
        from fastapi.testclient import TestClient
        from baolsec_api.middleware.security import SecurityMiddleware
        # Recherche du middleware de sécurité dans la pile pour réduire sa limite de connexion
        app.user_middleware = [m for m in app.user_middleware if m.cls is not SecurityMiddleware]
        app.add_middleware(SecurityMiddleware, login_per_minute=2)
        with TestClient(app) as c, patch("baolsec_api.database._pool", make_fake_pool([])):
            codes = [c.post("/api/v1/auth/login", data={"username": "x", "password": "y"}).status_code
                     for _ in range(3)]
        assert codes[:2] == [401, 401] and codes[2] == 429


# ── ES-01 : verrouillage après échecs ─────────────────────────────────────────

class TestVerrouillage:
    def _row(self, failed=0, locked_until=None, active=True):
        return (uuid.uuid4(), "ana@test.local", hash_password("BonMotDePasse1"), "Analyste", active,
                "ana", failed, locked_until)

    def test_echec_incremente_le_compteur(self, client):
        pool, conn, _ = _pool_with(fetchone=self._row(failed=1))
        with patch("baolsec_api.database._pool", pool), patch("baolsec_api.audit.record", AsyncMock()):
            resp = client.post("/api/v1/auth/login", data={"username": "ana", "password": "faux"})
        assert resp.status_code == 401
        sql, params = conn.execute.call_args.args
        assert "failed_attempts = %s" in sql and params[0] == 2

    def test_dernier_echec_verrouille_423(self, client):
        _auth.max_failed_attempts, _auth.lockout_minutes = 5, 15
        pool, conn, _ = _pool_with(fetchone=self._row(failed=4))
        with patch("baolsec_api.database._pool", pool), patch("baolsec_api.audit.record", AsyncMock()) as rec:
            resp = client.post("/api/v1/auth/login", data={"username": "ana", "password": "faux"})
        assert resp.status_code == 423
        assert "locked_until" in conn.execute.call_args.args[0]
        assert rec.await_args.kwargs["outcome"] == "refus"     # tentative tracée (ES-07)

    def test_compte_verrouille_refuse_meme_bon_mot_de_passe(self, client):
        pool, _, _ = _pool_with(fetchone=self._row(locked_until=NOW + timedelta(minutes=10)))
        with patch("baolsec_api.database._pool", pool), patch("baolsec_api.audit.record", AsyncMock()):
            resp = client.post("/api/v1/auth/login", data={"username": "ana", "password": "BonMotDePasse1"})
        assert resp.status_code == 423

    def test_succes_remet_a_zero_et_trace(self, client):
        pool, conn, _ = _pool_with(fetchone=self._row(failed=3))
        with patch("baolsec_api.database._pool", pool), patch("baolsec_api.audit.record", AsyncMock()) as rec:
            resp = client.post("/api/v1/auth/login", data={"username": "ana", "password": "BonMotDePasse1"})
        assert resp.status_code == 200 and resp.json()["access_token"]
        assert "failed_attempts = 0" in conn.execute.call_args.args[0]
        assert rec.await_args.kwargs["action"] == "auth.login" and rec.await_args.kwargs["outcome"] == "succes"


# ── ES-07 : audit monté et ciblé ──────────────────────────────────────────────

class TestAudit:
    def test_modification_tracee(self, client, admin_headers):
        with patch("baolsec_api.database._pool", make_fake_pool([SOURCE_ROW])), \
             patch("baolsec_api.audit.record", AsyncMock()) as rec:
            client.delete(f"/api/v1/sources/{SOURCE_ROW['id']}", headers=admin_headers)
        kwargs = rec.await_args.kwargs
        assert kwargs["action"].startswith("DELETE /api/v1/sources/")
        assert kwargs["target_type"] == "sources" and kwargs["target_id"] == str(SOURCE_ROW["id"])
        assert kwargs["outcome"] == "succes"

    def test_lecture_non_tracee(self, client, analyst_headers):
        with patch("baolsec_api.database._pool", make_fake_pool([SOURCE_ROW])), \
             patch("baolsec_api.audit.record", AsyncMock()) as rec:
            client.get("/api/v1/sources", headers=analyst_headers)
        rec.assert_not_awaited()

    def test_refus_trace_en_refus(self, client, analyst_headers):
        with patch("baolsec_api.database._pool", make_fake_pool([SOURCE_ROW])), \
             patch("baolsec_api.audit.record", AsyncMock()) as rec:
            client.delete(f"/api/v1/sources/{SOURCE_ROW['id']}", headers=analyst_headers)
        assert rec.await_args.kwargs["outcome"] == "refus"


# ── Commandes vers le service Incidents : conformité au contrat incident_command/v1 ──

class TestCommandes:
    def _send(self):
        return AsyncMock(return_value={"contract": "incident_command_result/v1", "result": "acceptee"})

    def test_statut_et_commentaire_separes(self, client, analyst_headers):
        iid = uuid.uuid4()
        send = self._send()
        with patch("baolsec_api.commandclient.send_command", send):
            resp = client.post(f"/api/v1/incidents/{iid}/status", headers={**analyst_headers, "Idempotency-Key": str(uuid.uuid4())},
                               json={"state": "en_cours", "comment": "prise en charge"})
        assert resp.status_code == 200
        calls = [c.kwargs for c in send.await_args_list]
        assert calls[0]["command_type"] == "changer_statut" and calls[0]["payload"] == {"status": "en_cours"}
        assert calls[1]["command_type"] == "commenter" and calls[1]["payload"] == {"body": "prise en charge"}

    def test_clore_avec_motif(self, client, analyst_headers):
        send = self._send()
        with patch("baolsec_api.commandclient.send_command", send):
            client.post(f"/api/v1/incidents/{uuid.uuid4()}/status", headers=analyst_headers,
                        json={"state": "clos", "comment": "faux positif"})
        assert send.await_args.kwargs["command_type"] == "clore"
        assert send.await_args.kwargs["payload"] == {"reason": "faux positif"}

    @pytest.mark.parametrize("path", ["/api/v1/incidents/{id}/assign", "/api/v1/alerts/{aid}/assign"])
    def test_assignation_assignee_id(self, client, analyst_headers, path):
        user = str(uuid.uuid4())
        send = self._send()
        url = path.format(id=uuid.uuid4(), aid="a" * 64)
        with patch("baolsec_api.commandclient.send_command", send):
            assert client.post(url, headers=analyst_headers, json={"assigned_to": user}).status_code == 200
        assert send.await_args.kwargs["payload"] == {"assignee_id": user}

    def test_assignation_identifiant_invalide_422(self, client, analyst_headers):
        with patch("baolsec_api.commandclient.send_command", self._send()):
            resp = client.post(f"/api/v1/incidents/{uuid.uuid4()}/assign", headers=analyst_headers,
                               json={"assignee_id": "pas-un-uuid"})
        assert resp.status_code == 422

    def test_reouverture_c5(self, client, analyst_headers):
        send = self._send()
        with patch("baolsec_api.commandclient.send_command", send):
            assert client.post(f"/api/v1/incidents/{uuid.uuid4()}/reopen", headers=analyst_headers,
                               json={}).status_code == 200
        assert send.await_args.kwargs["command_type"] == "rouvrir"


# ── Sources : erreurs de saisie et refus de la base traduits en 422/409 ──────

class TestSources:
    def test_ip_invalide_422(self, client, admin_headers):
        with patch("baolsec_api.database._pool", make_fake_pool([SOURCE_ROW])):
            resp = client.post("/api/v1/sources", headers=admin_headers,
                               json={"name": "x", "type": "linux", "config": {"ip_address": "pas-une-ip"}})
        assert resp.status_code == 422

    def test_troisieme_identifiant_409(self, client, admin_headers):
        calls = {"n": 0}

        async def execute(*_a, **_k):
            calls["n"] += 1
            if calls["n"] >= 2:
                exc = Exception("la source a déjà deux identifiants actifs")
                exc.sqlstate = "23514"
                raise exc
        pool, _, _ = _pool_with(fetchone={"id": SOURCE_ROW["id"]}, execute=execute)
        with patch("baolsec_api.database._pool", pool):
            resp = client.post(f"/api/v1/sources/{SOURCE_ROW['id']}/credentials", headers=admin_headers)
        assert resp.status_code == 409
        assert "deux identifiants actifs" in resp.json()["detail"]


# ── Dépendances externes indisponibles : messages explicites ─────────────────

class TestIndisponibilites:
    def test_dlq_broker_injoignable_503(self, client, admin_headers):
        from baolsec_api import broker
        with patch.object(broker, "dlq_list", AsyncMock(side_effect=broker.BrokerUnavailable("x"))):
            resp = client.get("/api/v1/dlq", headers=admin_headers)
        assert resp.status_code == 503

    def test_dlq_reservee_admin(self, client, analyst_headers):
        assert client.get("/api/v1/dlq", headers=analyst_headers).status_code == 403

    def test_evenements_sans_opensearch_503(self, client, analyst_headers):
        from opensearchpy import exceptions as osx
        from baolsec_api.routers import search
        fake = MagicMock()
        fake.search = AsyncMock(side_effect=osx.ConnectionError("N/A", "refus", Exception()))
        with patch.object(search, "_os_client", fake):
            resp = client.get("/api/v1/events?user=alice", headers=analyst_headers)
        assert resp.status_code == 503
        assert "indisponible" in resp.json()["detail"]


# ── Utilisateurs : garde-fous ─────────────────────────────────────────────────

class TestUtilisateurs:
    def test_ne_peut_pas_se_retrograder(self, client):
        uid = str(uuid.uuid4())
        _auth.configure("test-secret-key-1234567890abcdef", expire_minutes=60)
        from baolsec_api.models import UserRole
        token = _auth.create_token(uid, "admin@test.local", UserRole.ADMIN)
        with patch("baolsec_api.database._pool", make_fake_pool([])):
            resp = client.patch(f"/api/v1/users/{uid}", headers={"Authorization": f"Bearer {token}"},
                                json={"role": "ANALYST"})
        assert resp.status_code == 400


# ── Supervision : état global (EF-12) ────────────────────────────────────────

class TestEtatGlobal:
    """OpenSearch seul en panne : « dégradé » (la chaîne continue) ; base ou broker : « indisponible »."""

    @staticmethod
    def _run(monkeypatch, pg="up", os_="up", nats="up"):
        import asyncio
        from baolsec_api.routers import system

        async def comp(name, st):
            return {"name": name, "kind": "donnees", "status": st, "latency_ms": 1, "detail": ""}

        async def broker():
            return (await comp("nats-jetstream", nats), [])

        monkeypatch.setattr(system, "_targets", {})
        monkeypatch.setattr(system, "_postgres", lambda: comp("postgresql", pg))
        monkeypatch.setattr(system, "_opensearch", lambda: comp("opensearch", os_))
        monkeypatch.setattr(system, "_broker", broker)
        return asyncio.run(system.platform_health(_user=None))["status"]

    def test_tout_va_bien(self, monkeypatch):
        assert self._run(monkeypatch) == "up"

    def test_opensearch_en_panne_degrade(self, monkeypatch):
        assert self._run(monkeypatch, os_="down") == "degraded"

    def test_base_en_panne_indisponible(self, monkeypatch):
        assert self._run(monkeypatch, pg="down") == "down"

    def test_broker_en_panne_indisponible(self, monkeypatch):
        assert self._run(monkeypatch, nats="down") == "down"


# ── Journal d'audit lisible (27/11/2026) ─────────────────────────────────────

class TestAuditLisible:
    def test_resume_sans_secret(self):
        from baolsec_api.middleware.audit import summarize_changes
        out = summarize_changes({"password": "Secret-123", "role": "ADMIN", "email": "a@b.sn",
                                 "definition_yaml": "id: X", "body": "texte du commentaire",
                                 "config": {"transport": "https", "tags": ["x"]}, "token": "bsk_x"})
        assert "Secret-123" not in str(out) and "bsk_x" not in str(out)
        assert out["password_changed"] is True and out["definition_changed"] is True
        assert out["comment_length"] == len("texte du commentaire")
        assert out["role"] == "ADMIN" and out["config"] == {"transport": "https"}

    def test_motif_de_refus(self):
        from baolsec_api.middleware.audit import _reason
        assert _reason(b'{"detail": "Droits insuffisants"}') == "Droits insuffisants"
        assert _reason(b'{"detail": [{"loc": ["body", "ip_address"], "msg": "Value error, Adresse IP invalide", "type": "value_error"}]}') \
            == "Adresse IP invalide"
        assert _reason(b'{"detail": [{"loc": ["body", "name"], "msg": "Field required", "type": "missing"}]}') \
            == "information obligatoire manquante : nom"
        assert _reason(b'{"detail": [{"loc": ["query", "limit"], "msg": "Input should be less than or equal to 200", "type": "less_than_equal"}]}') \
            == "valeur non valable pour « nombre de résultats »"
        assert _reason(b"pas du json") is None
