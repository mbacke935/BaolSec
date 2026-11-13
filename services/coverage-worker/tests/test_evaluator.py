"""Tests unitaires de la logique d'évaluation des états de couverture (C17 axe 2).

Tous les tests sont purement en mémoire : aucun accès PostgreSQL ni NATS.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from coverage.evaluator import (
    COMPLETENESS_THRESHOLD,
    MIN_RECEIVED_FOR_COMPLETENESS,
    SourceStateEvaluator,
    evaluate_state,
)
from coverage.repositories import (
    CoverageStateRow,
    DatabaseUnavailable,
    SourceConfig,
)

# ------------------------------------------------------------------ helpers

NOW = datetime(2026, 11, 13, 10, 0, 0, tzinfo=timezone.utc)
SRC_ID = uuid.uuid4()
SILENCE_S = 600  # silence_threshold par défaut (10 min)


def _recent(offset_s: int = 60) -> datetime:
    """Horodatage récent (il y a offset_s secondes)."""
    return NOW - timedelta(seconds=offset_s)


def _old(offset_s: int = 1200) -> datetime:
    """Horodatage dépassant le seuil de silence (il y a offset_s secondes)."""
    return NOW - timedelta(seconds=offset_s)


def _eval(
    *,
    active: bool = True,
    last_received_at=None,
    received_count: int = 0,
    normalized_count: int = 0,
    silence_threshold_s: int = SILENCE_S,
) -> tuple[str, str]:
    return evaluate_state(
        active=active,
        last_received_at=last_received_at,
        received_count=received_count,
        normalized_count=normalized_count,
        silence_threshold_s=silence_threshold_s,
        now=NOW,
    )


# ------------------------------------------------------------------ tests de evaluate_state

def test_source_inactive_est_desactivee():
    state, reason = _eval(active=False)
    assert state == "DESACTIVEE"
    assert "désactivée" in reason


def test_aucun_evenement_est_inconnue():
    state, _ = _eval(last_received_at=None)
    assert state == "INCONNUE"


def test_evenement_recent_est_active():
    state, _ = _eval(last_received_at=_recent(30), received_count=5, normalized_count=5)
    assert state == "ACTIVE"


def test_dernier_evenement_vieux_est_silencieuse():
    state, reason = _eval(last_received_at=_old(1200))
    assert state == "SILENCIEUSE"
    assert "silence" in reason.lower() or "1200" in reason


def test_seuil_silence_personnalise():
    # avec un seuil de 300s, 400s d'inactivité → SILENCIEUSE
    state, _ = _eval(last_received_at=_recent(400), silence_threshold_s=300)
    assert state == "SILENCIEUSE"


def test_flux_incomplet_si_trop_peu_normalise():
    # 20 reçus, 5 normalisés → 25 % < 80 %
    state, reason = _eval(last_received_at=_recent(30), received_count=20, normalized_count=5)
    assert state == "FLUX_INCOMPLET"
    assert "complétude" in reason or "5/20" in reason


def test_flux_ok_si_completude_suffisante():
    # 20 reçus, 17 normalisés → 85 % ≥ 80 %
    state, _ = _eval(last_received_at=_recent(30), received_count=20, normalized_count=17)
    assert state == "ACTIVE"


def test_completude_ignoree_si_trop_peu_d_evenements():
    # Seulement 5 événements : pas assez pour évaluer la complétude (MIN = 10)
    state, _ = _eval(last_received_at=_recent(30), received_count=5, normalized_count=0)
    assert state == "ACTIVE"


def test_flux_incomplet_prime_sur_silencieuse():
    # Vieux ET incomplet → FLUX_INCOMPLET (plus informatif)
    state, _ = _eval(
        last_received_at=_old(1200),
        received_count=20,
        normalized_count=5,
    )
    assert state == "FLUX_INCOMPLET"


def test_completude_seuil_exact():
    # exactement 80 % → ACTIVE (seuil strict : < threshold = INCOMPLET)
    n = MIN_RECEIVED_FOR_COMPLETENESS
    state, _ = _eval(
        last_received_at=_recent(30),
        received_count=n,
        normalized_count=int(n * COMPLETENESS_THRESHOLD),
    )
    # int(10 * 0.80) = 8 → 8/10 = 80% → pas < 80% → ACTIVE
    assert state == "ACTIVE"


def test_completude_en_dessous_du_seuil():
    n = MIN_RECEIVED_FOR_COMPLETENESS
    state, _ = _eval(
        last_received_at=_recent(30),
        received_count=n,
        normalized_count=int(n * COMPLETENESS_THRESHOLD) - 1,
    )
    # 7/10 = 70% < 80% → FLUX_INCOMPLET
    assert state == "FLUX_INCOMPLET"


# ------------------------------------------------------------------ tests de SourceStateEvaluator (fake DB)

class _FakeConn:
    """Connexion factice pour l'évaluateur (sans PostgreSQL)."""

    def __init__(self, sources=None, state=None):
        self._sources = sources or []
        self._state = state  # CoverageStateRow ou None
        self.upserted: list[dict] = []
        self.history: list[dict] = []

    async def execute(self, *a, **kw):
        pass

    async def fetchall(self):
        return []

    async def fetchone(self):
        return None


