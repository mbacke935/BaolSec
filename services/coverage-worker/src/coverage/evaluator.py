"""Évaluateur des états de couverture — SourceStateEvaluator (C17 W6).

Toutes les `interval_s` secondes (défaut : 60 s), l'évaluateur :
  1. Lit toutes les sources depuis config.sources.
  2. Pour chaque source, lit son état dans couverture.coverage_state.
  3. Calcule le nouvel état selon la machine à états :
       INCONNUE  → ACTIVE si last_received_at existe et récent
       ACTIVE    → SILENCIEUSE si last_received_at > silence_threshold_s
       ACTIVE    → FLUX_INCOMPLET si normalized_count << received_count (> 20 % d'écart)
       SILENCIEUSE ↔ FLUX_INCOMPLET selon les compteurs
       DESACTIVEE si source.active = False
  4. Écrit le nouvel état + historique si l'état a changé.
  5. Met à jour les métriques Prometheus.

Transitions (étapes C3 etats_couverture.puml) :
  - Toute source inactive → DESACTIVEE
  - last_received_at absente → INCONNUE
  - last_received_at dans les `silence_threshold_s` secondes → au moins ACTIVE
  - dernier reçu > seuil silence → SILENCIEUSE
  - normalized_count / received_count < seuil de complétude (80 %) → FLUX_INCOMPLET
    (prime sur SILENCIEUSE si actif mais incomplet)
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

from . import metrics
from .repositories import (
    Database,
    DatabaseUnavailable,
    get_coverage_state,
    insert_state_history,
    list_sources,
    upsert_coverage_state,
    upsert_affected_rules,
    get_source_by_name,
)

log = logging.getLogger(__name__)

# Seuil de complétude : si moins de 80 % des événements reçus sont normalisés, état = FLUX_INCOMPLET.
COMPLETENESS_THRESHOLD = 0.80
# Nombre minimal d'événements reçus pour évaluer la complétude (évite les faux positifs au démarrage).
MIN_RECEIVED_FOR_COMPLETENESS = 10


def _now() -> datetime:
    return datetime.now(timezone.utc)


def evaluate_state(
    *,
    active: bool,
    last_received_at: datetime | None,
    received_count: int,
    normalized_count: int,
    silence_threshold_s: int,
    now: datetime,
) -> tuple[str, str]:
    """Calcule le nouvel état et la raison de la transition.

    Retourne (state, reason).
    """
    if not active:
        return "DESACTIVEE", "source désactivée dans config"

    if last_received_at is None:
        return "INCONNUE", "aucun événement reçu"

    age_s = (now - last_received_at).total_seconds()
    silent = age_s > silence_threshold_s

    # Évaluer la complétude uniquement si on a assez d'événements
    incomplete = (
        received_count >= MIN_RECEIVED_FOR_COMPLETENESS
        and received_count > 0
        and normalized_count / received_count < COMPLETENESS_THRESHOLD
    )

    if silent and incomplete:
        # Les deux problèmes ; on privilégie FLUX_INCOMPLET (plus informatif)
        return "FLUX_INCOMPLET", f"silence depuis {age_s:.0f}s et complétude {normalized_count}/{received_count}"
    if silent:
        return "SILENCIEUSE", f"aucun événement depuis {age_s:.0f}s (seuil {silence_threshold_s}s)"
    if incomplete:
        return "FLUX_INCOMPLET", f"complétude {normalized_count}/{received_count} < {COMPLETENESS_THRESHOLD:.0%}"

    return "ACTIVE", "source active et flux complet"


class SourceStateEvaluator:
    """Évalue périodiquement l'état de toutes les sources."""

    def __init__(self, db: Database, *, interval_s: float = 60.0):
        self._db = db
        self._interval_s = interval_s

    async def run(self, stop: asyncio.Event) -> None:
        """Boucle principale ; s'arrête quand stop est positionné."""
        while not stop.is_set():
            started = time.perf_counter()
            try:
                await self._evaluate_all()
            except DatabaseUnavailable as exc:
                log.warning("SourceStateEvaluator : PostgreSQL indisponible (%s), passage sauté", exc)
            except Exception:
                log.exception("SourceStateEvaluator : erreur inattendue")
            elapsed = time.perf_counter() - started
            metrics.EVAL_RUNS.inc()
            metrics.EVAL_DURATION.observe(elapsed)
            log.debug("évaluation terminée en %.3fs", elapsed)

            # Attendre interval_s ou l'arrêt
            try:
                await asyncio.wait_for(stop.wait(), timeout=self._interval_s)
            except asyncio.TimeoutError:
                pass

    async def _evaluate_all(self) -> None:
        """Évalue toutes les sources en une seule passe."""
        now = _now()
        async with self._db.connection() as conn:
            sources = await list_sources(conn)

        for source in sources:
            try:
                await self._evaluate_one(source, now)
            except DatabaseUnavailable:
                raise  # remonter pour que run() gère
            except Exception:
                log.exception("SourceStateEvaluator : erreur sur source %s", source.name)

    async def _evaluate_one(self, source, now: datetime) -> None:
        async with self._db.connection() as conn:
            current = await get_coverage_state(conn, source.id)

            prev_state = current.state if current else None
            received_count = current.received_count if current else 0
            normalized_count = current.normalized_count if current else 0
            last_received_at = current.last_received_at if current else None
            last_processed_at = current.last_processed_at if current else None

            new_state, reason = evaluate_state(
                active=source.active,
                last_received_at=last_received_at,
                received_count=received_count,
                normalized_count=normalized_count,
                silence_threshold_s=source.silence_threshold_s,
                now=now,
            )

            await upsert_coverage_state(
                conn,
                source_id=source.id,
                state=new_state,
                last_received_at=last_received_at,
                last_processed_at=last_processed_at,
                received_count=received_count,
                normalized_count=normalized_count,
                evaluated_at=now,
            )

            if new_state != prev_state:
                await insert_state_history(
                    conn,
                    source_id=source.id,
                    previous_state=prev_state,
                    new_state=new_state,
                    reason=reason,
                    changed_at=now,
                )
                metrics.STATE_TRANSITIONS.labels(source.name, prev_state or "INCONNUE", new_state).inc()
                log.info("source %s : %s → %s (%s)", source.name, prev_state, new_state, reason)
            else:
                log.debug("source %s : état inchangé (%s)", source.name, new_state)

            # Mettre à jour la gauge Prometheus
            for state in ("INCONNUE", "ACTIVE", "SILENCIEUSE", "FLUX_INCOMPLET", "DESACTIVEE"):
                metrics.SOURCE_STATE.labels(source.name, state).set(1 if new_state == state else 0)


__all__ = ["SourceStateEvaluator", "evaluate_state"]
