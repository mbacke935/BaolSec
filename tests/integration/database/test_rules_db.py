"""Chargement des règles dans PostgreSQL et lecture par detection-worker (C12).

Nécessite TEST_POSTGRES_DSN (voir test_schema.py). Crée puis supprime la base baolsec_rules_test.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import psycopg
import pytest

from test_schema import ADMIN_DSN, alembic, db_url

ROOT = Path(__file__).resolve().parents[3]
DB = "baolsec_rules_test"
pytestmark = pytest.mark.skipif(not ADMIN_DSN, reason="TEST_POSTGRES_DSN non défini")
sys.path.insert(0, str(ROOT / "services" / "detection-worker" / "src"))


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


def load(url: str, directory: Path) -> str:
    env = {**os.environ, "DATABASE_ADMIN_URL": url, "RULES_DIR": str(directory)}
    r = subprocess.run([sys.executable, str(ROOT / "infrastructure" / "database" / "load_rules.py")],
                       env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_meme_espace_de_noms_que_le_service():
    sys.path.insert(0, str(ROOT / "infrastructure" / "database"))
    import load_rules
    from detector.rules.model import RULE_NAMESPACE
    assert load_rules.RULE_NAMESPACE == RULE_NAMESPACE


async def test_chargement_versions_et_lecture_par_le_service(url, tmp_path):
    from detector.rules import PostgresRules, RulesCache, RuleValidator, rule_uuid
    for f in (ROOT / "rules").glob("*.yml"):
        shutil.copy(f, tmp_path / f.name)
    n = len(list(tmp_path.glob("*.yml")))
    assert f"créées : {n}" in load(url, tmp_path)
    assert f"inchangées : {n}" in load(url, tmp_path)

    rule_file = tmp_path / "AUTH-001.yml"
    rule_file.write_text(rule_file.read_text(encoding="utf-8").replace("threshold: 5", "threshold: 6"), encoding="utf-8")
    assert "nouvelle version : 1" in load(url, tmp_path)

    with psycopg.connect(url) as c:
        row = c.execute("SELECT current_version, rule_type::text FROM config.rules WHERE id = %s", (rule_uuid("AUTH-001"),)).fetchone()
        assert row == (2, "window")
        reqs = c.execute("SELECT source_type::text FROM config.rule_requirements WHERE rule_id = %s ORDER BY 1",
                         (rule_uuid("AUTH-001"),)).fetchall()
        assert [r[0] for r in reqs] == ["linux", "windows"]

    # Connexion administrateur qui prend le rôle svc_detection dès l'ouverture : mêmes droits que le service,
    # sans toucher au mot de passe du compte (commun au serveur).
    sep = "&" if "?" in url else "?"
    cache = RulesCache(PostgresRules(f"{url}{sep}options=-c%20role%3Dsvc_detection"), RuleValidator(ROOT / "shared" / "contracts"))
    await cache.refresh()
    auth = next(r for r in cache.rules if r.code == "AUTH-001")
    assert auth.version == 2 and auth.threshold == 6 and cache.rejected == {}


def test_regle_invalide_rien_n_est_ecrit(url, tmp_path):
    (tmp_path / "BAD-001.yml").write_text("id: BAD-001\nname: x\n", encoding="utf-8")
    env = {**os.environ, "DATABASE_ADMIN_URL": url, "RULES_DIR": str(tmp_path)}
    r = subprocess.run([sys.executable, str(ROOT / "infrastructure" / "database" / "load_rules.py")],
                       env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode != 0 and "rien n'a été écrit" in r.stderr


def test_compte_detection_lecture_seule(url):
    sep = "&" if "?" in url else "?"
    with psycopg.connect(f"{url}{sep}options=-c%20role%3Dsvc_detection") as c:
        assert c.execute("SELECT current_user").fetchone()[0] == "svc_detection"
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("UPDATE config.rules SET is_enabled = false")
