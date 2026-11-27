"""Schéma PostgreSQL de BaolSec (C4) : migrations, contraintes et droits des comptes de service.

Nécessite TEST_POSTGRES_DSN : connexion administrateur au serveur PostgreSQL, par exemple
postgresql://postgres:<mot de passe>@localhost:5432/postgres (make test-db la construit depuis .env).
Le test crée puis supprime la base baolsec_schema_test ; la base baolsec n'est pas modifiée.
Les comptes de service sont communs au serveur : les tests les utilisent avec SET ROLE, sans mot de passe.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest

ROOT = Path(__file__).resolve().parents[3]
DB_DIR = ROOT / "infrastructure" / "database"
ADMIN_DSN = os.environ.get("TEST_POSTGRES_DSN")
DB = "baolsec_schema_test"
pytestmark = pytest.mark.skipif(not ADMIN_DSN, reason="TEST_POSTGRES_DSN non défini")

TABLES = {
    "acces": {"roles", "permissions", "role_permissions", "users", "user_sessions", "audit_log"},
    "config": {"sources", "source_credentials", "rules", "rule_versions", "rule_requirements", "settings"},
    "incidents": {"alert_state", "incidents", "incident_alerts", "incident_timeline", "incident_comments", "incident_commands", "incident_outbox"},
    "couverture": {"coverage_state", "coverage_state_history", "coverage_stats", "coverage_affected_rules", "coverage_batches"},
}


def db_url(dsn: str, db: str) -> str:
    p = urlsplit(dsn)
    return urlunsplit((p.scheme, p.netloc, f"/{db}", p.query, ""))


def alembic(target: str, url: str) -> None:
    env = {**os.environ, "DATABASE_ADMIN_URL": url.replace("postgresql://", "postgresql+psycopg://", 1)}
    subprocess.run([sys.executable, "-m", "alembic", "-c", str(DB_DIR / "alembic.ini"), *target.split()],
                   check=True, env=env, cwd=DB_DIR, capture_output=True, timeout=120)


@pytest.fixture(scope="module")
def url():
    with psycopg.connect(ADMIN_DSN, autocommit=True) as admin:
        admin.execute(f"DROP DATABASE IF EXISTS {DB} WITH (FORCE)")
        admin.execute(f"CREATE DATABASE {DB}")
    u = db_url(ADMIN_DSN, DB)
    alembic("upgrade head", u)
    yield u
    with psycopg.connect(ADMIN_DSN, autocommit=True) as admin:
        admin.execute(f"DROP DATABASE IF EXISTS {DB} WITH (FORCE)")


@pytest.fixture
def conn(url):
    """Connexion administrateur dans une transaction annulée à la fin du test."""
    with psycopg.connect(url) as c:
        yield c
        c.rollback()


def source(conn, name=None) -> str:
    sid = str(uuid.uuid4())
    conn.execute("INSERT INTO config.sources (id, name, source_type, transport) VALUES (%s, %s, 'linux', 'https')",
                 (sid, name or f"src-{sid[:8]}"))
    return sid


def rule(conn) -> str:
    rid = str(uuid.uuid4())
    conn.execute("INSERT INTO config.rules (id, name, rule_type, severity) VALUES (%s, %s, 'window', 'moyenne')",
                 (rid, f"R-{rid[:8]}"))
    return rid


def user(conn) -> str:
    uid = str(uuid.uuid4())
    conn.execute("INSERT INTO acces.users (id, username, password_hash, role_id) "
                 "SELECT %s, %s, 'x', id FROM acces.roles WHERE name = 'Analyste'", (uid, f"u-{uid[:8]}"))
    return uid


def alert(conn, rid) -> str:
    aid = uuid.uuid4().hex
    conn.execute("INSERT INTO incidents.alert_state (alert_id, rule_id, severity, triggered_at) VALUES (%s, %s, 'moyenne', now())",
                 (aid, rid))
    return aid


def incident(conn) -> str:
    iid = str(uuid.uuid4())
    conn.execute("INSERT INTO incidents.incidents (id, title, severity, correlation_context, opened_at, last_activity_at) "
                 "VALUES (%s, 't', 'moyenne', '{}', now(), now())", (iid,))
    return iid


# ---------------------------------------------------------------- migrations

def test_quatre_schemas_et_tables_de_c4(conn):
    rows = conn.execute("SELECT table_schema, table_name FROM information_schema.tables "
                        "WHERE table_schema = ANY(%s)", (list(TABLES),)).fetchall()
    found: dict[str, set] = {}
    for schema, table in rows:
        found.setdefault(schema, set()).add(table)
    assert found == TABLES


def test_roles_et_parametres_initiaux(conn):
    assert {r[0] for r in conn.execute("SELECT name FROM acces.roles")} == {"Administrateur", "Analyste"}
    settings = dict(conn.execute("SELECT key, value FROM config.settings").fetchall())
    assert settings["correlation.window_minutes"] == 30 and settings["correlation.max_incident_hours"] == 24


def test_retour_arriere_puis_reapplication(url):
    alembic("downgrade base", url)
    with psycopg.connect(url) as c:
        assert c.execute("SELECT count(*) FROM pg_namespace WHERE nspname = ANY(%s)", (list(TABLES),)).fetchone()[0] == 0
    alembic("upgrade head", url)
    with psycopg.connect(url) as c:
        # Tête de la chaîne : la révision la plus récente du dépôt (et non un numéro figé, qui
        # devenait faux à chaque nouvelle migration : 0007, puis 0008 et 0009 en C26).
        head = max(f.name[:4] for f in (DB_DIR / "migrations" / "versions").glob("[0-9][0-9][0-9][0-9]_*.py"))
        assert c.execute("SELECT version_num FROM alembic_version").fetchone()[0] == head


# ---------------------------------------------------------------- contraintes (C4 4.5)

def test_une_alerte_un_seul_incident(conn):
    a = alert(conn, rule(conn))
    i1, i2 = incident(conn), incident(conn)
    conn.execute("INSERT INTO incidents.incident_alerts (incident_id, alert_id, criteria) VALUES (%s, %s, '{}')", (i1, a))
    with pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute("INSERT INTO incidents.incident_alerts (incident_id, alert_id, criteria) VALUES (%s, %s, '{}')", (i2, a))


def test_commande_avec_une_cible(conn):
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute("INSERT INTO incidents.incident_commands (command_id, command_type, issued_by, result) "
                     "VALUES (%s, 'commenter', %s, 'acceptee')", (str(uuid.uuid4()), user(conn)))


def test_incident_clos_a_une_date_de_cloture(conn):
    i = incident(conn)
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute("UPDATE incidents.incidents SET status = 'clos' WHERE id = %s", (i,))


def test_deux_identifiants_actifs_au_plus(conn):
    s = source(conn)
    for h in ("a", "b"):
        conn.execute("INSERT INTO config.source_credentials (source_id, credential_type, secret_hash) VALUES (%s, 'token', %s)", (s, h))
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute("INSERT INTO config.source_credentials (source_id, credential_type, secret_hash) VALUES (%s, 'token', 'c')", (s,))


def test_rotation_apres_revocation(conn):
    s = source(conn)
    for h in ("a", "b"):
        conn.execute("INSERT INTO config.source_credentials (source_id, credential_type, secret_hash) VALUES (%s, 'token', %s)", (s, h))
    conn.execute("UPDATE config.source_credentials SET revoked_at = now() WHERE source_id = %s AND secret_hash = 'a'", (s,))
    conn.execute("INSERT INTO config.source_credentials (source_id, credential_type, secret_hash) VALUES (%s, 'token', 'c')", (s,))


# ---------------------------------------------------------------- droits des comptes (C4 2.2)

def allowed(conn, role: str, statement: str, params=()) -> bool:
    conn.execute("SAVEPOINT droit")
    try:
        conn.execute(f"SET LOCAL ROLE {role}")
        conn.execute(statement, params)
        return True
    except psycopg.errors.InsufficientPrivilege:
        return False
    finally:
        conn.execute("ROLLBACK TO SAVEPOINT droit")


def test_droits_par_compte(conn):
    s, r = source(conn), rule(conn)
    a = alert(conn, r)
    ins_alert = ("INSERT INTO incidents.alert_state (alert_id, rule_id, severity, triggered_at) VALUES (%s, %s, 'faible', now())",
                 (uuid.uuid4().hex, r))
    ins_stat = ("INSERT INTO couverture.coverage_stats (source_id, bucket_start) VALUES (%s, now())", (s,))
    upd_source = ("UPDATE config.sources SET host = 'x' WHERE id = %s", (s,))
    cases = [
        ("svc_passerelle", "SELECT secret_hash FROM config.source_credentials", (), True),
        ("svc_passerelle", *upd_source, False),
        ("svc_passerelle", "SELECT 1 FROM config.rules", (), False),
        ("svc_normalisation", "SELECT host, criticality FROM config.sources", (), True),
        ("svc_normalisation", "SELECT secret_hash FROM config.source_credentials", (), False),
        ("svc_detection", "SELECT definition_yaml FROM config.rule_versions", (), True),
        ("svc_detection", *ins_alert, False),
        ("svc_detection", "SELECT 1 FROM config.source_credentials", (), False),
        ("svc_incidents", *ins_alert, True),
        ("svc_incidents", "UPDATE incidents.alert_state SET status = 'en_cours' WHERE alert_id = %s", (a,), True),
        ("svc_incidents", "SELECT value FROM config.settings", (), True),
        ("svc_incidents", "SELECT username FROM acces.users", (), True),
        ("svc_incidents", "SELECT password_hash FROM acces.users", (), False),
        ("svc_incidents", "DELETE FROM incidents.alert_state WHERE alert_id = %s", (a,), False),
        ("svc_incidents", *upd_source, False),
        ("svc_incidents", *ins_stat, False),
        ("svc_couverture", *ins_stat, True),
        ("svc_couverture", "SELECT required_fields FROM config.rule_requirements", (), True),
        ("svc_couverture", *ins_alert, False),
        ("svc_api", *upd_source, True),
        ("svc_api", "DELETE FROM config.sources WHERE id = %s", (s,), False),
        ("svc_api", "INSERT INTO acces.audit_log (actor_username, action, target_type, target_id, outcome) "
                    "VALUES ('a', 'b', 'c', 'd', 'succes')", (), True),
        ("svc_api", "UPDATE acces.audit_log SET action = 'x'", (), False),
        ("svc_api", "DELETE FROM acces.audit_log", (), False),
        ("svc_api", "SELECT 1 FROM incidents.incidents", (), True),
        ("svc_api", *ins_alert, False),
    ]
    wrong = [(role, stmt.split(" (")[0][:60], expected) for role, stmt, params, expected in cases
             if allowed(conn, role, stmt, params) != expected]
    assert wrong == [], f"droits inattendus (compte, requête, attendu) : {wrong}"


# ---------------------------------------------------------------- référentiel de développement et services

def test_copie_du_referentiel_et_lecture_par_les_services(url, tmp_path):
    sid = str(uuid.uuid4())
    path = tmp_path / "sources.json"
    path.write_text(json.dumps({"sources": [{
        "id": sid, "name": f"dev-{sid[:8]}", "source_type": "linux", "transport": "https", "ingestion_mode": "direct",
        "host": "srv-test", "criticality": "elevee", "is_enabled": True,
        "credentials": [{"credential_type": "token", "secret_hash": "f" * 64}]}]}))
    env = {**os.environ, "DATABASE_ADMIN_URL": url, "SOURCES_FILE": str(path)}
    for _ in range(2):    # relancé sans doublon
        subprocess.run([sys.executable, str(DB_DIR / "seed_dev.py")], check=True, env=env, capture_output=True, timeout=60)

    sys.path[:0] = [str(ROOT / "services" / "ingestion-gateway" / "src"), str(ROOT / "services" / "normalization-worker" / "src")]
    from gateway.sources_cache.postgres import QUERY as GATEWAY_QUERY
    from normalizer.sources.postgres import QUERY as NORMALIZER_QUERY

    with psycopg.connect(url) as c:
        assert c.execute("SELECT count(*) FROM config.source_credentials WHERE source_id = %s", (sid,)).fetchone()[0] == 1
        c.execute("SET ROLE svc_passerelle")
        assert any(r[0] == sid for r in c.execute(GATEWAY_QUERY).fetchall())
        c.execute("RESET ROLE")
        c.execute("SET ROLE svc_normalisation")
        row = next(r for r in c.execute(NORMALIZER_QUERY).fetchall() if r[0] == sid)
        assert "srv-test" in row and "elevee" in row


# ---------------------------------------------------------------- C26 : migrations 0008 et 0009

def test_metadonnees_de_source_0008(conn):
    """Colonnes lues et écrites par l'API (GET/POST /sources) : absentes avant 0008, d'où une erreur 500."""
    sid = source(conn)
    conn.execute("UPDATE config.sources SET hostname = 'web01', ip_address = '10.0.0.5', environment = 'production', "
                 "tags = ARRAY['dmz'], responsible = 'SOC' WHERE id = %s", (sid,))
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute("UPDATE config.sources SET environment = 'inconnu' WHERE id = %s", (sid,))


def test_meme_jeton_actif_deux_fois_refuse_0009(conn):
    s1, s2 = source(conn), source(conn)
    conn.execute("INSERT INTO config.source_credentials (source_id, credential_type, secret_hash) "
                 "VALUES (%s, 'token', 'h-commun')", (s1,))
    with pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute("INSERT INTO config.source_credentials (source_id, credential_type, secret_hash) "
                     "VALUES (%s, 'token', 'h-commun')", (s2,))


def test_jeton_revoque_ne_bloque_pas_0009(conn):
    s1, s2 = source(conn), source(conn)
    conn.execute("INSERT INTO config.source_credentials (source_id, credential_type, secret_hash, revoked_at) "
                 "VALUES (%s, 'token', 'h-revoque', now())", (s1,))
    conn.execute("INSERT INTO config.source_credentials (source_id, credential_type, secret_hash) "
                 "VALUES (%s, 'token', 'h-revoque')", (s2,))
