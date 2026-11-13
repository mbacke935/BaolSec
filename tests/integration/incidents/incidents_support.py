"""Outils communs aux tests d'intégration du service Incidents (C15)."""
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "incident-builder" / "src"))

CONTRACTS = ROOT / "shared" / "contracts"
DB_DIR = ROOT / "infrastructure" / "database"
ADMIN_DSN = os.environ.get("TEST_POSTGRES_DSN")
DB = "baolsec_incidents_test"
RESULT = Draft202012Validator(json.loads((CONTRACTS / "incident_command" / "v1" / "result.schema.json").read_text()),
                              format_checker=FormatChecker())
ALERT_EXAMPLE = json.loads((CONTRACTS / "alert" / "v1" / "examples" / "auth001_force_brute.json").read_text())


def db_url(dsn: str, db: str, role: str | None = None) -> str:
    """Même serveur, autre base ; `role` ouvre les connexions sous ce compte (SET ROLE, sans mot de passe)."""
    p = urlsplit(dsn)
    query = f"options=-c%20role%3D{role}" if role else p.query
    return urlunsplit((p.scheme, p.netloc, f"/{db}", query, ""))


def create_database() -> str:
    """Crée la base de test, applique les migrations Alembic et charge les règles du dépôt (config.rules)."""
    with psycopg.connect(ADMIN_DSN, autocommit=True) as admin:
        admin.execute(f"DROP DATABASE IF EXISTS {DB} WITH (FORCE)")
        admin.execute(f"CREATE DATABASE {DB}")
    url = db_url(ADMIN_DSN, DB)
    env = {**os.environ, "DATABASE_ADMIN_URL": url.replace("postgresql://", "postgresql+psycopg://", 1)}
    subprocess.run([sys.executable, "-m", "alembic", "-c", str(DB_DIR / "alembic.ini"), "upgrade", "head"],
                   check=True, env=env, cwd=DB_DIR, capture_output=True, timeout=120)
    subprocess.run([sys.executable, str(DB_DIR / "load_rules.py")], check=True, env={**os.environ, "DATABASE_ADMIN_URL": url},
                   cwd=ROOT, capture_output=True, timeout=120)
    return url


def drop_database() -> None:
    with psycopg.connect(ADMIN_DSN, autocommit=True) as admin:
        admin.execute(f"DROP DATABASE IF EXISTS {DB} WITH (FORCE)")


def new_user(url: str, *, active: bool = True) -> uuid.UUID:
    uid = uuid.uuid4()
    with psycopg.connect(url) as c:
        c.execute("INSERT INTO acces.users (id, username, password_hash, role_id, is_active) "
                  "SELECT %s, %s, 'x', id, %s FROM acces.roles WHERE name = 'Analyste'", (uid, f"u-{uid.hex[:8]}", active))
    return uid


def alert_document(*, rule: str = "AUTH-001", severity: str = "elevee", at: str | None = None) -> dict:
    scores = {"faible": 1, "moyenne": 2, "elevee": 3, "critique": 4}
    doc = copy.deepcopy(ALERT_EXAMPLE)
    doc["event"]["id"] = uuid.uuid4().hex + uuid.uuid4().hex
    doc["rule"]["id"] = rule
    doc["baolsec"]["severity"] = {"label": severity, "score": scores[severity]}
    if at:
        doc["@timestamp"] = at
    return doc


def command(ctype: str, alert_id: str, issuer: uuid.UUID, payload: dict, command_id: uuid.UUID | None = None) -> dict:
    return {"contract": "incident_command/v1", "command_id": str(command_id or uuid.uuid4()), "command_type": ctype,
            "target": {"alert_id": alert_id}, "issued_by": {"user_id": str(issuer), "username": "analyste"},
            "issued_at": "2026-11-12T10:00:00Z", "payload": payload}


def status_command(alert_id, issuer, status, command_id=None) -> dict:
    return command("statut_alerte", alert_id, issuer, {"status": status}, command_id)


def assign_command(alert_id, issuer, assignee, command_id=None) -> dict:
    return command("assigner_alerte", alert_id, issuer, {"assignee_id": None if assignee is None else str(assignee)}, command_id)


def rows(url: str, query: str, params=()) -> list[tuple]:
    with psycopg.connect(url) as c:
        return c.execute(query, params).fetchall()
