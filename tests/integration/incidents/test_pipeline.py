"""Chaîne complète avec NATS et PostgreSQL réels : détection → broker → service Incidents → alert_state (C15).

Ne nécessite ni Docker ni la passerelle : le moteur de détection (C12, C14) et le service Incidents tournent
dans le processus du test, sur un vrai broker JetStream et une vraie base.

Variables : TEST_POSTGRES_DSN (voir test_alert_state.py), BROKER_URL (défaut nats://localhost:4222), BROKER_TOKEN.
Le broker doit avoir sa topologie (init_broker.py). Les flux ALERTS, NORMALIZED_EVENTS et DLQ sont VIDÉS au début de chaque test et le
consommateur durable incident-builder est lu par le test : ne jamais viser le broker de la pile. `make test-incidents` démarre un broker
jetable et positionne INCIDENTS_TEST_PURGE=yes ; sans cette variable, les tests sont ignorés.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone

import nats
import pytest
from prometheus_client import REGISTRY

from incidents_support import ADMIN_DSN, ROOT, alert_document, rows

BROKER_URL = os.environ.get("BROKER_URL", "nats://localhost:4222")
BROKER_TOKEN = os.environ.get("BROKER_TOKEN")
pytestmark = [pytest.mark.skipif(not ADMIN_DSN or not BROKER_TOKEN, reason="TEST_POSTGRES_DSN et BROKER_TOKEN requis"),
              pytest.mark.skipif(os.environ.get("INCIDENTS_TEST_PURGE") != "yes",
                                 reason="ces tests vident les flux du broker : INCIDENTS_TEST_PURGE=yes, broker jetable seulement (make test-incidents)"),
              pytest.mark.asyncio(loop_scope="function")]

sys.path.insert(0, str(ROOT / "services" / "detection-worker" / "src"))

from baolsec_common.messaging.nats_adapter import NatsBroker                    # noqa: E402
from incidents.config import Settings                                            # noqa: E402,F401
from incidents.consumer import AlertConsumer, PostgresAlertSink                  # noqa: E402
from incidents.contracts import Contracts                                        # noqa: E402
from incidents_support import CONTRACTS                                          # noqa: E402


@pytest.fixture
async def broker():
    b = await NatsBroker.connect(BROKER_URL, BROKER_TOKEN, name="test-c15")
    yield b
    await b.close()


@pytest.fixture
async def js():
    nc = await nats.connect(BROKER_URL, token=BROKER_TOKEN)
    js = nc.jetstream()
    for stream in ("ALERTS", "NORMALIZED_EVENTS", "DLQ"):
        await js.purge_stream(stream)
    yield js
    await nc.close()


@pytest.fixture(scope="module")
def contracts():
    return Contracts(CONTRACTS)


async def wait_for(predicate, timeout=15.0, interval=0.1):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if await predicate():
            return True
        await asyncio.sleep(interval)
    return False


async def stored(database, ids) -> list[tuple]:
    return await asyncio.to_thread(rows, database, "SELECT alert_id, status::text, severity::text FROM incidents.alert_state "
                                   "WHERE alert_id = ANY(%s) ORDER BY alert_id", (list(ids),))


def counter(name, **labels):
    return REGISTRY.get_sample_value(name, labels) or 0.0


async def publish(broker, subject, doc, msg_id=None):
    await broker.publish(subject, json.dumps(doc).encode(), msg_id=msg_id or doc["event"]["id"])


class Running:
    """Service Incidents lancé en tâche de fond."""

    def __init__(self, consumer):
        self.consumer, self.task = consumer, None

    async def __aenter__(self):
        self.task = asyncio.create_task(self.consumer.run())
        return self

    async def __aexit__(self, *exc):
        self.consumer.stop()
        await asyncio.wait_for(self.task, 5)


async def info(js):
    return await js.consumer_info("ALERTS", "incident-builder")


async def test_alertes_du_flux_enregistrees_une_seule_fois(db, database, broker, js, contracts):
    docs = [alert_document(severity=s) for s in ("faible", "elevee", "critique")]
    for d in docs:
        await publish(broker, "alerts", d)
    await publish(broker, "alerts", docs[0], msg_id="republication-" + docs[0]["event"]["id"])   # même alerte, autre Msg-Id
    ids = [d["event"]["id"] for d in docs]
    dups = counter("baolsec_incidents_alert_duplicates_total")

    async with Running(AlertConsumer(broker, PostgresAlertSink(db), contracts, retry_pause_s=0.2)):
        assert await wait_for(lambda: _done(database, ids, js))
    assert await stored(database, ids) == sorted((d["event"]["id"], "nouvelle", d["baolsec"]["severity"]["label"]) for d in docs)
    assert counter("baolsec_incidents_alert_duplicates_total") == dups + 1
    i = await info(js)
    assert (i.num_pending, i.num_ack_pending) == (0, 0)


async def _done(database, ids, js) -> bool:
    i = await info(js)
    return len(await stored(database, ids)) == len(ids) and i.num_pending == 0 and i.num_ack_pending == 0


async def test_message_illisible_file_de_rejet_et_rien_dans_alert_state(db, database, broker, js, contracts):
    before = (await asyncio.to_thread(rows, database, "SELECT count(*) FROM incidents.alert_state"))[0][0]
    await broker.publish("alerts", b"{ceci n'est pas une alerte", msg_id="illisible-" + uuid.uuid4().hex)
    async with Running(AlertConsumer(broker, PostgresAlertSink(db), contracts, retry_pause_s=0.2)):
        async def dlq_has_it():
            return (await js.stream_info("DLQ")).state.messages == 1
        assert await wait_for(dlq_has_it)
        assert await wait_for(lambda: _idle(js))
    dlq = json.loads((await js.get_last_msg("DLQ", "dlq.incident-builder")).data)
    assert dlq["contract"] == "dlq_message/v1" and dlq["reason_code"] == "parse_error" and dlq["original_stream"] == "alerts"
    assert (await asyncio.to_thread(rows, database, "SELECT count(*) FROM incidents.alert_state"))[0][0] == before


async def _idle(js) -> bool:
    i = await info(js)
    return i.num_pending == 0 and i.num_ack_pending == 0


class Gated(PostgresAlertSink):
    """PostgreSQL « coupé » tant que `open` est faux."""

    def __init__(self, db):
        super().__init__(db)
        self.open = False

    async def ready(self) -> bool:
        return self.open and await super().ready()


async def test_postgresql_coupe_les_alertes_attendent_dans_le_broker_puis_sont_enregistrees(db, database, broker, js, contracts):
    doc = alert_document()
    await publish(broker, "alerts", doc)
    sink = Gated(db)
    async with Running(AlertConsumer(broker, sink, contracts, retry_pause_s=0.1)):
        await asyncio.sleep(1.5)
        i = await info(js)
        assert (i.num_pending, i.num_ack_pending) == (1, 0)             # jamais lue : aucune tentative consommée
        assert await stored(database, [doc["event"]["id"]]) == []
        sink.open = True                                                 # PostgreSQL revient
        assert await wait_for(lambda: _done(database, [doc["event"]["id"]], js))
    assert (await js.stream_info("DLQ")).state.messages == 0


async def test_alerte_deja_publiee_avant_le_demarrage_du_service_est_rattrapee(db, database, broker, js, contracts):
    """Le consommateur durable conserve les alertes arrivées pendant que le service était arrêté (reprise)."""
    docs = [alert_document() for _ in range(25)]
    for d in docs:
        await publish(broker, "alerts", d)
    ids = [d["event"]["id"] for d in docs]
    async with Running(AlertConsumer(broker, PostgresAlertSink(db), contracts, batch=10, retry_pause_s=0.2)):
        assert await wait_for(lambda: _done(database, ids, js), timeout=30)


async def test_chaine_complete_cinq_echecs_de_connexion_jusqu_a_l_etat_de_l_alerte(db, database, broker, js, contracts):
    """Cinq échecs d'authentification → moteur de détection → flux alerts → service Incidents → alert_state."""
    from detector.rules import FileRules, RulesCache, RuleValidator
    from detector.worker import Worker

    rules = RulesCache(FileRules(ROOT / "rules"), RuleValidator(CONTRACTS))
    await rules.refresh()
    detection = Worker(broker, broker.state_store("detection-state"), rules, pending_interval_s=3600)
    user, ip = "u" + uuid.uuid4().hex[:10], "10.8.0.77"
    now = datetime.now(timezone.utc)
    for i in range(5):
        at = datetime.fromtimestamp(now.timestamp() - 30 + i * 5, tz=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        event = {"@timestamp": at, "event": {"id": f"evt-{uuid.uuid4().hex}", "kind": "event", "category": ["authentication"],
                                             "outcome": "failure"}, "user": {"name": user}, "source": {"ip": ip},
                 "host": {"name": "srv-linux-01"}, "baolsec": {"source": {"type": "linux", "ingestion_mode": "direct"}}}
        await publish(broker, "normalized-events", event)

    found: list[str] = []

    async def alert_known() -> bool:
        candidates = await asyncio.to_thread(rows, database, "SELECT alert_id FROM incidents.alert_state WHERE rule_id = %s "
                                             "AND created_at > now() - interval '1 minute'", (_rule("AUTH-001"),))
        found[:] = [a for (a,) in candidates if await _alert_for(js, a, user)]
        return bool(found)

    det = asyncio.create_task(detection.run())
    try:
        async with Running(AlertConsumer(broker, PostgresAlertSink(db), contracts, retry_pause_s=0.2)):
            assert await wait_for(alert_known, timeout=30)
    finally:
        detection.stop()
        await asyncio.wait_for(det, 5)

    assert len(found) == 1
    [(status, severity, assigned)] = await asyncio.to_thread(
        rows, database, "SELECT status::text, severity::text, assigned_to FROM incidents.alert_state WHERE alert_id = %s", (found[0],))
    assert (status, severity, assigned) == ("nouvelle", "elevee", None)
    assert (await js.stream_info("DLQ")).state.messages == 0


def _rule(code):
    from incidents.alert_state import rule_uuid
    return rule_uuid(code)


async def _alert_for(js, alert_id: str, user: str) -> bool:
    """L'alerte `alert_id` du flux alerts concerne bien `user` (le document complet reste dans le flux, EF-06)."""
    state = (await js.stream_info("ALERTS")).state
    for seq in range(state.first_seq, state.last_seq + 1):
        doc = json.loads((await js.get_msg("ALERTS", seq)).data)
        if doc["event"]["id"] == alert_id:
            return doc.get("user", {}).get("name") == user and len(doc["baolsec"]["alert"]["event_ids"]) == 5
    return False
