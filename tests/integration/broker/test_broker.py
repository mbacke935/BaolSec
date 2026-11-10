"""Tests d'intégration du broker (critères de la carte C8, ADR 0002).

Nécessitent un broker démarré :
    make broker-up        # broker + création des flux
    make test-broker

Variables : BROKER_URL (défaut nats://localhost:4222), BROKER_TOKEN,
BROKER_RESTART_CMD (commande qui redémarre le broker ; défaut : docker compose restart broker).

Les tests de mécanique utilisent des flux temporaires TEST_* créés avec les mêmes
réglages que topology.json, puis supprimés : les flux réels ne sont pas modifiés.
"""
from __future__ import annotations

import asyncio
import json
import os
import shlex
import subprocess
import time
import uuid
from pathlib import Path

import nats
import pytest
from nats.js.api import AckPolicy, ConsumerConfig, DeliverPolicy, StreamConfig

from baolsec_common.messaging import ProcessingError, RetryPolicy, process
from baolsec_common.messaging.nats_adapter import NatsBroker

ROOT = Path(__file__).resolve().parents[3]
TOPOLOGY = json.loads((ROOT / "infrastructure" / "broker" / "topology.json").read_text(encoding="utf-8"))
KV = json.loads((ROOT / "infrastructure" / "state-store" / "detection-state.json").read_text(encoding="utf-8"))
URL = os.environ.get("BROKER_URL", "nats://localhost:4222")
TOKEN = os.environ.get("BROKER_TOKEN")
RESTART = os.environ.get(
    "BROKER_RESTART_CMD",
    "docker compose --env-file .env -f infrastructure/compose/compose.yaml restart broker",
)

pytestmark = pytest.mark.asyncio(loop_scope="function")


def val(x):
    """Les champs énumérés reviennent en Enum ou en str selon la version du client."""
    return getattr(x, "value", x)


async def connect():
    """Échoue en 10 s si le broker est injoignable, au lieu de réessayer sans fin."""
    async def quiet(_e):
        return None
    try:
        return await asyncio.wait_for(
            nats.connect(URL, token=TOKEN, error_cb=quiet, reconnect_time_wait=1, max_reconnect_attempts=-1),
            timeout=10,
        )
    except asyncio.TimeoutError:
        pytest.fail(f"broker injoignable à {URL} : lancer « make broker-up » et vérifier BROKER_TOKEN dans .env")


@pytest.fixture
async def temp_stream():
    """Flux temporaire avec les réglages de RAW_EVENTS ; supprimé à la fin du test."""
    nc = await connect()
    js = nc.jetstream()
    name = f"TEST_{uuid.uuid4().hex[:8].upper()}"
    subject = f"test.{name.lower()}"
    d = TOPOLOGY["stream_defaults"]
    await js.add_stream(StreamConfig(
        name=name, subjects=[subject], storage=d["storage"], retention=d["retention"],
        discard=d["discard"], duplicate_window=d["duplicate_window"], max_msg_size=d["max_msg_size"],
    ))
    yield js, name, subject
    try:
        await js.delete_stream(name)
    finally:
        await nc.close()


# ---------------------------------------------------------------- topologie réelle

async def test_topologie_conforme():
    nc = await connect()
    js = nc.jetstream()
    try:
        cdef = TOPOLOGY["consumer_defaults"]
        for s in TOPOLOGY["streams"]:
            info = await js.stream_info(s["name"])
            cfg = info.config
            assert cfg.subjects == s["subjects"]
            assert val(cfg.storage) == "file"
            assert cfg.duplicate_window == TOPOLOGY["stream_defaults"]["duplicate_window"]
            assert cfg.max_age == s["max_age"] and cfg.max_bytes == s["max_bytes"]
            assert val(cfg.discard) == s.get("discard", TOPOLOGY["stream_defaults"]["discard"])
            assert val(cfg.retention) == s.get("retention", TOPOLOGY["stream_defaults"]["retention"])
            for durable in s["consumers"]:
                c = (await js.consumer_info(s["name"], durable)).config
                assert val(c.ack_policy) == "explicit"
                assert c.max_deliver == cdef["max_deliver"]
                assert c.backoff == cdef["backoff"]
        kv = await js.key_value(KV["bucket"])
        status = await kv.status()
        assert status.history == KV["history"]
    finally:
        await nc.close()


# ---------------------------------------------------------------- déduplication

async def test_deduplication_par_msg_id(temp_stream):
    js, _, subject = temp_stream
    broker = await NatsBroker.connect(URL, TOKEN)
    try:
        first = await broker.publish(subject, b"e1", msg_id="evt-1")
        again = await broker.publish(subject, b"e1", msg_id="evt-1")
        other = await broker.publish(subject, b"e2", msg_id="evt-2")
    finally:
        await broker.close()
    assert not first.duplicate and again.duplicate and again.sequence == first.sequence
    assert other.sequence == first.sequence + 1


# ---------------------------------------------------------------- relecture

