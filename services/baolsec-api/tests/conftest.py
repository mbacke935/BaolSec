"""Fixtures partagées pour les tests de l'API BaolSec (C20)."""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from baolsec_api import auth as _auth
from baolsec_api.main import create_app
from baolsec_api.models import TokenPayload, UserRole


# ── Token helpers ─────────────────────────────────────────────────────────────

def _make_token(role: UserRole = UserRole.ANALYST) -> str:
    _auth.configure("test-secret-key-1234567890abcdef", expire_minutes=60)
    user_id = str(uuid.uuid4())
    return _auth.create_token(user_id, f"{role.value.lower()}@test.local", role)


def _admin_token() -> str:
    return _make_token(UserRole.ADMIN)


def _analyst_token() -> str:
    return _make_token(UserRole.ANALYST)


# ── Fake DB connection ─────────────────────────────────────────────────────────

class FakeCursor:
    def __init__(self, rows=None):
        self._rows = rows or []
        self._index = 0

    async def execute(self, *args, **kwargs):
        pass

    async def fetchone(self):
        return self._rows[0] if self._rows else None

    async def fetchall(self):
        return list(self._rows)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass


class FakeConn:
    def __init__(self, rows=None):
        self._rows = rows or []

    def cursor(self, row_factory=None):
        return FakeCursor(self._rows)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass


# ── App fixture ───────────────────────────────────────────────────────────────

@asynccontextmanager
async def test_lifespan(_app) -> AsyncIterator[None]:
    """Lifespan isolé : aucun accès aux services externes durant les tests."""
    yield


@pytest.fixture
def app():
    """Crée une instance de l'app avec le pool mocké."""
    _auth.configure("test-secret-key-1234567890abcdef", expire_minutes=60)
    test_app = create_app()
    test_app.router.lifespan_context = test_lifespan
    return test_app


@pytest.fixture
def client(app):
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture
def admin_headers():
    return {"Authorization": f"Bearer {_admin_token()}"}


@pytest.fixture
def analyst_headers():
    return {"Authorization": f"Bearer {_analyst_token()}"}