class _FakeDB:
    """Base de données factice avec sources et état configurables."""

    def __init__(self, sources=None, state_by_id=None, raises=None):
        self._sources = sources or []
        self._state_by_id: dict[uuid.UUID, CoverageStateRow | None] = state_by_id or {}
        self._raises = raises
        self.upserts: list[dict] = []
        self.history: list[dict] = []
        self.affected_rules: list[dict] = []

    async def ping(self) -> bool:
        return self._raises is None

    class _Conn:
        """Pseudo-connexion qui délègue tout à la FakeDB."""
        def __init__(self, db):
            self._db = db

        async def execute(self, *a, **kw):
            pass

    from contextlib import asynccontextmanager as _acm  # pour type checker

    async def __aenter__(self):
        return self._Conn(self)

    async def __aexit__(self, *a):
        pass


import contextlib


def make_fake_db(sources=None, state_by_id=None):
    """Crée un objet FakeDB avec contextmanager.connection()."""

    class FakeDB:
        def __init__(self):
            self.upserts: list[dict] = []
            self.history: list[dict] = []
            self._sources = sources or []
            self._state_by_id = state_by_id or {}

        async def ping(self) -> bool:
            return True

        @contextlib.asynccontextmanager
        async def connection(self):
            yield self

        # Pseudo-interface psycopg (non utilisée directement ici)
        async def execute(self, *a, **kw):
            pass

    return FakeDB()


@pytest.fixture
def source_active():
    return SourceConfig(
        id=SRC_ID, name="src-test",
        silence_threshold_s=SILENCE_S,
        expected_min_events_per_h=None,
        active=True,
    )


@pytest.fixture
def source_inactive():
    return SourceConfig(
        id=SRC_ID, name="src-test",
        silence_threshold_s=SILENCE_S,
        expected_min_events_per_h=None,
        active=False,
    )


async def test_evaluateur_appelle_evaluate_state_par_source(monkeypatch, source_active):
    """SourceStateEvaluator appelle evaluate_state pour chaque source."""
    db = make_fake_db(sources=[source_active])

    captured: list[tuple] = []

    async def _fake_list_sources(conn):
        return [source_active]

    async def _fake_get_state(conn, source_id):
        return CoverageStateRow(
            source_id=source_id, state="INCONNUE",
            last_received_at=_recent(30), last_processed_at=None,
            received_count=5, normalized_count=5, evaluated_at=None,
        )

    async def _fake_upsert(conn, *, source_id, **kw):
        captured.append(("upsert", source_id, kw["state"]))

    async def _fake_history(conn, **kw):
        captured.append(("history", kw["new_state"]))

    import coverage.evaluator as _ev
    monkeypatch.setattr(_ev, "list_sources", _fake_list_sources)
    monkeypatch.setattr(_ev, "get_coverage_state", _fake_get_state)
    monkeypatch.setattr(_ev, "upsert_coverage_state", _fake_upsert)
    monkeypatch.setattr(_ev, "insert_state_history", _fake_history)

    evaluator = SourceStateEvaluator(db, interval_s=0.0)
    await evaluator._evaluate_all()

    upserts = [c for c in captured if c[0] == "upsert"]
    assert len(upserts) == 1
    assert upserts[0][1] == SRC_ID
    assert upserts[0][2] == "ACTIVE"


async def test_evaluateur_enregistre_transition(monkeypatch, source_active):
    """Une transition INCONNUE → ACTIVE déclenche insert_state_history."""
    db = make_fake_db()

    history_calls: list[dict] = []

    async def _fake_list_sources(conn):
        return [source_active]

    async def _fake_get_state(conn, source_id):
        return CoverageStateRow(
            source_id=source_id, state="INCONNUE",
            last_received_at=_recent(30), last_processed_at=None,
            received_count=5, normalized_count=5, evaluated_at=None,
        )

    async def _fake_upsert(conn, **kw):
        pass

    async def _fake_history(conn, *, source_id, previous_state, new_state, reason, changed_at):
        history_calls.append({"prev": previous_state, "new": new_state, "reason": reason})

    import coverage.evaluator as _ev
    monkeypatch.setattr(_ev, "list_sources", _fake_list_sources)
    monkeypatch.setattr(_ev, "get_coverage_state", _fake_get_state)
    monkeypatch.setattr(_ev, "upsert_coverage_state", _fake_upsert)
    monkeypatch.setattr(_ev, "insert_state_history", _fake_history)

    evaluator = SourceStateEvaluator(db, interval_s=0.0)
    await evaluator._evaluate_all()

    assert len(history_calls) == 1
    assert history_calls[0]["prev"] == "INCONNUE"
    assert history_calls[0]["new"] == "ACTIVE"


async def test_evaluateur_pas_de_transition_si_etat_identique(monkeypatch, source_active):
    """Pas d'enregistrement d'historique si l'état ne change pas."""
    db = make_fake_db()
    history_calls: list = []

    async def _fake_list_sources(conn):
        return [source_active]

    async def _fake_get_state(conn, source_id):
        return CoverageStateRow(
            source_id=source_id, state="ACTIVE",
            last_received_at=_recent(30), last_processed_at=None,
            received_count=10, normalized_count=9, evaluated_at=None,
        )

    async def _fake_upsert(conn, **kw):
        pass

    async def _fake_history(conn, **kw):
        history_calls.append(kw)

    import coverage.evaluator as _ev
    monkeypatch.setattr(_ev, "list_sources", _fake_list_sources)
    monkeypatch.setattr(_ev, "get_coverage_state", _fake_get_state)
    monkeypatch.setattr(_ev, "upsert_coverage_state", _fake_upsert)
    monkeypatch.setattr(_ev, "insert_state_history", _fake_history)

    evaluator = SourceStateEvaluator(db, interval_s=0.0)
    await evaluator._evaluate_all()

    assert history_calls == []