async def test_relecture_depuis_une_sequence(temp_stream):
    js, name, subject = temp_stream
    for i in range(1, 11):
        await js.publish(subject, f"m{i}".encode(), headers={"Nats-Msg-Id": f"r{i}"})
    sub = await js.pull_subscribe(subject, durable=None, stream=name,
                                  config=ConsumerConfig(deliver_policy=DeliverPolicy.BY_START_SEQUENCE,
                                                        opt_start_seq=6, ack_policy=AckPolicy.EXPLICIT))
    msgs = await sub.fetch(10, timeout=2)
    assert [m.data for m in msgs] == [f"m{i}".encode() for i in range(6, 11)]


# ---------------------------------------------------------------- partage entre instances

async def test_deux_instances_se_partagent_le_flux(temp_stream):
    js, name, subject = temp_stream
    await js.add_consumer(name, ConsumerConfig(durable_name="worker", ack_policy=AckPolicy.EXPLICIT))
    n = 200
    for i in range(n):
        await js.publish(subject, str(i).encode(), headers={"Nats-Msg-Id": f"s{i}"})

    async def instance(label, seen):
        b = await NatsBroker.connect(URL, TOKEN, name=label)
        sub = await b.subscribe(name, "worker")
        while True:
            batch = await sub.fetch(10, timeout=1)
            if not batch:
                break
            for m in batch:
                seen.append(m.data)
                await m.ack()
                await asyncio.sleep(0.002)   # laisse l'autre instance travailler
        await b.close()

    a, b = [], []
    await asyncio.gather(instance("A", a), instance("B", b))
    assert len(a) > 0 and len(b) > 0, "les deux instances doivent recevoir des messages"
    assert sorted(a + b, key=int) == [str(i).encode() for i in range(n)], "chaque message traité une seule fois"


# ---------------------------------------------------------------- redélivrance et dlq

async def test_echecs_relivres_puis_dlq(temp_stream):
    js, name, subject = temp_stream
    await js.add_consumer(name, ConsumerConfig(durable_name="w", ack_policy=AckPolicy.EXPLICIT,
                                               max_deliver=-1, ack_wait=2))
    await js.publish(subject, b'{"contract":"raw_event/v1"}', headers={"Nats-Msg-Id": "bad-1"})

    broker = await NatsBroker.connect(URL, TOKEN)
    sub = await broker.subscribe(name, "w")
    policy = RetryPolicy(service="normalization-worker", stream="raw-events", publisher=broker,
                         backoff=(0.2, 0.2, 0.2, 0.2))

    async def always_fails(_m):
        raise ProcessingError("parse_error", "test")

    outcomes, counts = [], []
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline and "dlq" not in outcomes:
        for m in await sub.fetch(1, timeout=1):
            counts.append(m.delivery_count)
            outcomes.append(await process(m, always_fails, policy))
    assert counts == [1, 2, 3, 4, 5]
    assert outcomes == ["retry"] * 4 + ["dlq"]
    assert await sub.fetch(1, timeout=1) == [], "le message acquitté après la dlq ne revient plus"

    dlq = await js.get_last_msg("DLQ", "dlq.normalization-worker")
    body = json.loads(dlq.data)
    await broker.close()
    assert body["message_id"] == "bad-1" and body["attempts"] == 5


async def test_cinquieme_tentative_interrompue_puis_dlq(temp_stream):
    """C11 : le service s'arrête pendant la 5e tentative (aucun acquittement). Le broker relivre
    sans limite : le message revient et part en dlq, au lieu de rester bloqué dans le flux."""
    js, name, subject = temp_stream
    await js.add_consumer(name, ConsumerConfig(durable_name="w", ack_policy=AckPolicy.EXPLICIT,
                                               max_deliver=-1, ack_wait=1))
    msg_id = f"stuck-{uuid.uuid4().hex[:8]}"
    await js.publish(subject, b'{"contract":"raw_event/v1"}', headers={"Nats-Msg-Id": msg_id})
    broker = await NatsBroker.connect(URL, TOKEN)
    sub = await broker.subscribe(name, "w")
    policy = RetryPolicy(service="normalization-worker", stream="raw-events", publisher=broker,
                         backoff=(0.2, 0.2, 0.2, 0.2))

    async def always_fails(_m):
        raise ProcessingError("processing_error", "test")

    outcomes = []
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and "dlq" not in outcomes:
        for m in await sub.fetch(1, timeout=2):
            if m.delivery_count == 5:
                outcomes.append("interrompu")        # arrêt simulé : ni nak ni ack
                continue
            outcomes.append(await process(m, always_fails, policy))
    await broker.close()
    assert outcomes == ["retry"] * 4 + ["interrompu", "dlq"]
    body = json.loads((await js.get_last_msg("DLQ", "dlq.normalization-worker")).data)
    assert body["message_id"] == msg_id and body["attempts"] == 5
    assert (await js.consumer_info(name, "w")).num_ack_pending == 0


