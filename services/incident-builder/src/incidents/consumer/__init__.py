"""Consommation du flux alerts : création de l'état de traitement et corrélation (C3 W4, C16).

Pour chaque message :
1. le contrat alert/v1 est vérifié (message illisible ou non conforme : file de rejet dès la 1re tentative) ;
2. l'état « nouvelle » est créé dans incidents.alert_state, clé alert_id : une alerte déjà connue est ignorée ;
3. la corrélation est appelée : l'alerte est rattachée à un incident existant ou un nouvel incident est créé ;
4. le message n'est acquitté qu'après la validation de la transaction PostgreSQL (I-8).

Si PostgreSQL est injoignable, le service cesse de lire le flux : les alertes attendent dans le broker (7 jours)
au lieu de consommer leurs 5 tentatives (C11).
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Protocol

from datetime import datetime, timedelta, timezone

from baolsec_common.messaging import Broker, ProcessingError, ReceivedMessage, RetryPolicy, process

from .. import metrics
from ..alert_state import Alert, AlertRejected, parse_alert
from ..contracts import Contracts
from ..correlation import (
    DEFAULT_MAX_DURATION_HOURS,
    DEFAULT_WINDOW_MINUTES,
    IncidentContext,
    apply_settings,
    correlate,
    extract_entities,
    incident_title,
    max_severity,
)
from ..repositories import Database, DatabaseUnavailable, UnknownRule
from ..repositories import alerts as repo
from ..repositories import incidents as inc_repo

log = logging.getLogger(__name__)
SERVICE = "incident-builder"


class AlertSink(Protocol):
    async def record(self, alert: Alert) -> bool:
        """Enregistre l'alerte ; False si elle existait déjà."""

    async def ready(self) -> bool:
        """La destination répond (PostgreSQL joignable)."""


SETTINGS_TTL_S = 60.0


class PostgresAlertSink:
    def __init__(self, db: Database, *, window_minutes: int = DEFAULT_WINDOW_MINUTES,
                 max_duration_hours: int = DEFAULT_MAX_DURATION_HOURS, settings_ttl_s: float = SETTINGS_TTL_S):
        self._db = db
        self._window_minutes = window_minutes
        self._max_duration_hours = max_duration_hours
        self._settings_ttl_s = settings_ttl_s
        self._settings_loaded_at = float("-inf")

    async def _refresh_settings(self, conn) -> None:
        """Relit les paramètres de corrélation (config.settings, C3 3.8) au plus une fois par minute.

        L'administrateur les modifie depuis l'interface ; ils s'appliquent aux alertes suivantes
        sans redémarrage. En cas d'erreur de lecture, les valeurs courantes sont conservées.
        """
        if time.monotonic() - self._settings_loaded_at < self._settings_ttl_s:
            return
        self._settings_loaded_at = time.monotonic()
        try:
            async with conn.cursor() as cur:
                await cur.execute("SELECT key, value FROM config.settings WHERE key LIKE 'correlation.%%'")
                rows = await cur.fetchall()
        except Exception as exc:  # noqa: BLE001
            log.warning("paramètres de corrélation illisibles, valeurs courantes conservées : %s", exc)
            return
        values = {}
        for row in rows:
            key, value = (row["key"], row["value"]) if isinstance(row, dict) else (row[0], row[1])
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except ValueError:
                    continue
            values[key] = value
        window = values.get("correlation.window_minutes")
        if isinstance(window, int) and not isinstance(window, bool) and 1 <= window <= 1440:
            self._window_minutes = window
        duration = values.get("correlation.max_incident_hours")
        if isinstance(duration, int) and not isinstance(duration, bool) and 1 <= duration <= 720:
            self._max_duration_hours = duration
        apply_settings(values.get("correlation.generic_values"), values.get("correlation.activity_chains"))

    async def record(self, alert: Alert) -> bool:
        async with self._db.connection() as conn:
            created = await repo.insert_alert(conn, alert)
            if created:
                await self._correlate(conn, alert)
            return created

    async def _correlate(self, conn, alert: Alert) -> None:
        """Corrélation C16 : rattache l'alerte à un incident existant ou en crée un."""
        await self._refresh_settings(conn)
        entities = extract_entities(alert.doc)

        now = alert.triggered_at
        since = now - timedelta(minutes=self._window_minutes)
        max_opened = now - timedelta(hours=self._max_duration_hours)

        candidates = await inc_repo.find_candidates(conn, since, max_opened)
        decision = correlate(
            entities, alert.rule_code, alert.severity, now, candidates,
            window_minutes=self._window_minutes,
            max_duration_hours=self._max_duration_hours,
        )

        if decision.action == "create":
            title = incident_title(entities, alert.rule_code, (alert.doc.get("rule") or {}).get("name"))
            await inc_repo.create_incident(
                conn, incident_id=decision.incident_id, title=title,
                severity=alert.severity, context=decision.new_context, opened_at=now,
            )
            attached = await inc_repo.attach_alert(
                conn, incident_id=decision.incident_id, alert_id=alert.alert_id,
                criteria=decision.justification, attached_at=now,
            )
            await inc_repo.add_timeline_entry(
                conn, incident_id=decision.incident_id, occurred_at=now,
                entry_type="correlation", alert_id=alert.alert_id,
                summary=f"Incident créé à partir de l'alerte {alert.rule_code}",
                justification=decision.justification,
            )
            metrics.INCIDENTS_CREATED.labels(alert.severity).inc()
            log.info("incident %s créé pour alerte %s", decision.incident_id, alert.alert_id[:12])

        else:  # attach
            inc = await inc_repo.lock_incident(conn, decision.incident_id)
            if inc is None:
                log.warning("incident %s disparu pendant la corrélation, création d'un nouvel incident",
                            decision.incident_id)
                return await self._correlate(conn, alert)

            attached = await inc_repo.attach_alert(
                conn, incident_id=decision.incident_id, alert_id=alert.alert_id,
                criteria=decision.justification, attached_at=now,
            )
            if not attached:
                # Conflit : alerte déjà rattachée à un autre incident
                existing = await inc_repo.get_alert_incident(conn, alert.alert_id)
                await inc_repo.add_timeline_entry(
                    conn, incident_id=decision.incident_id, occurred_at=now,
                    entry_type="conflict", alert_id=alert.alert_id,
                    summary=f"Conflit : alerte déjà rattachée à l'incident {existing}",
                    justification={"conflict_with": str(existing), **decision.justification},
                )
                metrics.CORRELATION_CONFLICTS.inc()
                log.warning("conflit : alerte %s déjà rattachée à %s", alert.alert_id[:12], existing)
                return

            new_sev = max_severity(inc.severity, alert.severity)
            await inc_repo.update_incident(
                conn, decision.incident_id,
                severity=new_sev if new_sev != inc.severity else None,
                context=decision.new_context,
                last_activity_at=now,
            )
            await inc_repo.add_timeline_entry(
                conn, incident_id=decision.incident_id, occurred_at=now,
                entry_type="correlation", alert_id=alert.alert_id,
                summary=f"Alerte {alert.rule_code} rattachée par {decision.rule}",
                justification=decision.justification,
            )
            metrics.ALERTS_ATTACHED.labels(decision.rule).inc()
            log.info("alerte %s rattachée à incident %s par %s",
                     alert.alert_id[:12], decision.incident_id, decision.rule)

    async def ready(self) -> bool:
        return await self._db.ping()


