"""Boucle de consommation sans broker réel : publication, acquittement, doublon, file de rejet, pause."""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field

from baolsec_common.messaging import BrokerUnavailable, PublishResult

from normalizer.worker import Worker

from .conftest import DLQ, NORMALIZED, raw


@dataclass
class Msg:
    data: bytes
    delivery_count: int = 1
    subject: str = "raw-events"
    msg_id: str | None = "e" * 64
    stream_sequence: int = 1
    calls: list = field(default_factory=list)

    async def ack(self):
        self.calls.append("ack")

    async def nak(self, delay=None):
        self.calls.append(("nak", delay))

    async def in_progress(self):
        pass


class Broker:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.sent: list[tuple[str, dict, str]] = []
        self.seen: set[str] = set()

    async def publish(self, subject, data, msg_id, timeout=5.0):
        if self.fail:
            raise BrokerUnavailable("arrêté")
        dup = msg_id in self.seen
        self.seen.add(msg_id)
        if not dup:
            self.sent.append((subject, json.loads(data), msg_id))
        return PublishResult("X", len(self.sent), dup)


LINE = "<38>Nov  2 10:40:52 srv-linux-01 sshd[1842]: Failed password for admin from 10.0.4.23 port 51234 ssh2"


async def test_publie_puis_acquitte(normalizer, cache):
    broker = Broker()
    msg = Msg(json.dumps(raw("linux", LINE)).encode())
    await Worker(broker, normalizer, cache)._one(msg)
    subject, doc, msg_id = broker.sent[0]
    assert subject == "normalized-events" and msg_id == "e" * 64
    NORMALIZED.validate(doc)
    assert msg.calls == ["ack"]


async def test_relivraison_ne_cree_pas_de_doublon(normalizer, cache):
    broker = Broker()
    worker = Worker(broker, normalizer, cache)
    for _ in range(2):      # acquittement perdu : le même message revient
        await worker._one(Msg(json.dumps(raw("linux", LINE)).encode()))
    assert len(broker.sent) == 1


async def test_contenu_illisible_en_file_de_rejet_des_la_premiere_fois(normalizer, cache):
    broker = Broker()
    msg = Msg(json.dumps(raw("linux", "n'importe quoi")).encode())
    await Worker(broker, normalizer, cache)._one(msg)
    subject, dlq, msg_id = broker.sent[0]
    assert subject == "dlq.normalization-worker" and msg_id == "dlq:normalization-worker:" + "e" * 64
    DLQ.validate(dlq)
    assert dlq["attempts"] == 1 and dlq["reason_code"] == "parse_error" and dlq["original_stream"] == "raw-events"
    assert msg.calls == ["ack"]


async def test_broker_indisponible_nouvelle_livraison(normalizer, cache):
    msg = Msg(json.dumps(raw("linux", LINE)).encode(), delivery_count=2)
    await Worker(Broker(fail=True), normalizer, cache)._one(msg)
    assert msg.calls == [("nak", 15)]


class Sub:
    def __init__(self):
        self.fetches = 0

    async def fetch(self, batch=10, timeout=5.0):
        self.fetches += 1
        await asyncio.sleep(0.01)
        return []


class SubscribingBroker(Broker):
    def __init__(self):
        super().__init__()
        self.sub = Sub()

    async def subscribe(self, stream, durable):
        assert (stream, durable) == ("RAW_EVENTS", "normalization")
        return self.sub


class StaleCache:
    usable = False


async def test_referentiel_indisponible_lecture_suspendue(normalizer):
    broker = SubscribingBroker()
    worker = Worker(broker, normalizer, StaleCache())
    task = asyncio.create_task(worker.run())
    await asyncio.sleep(0.3)
    worker.stop()
    await asyncio.wait_for(task, 3)
    assert broker.sub.fetches == 0
