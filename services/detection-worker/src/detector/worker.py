"""Boucle de détection sur normalized-events (C3, workflow W3).

Pour chaque événement et chaque règle applicable :
1. règle simple : l'alerte est publiée directement (son identifiant dépend de l'événement : une
   relivraison republie la même alerte, écartée par le broker) ;
2. règle à fenêtre : l'état est lu dans le KV, mis à jour par écriture conditionnelle sur la révision lue ;
   si le seuil est atteint, l'alerte est enregistrée « en attente » dans la même écriture ;
3. l'alerte est publiée dans alerts (Msg-Id = alert_id), puis effacée de l'état ;
4. l'événement n'est acquitté qu'après toutes les règles.
Si le service s'arrête entre 2 et 3, l'alerte en attente est republiée par le contrôle périodique
(au démarrage puis toutes les minutes) ou au prochain événement de la même clé.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time

from baolsec_common.messaging import (Broker, ProcessingError, ReceivedMessage, RetryPolicy, StateConflict,
                                      StateStore, process)

from . import alert as alerts
from . import engine, metrics
from .rules import Rule, RulesCache
from .timeutil import now_ms

log = logging.getLogger(__name__)
SERVICE = "detection-worker"


def state_key(rule: Rule, group: str) -> str:
    return f"{rule.code}.{hashlib.sha256(group.encode('utf-8')).hexdigest()[:40]}"


class Worker:
    def __init__(self, broker: Broker, store: StateStore, rules: RulesCache, *,
                 stream: str = "NORMALIZED_EVENTS", durable: str = "detection", output_subject: str = "alerts",
                 batch: int = 100, publish_timeout_s: float = 5.0, late_tolerance_s: int = 120,
                 pending_interval_s: float = 60.0, cas_retries: int = 20, clock=now_ms):
        self._broker, self._store, self._rules = broker, store, rules
        self._stream, self._durable, self._subject = stream, durable, output_subject
        self._batch, self._timeout = batch, publish_timeout_s
        self._tolerance, self._pending_interval, self._retries = late_tolerance_s, pending_interval_s, cas_retries
        self._clock = clock
        self._policy = RetryPolicy(service=SERVICE, stream="normalized-events", publisher=broker)
        self._stop = asyncio.Event()

    def stop(self) -> None:
        self._stop.set()

    # ------------------------------------------------------------ publication

    async def publish(self, doc: dict) -> None:
        body = json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        result = await self._broker.publish(self._subject, body, msg_id=doc["event"]["id"], timeout=self._timeout)
        if not result.duplicate:
            metrics.ALERTS.labels(doc["rule"]["id"], doc["baolsec"]["severity"]["label"]).inc()
            log.info("alerte %s %s : %s", doc["rule"]["id"], doc["event"]["id"][:12], doc["message"])

    async def clear_pending(self, key: str, alert_id: str) -> None:
        """Retire l'alerte publiée de l'état ; en cas d'échec, le contrôle périodique s'en chargera."""
        for _ in range(self._retries):
            entry = await self._store.get(key)
            if entry is None:
                return
            state = json.loads(entry.value)
            if not state.get("pending") or state["pending"]["event"]["id"] != alert_id:
                return
            state["pending"] = None
            try:
                await self._store.put(key, _dump(state), entry.revision, self._ttl(state, _rule_window(state)))
                return
            except StateConflict:
                metrics.CONFLICTS.inc()

    # ------------------------------------------------------------ évaluation

    async def apply_window(self, rule: Rule, doc: dict) -> str:
        values = engine.group_values(rule, doc)
        if values is None:
            return "ignored"
        key = state_key(rule, engine.group_key(rule, values, doc["event"]["id"]))
        for _ in range(self._retries):
            entry = await self._store.get(key)
            state = json.loads(entry.value) if entry else None
            if state and state.get("pending"):
                # Alerte précédente pas encore effacée : publiée d'abord, pour ne jamais l'écraser.
                await self.publish(state["pending"])
                state["pending"] = None
            decision = engine.evaluate_window(rule, doc, state, self._clock(), self._tolerance)
            if decision.state is None:
                if decision.outcome == "late":
                    metrics.LATE.labels(rule.code).inc()
                if entry and state is not None and entry.value != _dump(state):
                    await self._write(key, state, entry.revision, rule)      # efface l'alerte déjà republiée
                return decision.outcome
            new_state = decision.state
            doc_alert = alerts.build(rule, decision.fire) if decision.fire else None
            new_state["pending"] = doc_alert
            new_state["window_s"] = rule.window_s
            try:
                await self._store.put(key, _dump(new_state), entry.revision if entry else 0, self._ttl(new_state, rule.window_s))
            except StateConflict:
                metrics.CONFLICTS.inc()
                continue
            if doc_alert:
                await self.publish(doc_alert)
                await self.clear_pending(key, doc_alert["event"]["id"])
            return decision.outcome
        raise ProcessingError("processing_error", f"état {key} modifié trop souvent par d'autres instances")

    async def _write(self, key: str, state: dict, revision: int, rule: Rule) -> None:
        try:
            await self._store.put(key, _dump(state), revision, self._ttl(state, rule.window_s))
        except StateConflict:
            metrics.CONFLICTS.inc()

    def _ttl(self, state: dict, window_s: int) -> float:
        ttl = window_s + self._tolerance
        remaining = (state.get("suppress_until", 0) - self._clock()) / 1000
        return max(ttl, remaining + self._tolerance)

    async def handle(self, msg: ReceivedMessage) -> None:
        try:
            doc = json.loads(msg.data)
            categories = doc["event"].get("category", [])
            doc["event"]["id"], doc["@timestamp"]
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise ProcessingError("validation_error", f"événement normalisé illisible : {exc}", permanent=True) from exc
        for rule in self._rules.candidates(categories):
            if rule.type == "simple":
                decision = engine.evaluate_simple(rule, doc)
                if decision.fire:
                    await self.publish(alerts.build(rule, decision.fire))
                outcome = decision.outcome
            else:
                if not (rule.matches(doc) or (rule.trigger and rule.trigger(doc))):
                    continue
                outcome = await self.apply_window(rule, doc)
            if outcome != "ignored":
                metrics.EVALUATIONS.labels(rule.code, outcome).inc()

    async def _one(self, msg: ReceivedMessage) -> None:
        started = time.perf_counter()
        try:
            outcome = await process(msg, self.handle, self._policy)
        except Exception:      # acquittement impossible (broker coupé) : le message sera relivré
            log.exception("traitement interrompu pour %s", msg.msg_id)
            return
        metrics.SECONDS.observe(time.perf_counter() - started)
        metrics.EVENTS.labels(outcome).inc()

    # ------------------------------------------------------------ alertes en attente

    async def republish_pending(self) -> int:
        n = 0
        for entry in await self._store.scan():
            try:
                state = json.loads(entry.value)
            except ValueError:
                continue
            pending = state.get("pending")
            if not pending:
                continue
            n += 1
            await self.publish(pending)
            metrics.REPUBLISHED.inc()
            await self.clear_pending(entry.key, pending["event"]["id"])
        metrics.PENDING.set(n)
        return n

    async def pending_loop(self) -> None:
        while not self._stop.is_set():
            try:
                n = await self.republish_pending()
                if n:
                    log.warning("%d alerte(s) en attente republiée(s)", n)
            except Exception as exc:
                log.warning("contrôle des alertes en attente impossible : %s", exc)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._pending_interval)
            except asyncio.TimeoutError:
                pass

    # ------------------------------------------------------------ boucle principale

    async def run(self) -> None:
        sub = None
        while not self._stop.is_set():
            if not self._rules.usable:
                await asyncio.sleep(1)         # règles jamais chargées : les événements attendent dans le broker
                continue
            try:
                if sub is None:
                    sub = await self._broker.subscribe(self._stream, self._durable)
                msgs = await sub.fetch(self._batch, timeout=1)
            except Exception as exc:
                log.warning("lecture de %s impossible (%s : %s), nouvel essai", self._stream, type(exc).__name__, exc)
                sub = None
                await asyncio.sleep(2)
                continue
            if msgs:
                await asyncio.gather(*(self._one(m) for m in msgs))


def _dump(state: dict) -> bytes:
    return json.dumps(state, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _rule_window(state: dict) -> int:
    return int(state.get("window_s", 0))


__all__ = ["Worker", "state_key"]