class AlertConsumer:
    def __init__(self, broker: Broker, sink: AlertSink, contracts: Contracts, *, stream: str = "ALERTS",
                 durable: str = "incident-builder", batch: int = 50, retry_pause_s: float = 2.0):
        self._broker, self._sink, self._contracts = broker, sink, contracts
        self._stream, self._durable, self._batch, self._pause = stream, durable, batch, retry_pause_s
        self._policy = RetryPolicy(service=SERVICE, stream="alerts", publisher=broker)
        self._stop = asyncio.Event()
        self._sink_ok = False

    def stop(self) -> None:
        self._stop.set()

    @property
    def sink_ok(self) -> bool:
        return self._sink_ok

    async def handle(self, msg: ReceivedMessage) -> None:
        try:
            doc = json.loads(msg.data)
        except ValueError as exc:
            raise ProcessingError("parse_error", f"alerte illisible : {exc}", permanent=True) from exc
        problems = self._contracts.alert_errors(doc)
        if problems:
            raise ProcessingError("validation_error", f"alerte non conforme à alert/v1 : {problems}", permanent=True)
        try:
            alert = parse_alert(doc)
            created = await self._sink.record(alert)
        except AlertRejected as exc:
            raise ProcessingError("validation_error", str(exc), permanent=True) from exc
        except UnknownRule as exc:
            # Règle chargée depuis un dossier YAML (DETECTOR_RULES_SOURCE=file) ou pas encore chargée : make rules-load,
            # puis reprise depuis la file de rejet (make dlq-replay).
            raise ProcessingError("processing_error", str(exc), permanent=True) from exc
        except DatabaseUnavailable as exc:
            self._sink_ok = False
            raise ProcessingError("processing_error", f"PostgreSQL indisponible : {exc}") from exc
        if created:
            metrics.ALERTS.labels(alert.severity).inc()
            log.info("alerte %s %s enregistrée (nouvelle)", alert.rule_code, alert.alert_id[:12])
        else:
            metrics.DUPLICATES.inc()
            log.info("alerte %s %s déjà connue : ignorée", alert.rule_code, alert.alert_id[:12])

    async def _one(self, msg: ReceivedMessage) -> None:
        started = time.perf_counter()
        try:
            outcome = await process(msg, self.handle, self._policy)
        except Exception:        # acquittement impossible (broker coupé) : le message sera relivré
            log.exception("traitement interrompu pour %s", msg.msg_id)
            return
        metrics.SECONDS.observe(time.perf_counter() - started)
        metrics.MESSAGES.labels(outcome).inc()

    async def run(self) -> None:
        sub = None
        while not self._stop.is_set():
            if not self._sink_ok:
                self._sink_ok = await self._sink.ready()
                if not self._sink_ok:
                    log.warning("PostgreSQL injoignable : lecture du flux %s suspendue", self._stream)
                    await self._sleep(self._pause)
                    continue
            try:
                if sub is None:
                    sub = await self._broker.subscribe(self._stream, self._durable)
                msgs = await sub.fetch(self._batch, timeout=1)
            except Exception as exc:
                if self._stop.is_set():
                    break                       # arrêt demandé pendant la lecture : sortie normale
                log.warning("lecture de %s impossible (%s : %s), nouvel essai", self._stream, type(exc).__name__, exc)
                sub = None
                await self._sleep(self._pause)
                continue
            for m in msgs:                     # un par un : les alertes sont rares, l'ordre du flux est conservé
                await self._one(m)

    async def _sleep(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass


__all__ = ["AlertConsumer", "AlertSink", "PostgresAlertSink"]