async def test_message_non_acquitte_est_relivre(temp_stream):
    js, name, subject = temp_stream
    await js.add_consumer(name, ConsumerConfig(durable_name="w", ack_policy=AckPolicy.EXPLICIT, ack_wait=1))
    await js.publish(subject, b"x", headers={"Nats-Msg-Id": "lost"})
    broker = await NatsBroker.connect(URL, TOKEN)
    sub = await broker.subscribe(name, "w")
    first = (await sub.fetch(1, timeout=2))[0]      # simulé : le worker plante sans acquitter
    assert first.delivery_count == 1
    second = (await sub.fetch(1, timeout=5))[0]
    assert second.msg_id == "lost" and second.delivery_count == 2
    await second.ack()
    await broker.close()


# ---------------------------------------------------------------- raw-events : pas de suppression silencieuse

async def test_flux_plein_refuse_au_lieu_de_supprimer():
    """Réglages de RAW_EVENTS (interest + refus si plein) sur un petit flux temporaire :
    un message non traité n'est jamais supprimé pour faire de la place ; le nouveau est refusé,
    puis accepté dès que les consommateurs ont acquitté les anciens."""
    nc = await connect()
    js = nc.jetstream()
    name = f"TEST_{uuid.uuid4().hex[:8].upper()}"
    subject = f"test.{name.lower()}"
    await js.add_stream(StreamConfig(name=name, subjects=[subject], retention="interest", discard="new",
                                     max_msgs=3, storage="file"))
    try:
        await js.add_consumer(name, ConsumerConfig(durable_name="w", ack_policy=AckPolicy.EXPLICIT))
        for i in range(3):
            await js.publish(subject, f"m{i}".encode(), headers={"Nats-Msg-Id": f"f{i}"})
        broker = await NatsBroker.connect(URL, TOKEN)
        try:
            from baolsec_common.messaging import BrokerUnavailable
            with pytest.raises(BrokerUnavailable):
                await broker.publish(subject, b"m3", msg_id="f3", timeout=2)
            sub = await broker.subscribe(name, "w")
            for m in await sub.fetch(3, timeout=2):
                await m.ack()
            await asyncio.sleep(0.5)
            result = await broker.publish(subject, b"m3", msg_id="f3", timeout=2)
            assert not result.duplicate
        finally:
            await broker.close()
        assert (await js.stream_info(name)).state.messages == 1, "les messages acquittés ont été supprimés"
    finally:
        await js.delete_stream(name)
        await nc.close()


# ---------------------------------------------------------------- persistance après redémarrage

@pytest.mark.skipif(os.environ.get("BROKER_SKIP_RESTART") == "1", reason="redémarrage désactivé")
async def test_messages_conserves_apres_redemarrage(temp_stream):
    js, name, subject = temp_stream
    await js.add_consumer(name, ConsumerConfig(durable_name="w", ack_policy=AckPolicy.EXPLICIT))
    for i in range(50):
        await js.publish(subject, f"p{i}".encode(), headers={"Nats-Msg-Id": f"p{i}"})
    sub = await js.pull_subscribe_bind(durable="w", stream=name)
    for m in await sub.fetch(20, timeout=2):
        await m.ack_sync()

    subprocess.run(shlex.split(RESTART), cwd=ROOT, check=True, timeout=120)

    nc = await connect()
    js2 = nc.jetstream()
    for _ in range(60):                                   # attendre le retour du broker
        try:
            info = await js2.stream_info(name)
            break
        except Exception:
            await asyncio.sleep(1)
    assert info.state.messages == 50, "les 50 messages sont toujours stockés"
    sub2 = await js2.pull_subscribe_bind(durable="w", stream=name)
    rest = await sub2.fetch(50, timeout=3)
    assert [m.data for m in rest] == [f"p{i}".encode() for i in range(20, 50)], \
        "le consommateur reprend après le dernier message acquitté"
    for m in rest:
        await m.ack_sync()
    await nc.close()


# ---------------------------------------------------------------- état de détection (KV, C14)

async def test_etat_ecriture_conditionnelle_et_expiration():
    from baolsec_common.messaging import StateConflict
    broker = await NatsBroker.connect(URL, TOKEN)
    store = broker.state_store(KV["bucket"])
    key = f"TEST-000.{uuid.uuid4().hex}"
    try:
        assert await store.get(key) is None
        rev = await store.put(key, b"v1", 0, ttl_s=2)
        with pytest.raises(StateConflict):
            await store.put(key, b"autre", 0, ttl_s=2)            # une autre instance a déjà créé l'entrée
        rev2 = await store.put(key, b"v2", rev, ttl_s=2)
        with pytest.raises(StateConflict):
            await store.put(key, b"v3", rev, ttl_s=2)             # révision périmée
        entry = await store.get(key)
        assert entry.value == b"v2" and entry.revision == rev2
        assert any(e.key == key for e in await store.scan())
        await asyncio.sleep(3.5)
        assert await store.get(key) is None, "l'entrée doit expirer après son délai de vie"
        assert await store.put(key, b"v4", 0, ttl_s=2) > rev2      # recréée après expiration
    finally:
        await broker.close()
