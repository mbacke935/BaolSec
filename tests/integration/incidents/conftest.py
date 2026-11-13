from __future__ import annotations

import pytest

from incidents_support import ADMIN_DSN, DB, create_database, db_url, drop_database

if ADMIN_DSN is None:
    collect_ignore_glob = []


@pytest.fixture(scope="session")
def database():
    """URL administrateur d'une base de test migrée, avec les règles du dépôt chargées."""
    if not ADMIN_DSN:
        pytest.skip("TEST_POSTGRES_DSN non défini")
    url = create_database()
    yield url
    drop_database()


@pytest.fixture
async def db(database):
    """Pool du service, connecté sous le compte svc_incidents : les droits réels du service sont exercés."""
    from incidents.repositories import Database
    pool = Database(db_url(ADMIN_DSN, DB, role="svc_incidents"), max_size=5, timeout_s=5)
    await pool.open()
    yield pool
    await pool.close()
