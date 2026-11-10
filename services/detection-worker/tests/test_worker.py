"""Boucle de détection avec KV et broker simulés (C12, C14, W3)."""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field

from conftest import FakeBroker, FakeStore, event
from detector.worker import Worker, state_key
from test_engine import NOW, burst


@dataclass
class Msg:
    data: bytes
    delivery_count: int = 1
    subject: str = "normalized-events"
    msg_id: str | None = "m"
    stream_sequence: int = 1
    calls: list = field(default_factory=list)

    async def ack(self):
        self.calls.append("ack")

    async def nak(self, delay=None):
        self.calls.append("nak")

    async def in_progress(self):
        pass


def msg(ev):
    return Msg(json.dumps(ev).encode(), msg_id=ev["event"]["id"])


def worker(rules_cache, broker=None, store=None):
    return Worker(broker or FakeBroker(), store or FakeStore(), rules_cache, clock=lambda: NOW)


async def feed(w, events):
    for ev in events:
        await w._one(msg(ev))


async def test_cinq_echecs_une_alerte_puis_etat_sans_attente(rules_cache):
    w = worker(rules_cache)
    await feed(w, burst(4))
    assert w._broker.alerts() == []
    await feed(w, burst(5, start=NOW - 5 * 60_000, user="bob"))
    alerts = w._broker.alerts()
    assert len(alerts) == 1 and alerts[0]["user"]["name"] == "bob"
    assert all(s["pending"] is None for s in w._store.states().values())


async def test_arret_entre_etat_et_publication_puis_reprise(rules_cache):
    """Le KV contient l'alerte en attente ; la publication échoue (service arrêté) ;
    le contrôle périodique la republie avec le même alert_id, une seule fois."""
    broker, store = FakeBroker(), FakeStore()
    w = worker(rules_cache, broker, store)
    evs = burst(5, start=NOW - 5 * 60_000)
    await feed(w, evs[:4])
    broker.fail_next = 1                       # la publication de l'alerte échoue
    m = msg(evs[4])
    await w._one(m)
    assert m.calls == ["nak"] and broker.alerts() == []
    pending = [s["pending"] for s in store.states().values() if s["pending"]]
    assert len(pending) == 1

    w2 = worker(rules_cache, broker, store)    # redémarrage
    assert await w2.republish_pending() == 1
    assert len(broker.alerts()) == 1 and broker.alerts()[0]["event"]["id"] == pending[0]["event"]["id"]
    assert await w2.republish_pending() == 0
    await w2._one(msg(evs[4]))                 # relivraison du 5e échec : déjà compté
    assert len(broker.alerts()) == 1


async def test_alerte_en_attente_publiee_avant_la_suivante(rules_cache):
    broker, store = FakeBroker(), FakeStore()
    w = worker(rules_cache, broker, store)
    evs = burst(5, start=NOW - 5 * 60_000)
    await feed(w, evs[:4])
    broker.fail_next = 1
    await w._one(msg(evs[4]))
    await feed(w, [event(ts=NOW - 60_000)])     # événement suivant de la même clé
    assert len(broker.alerts()) == 1
    assert all(s["pending"] is None for s in store.states().values())


async def test_deux_instances_meme_cle_une_seule_alerte(rules_cache):
    broker, store = FakeBroker(), FakeStore()
    a, b = worker(rules_cache, broker, store), worker(rules_cache, broker, store)
    evs = burst(10, start=NOW - 5 * 60_000, step=10_000)
    await asyncio.gather(*(x._one(msg(ev)) for x, ev in zip([a, b] * 5, evs)))
    assert len(broker.alerts()) == 1
    st = store.states()[state_key(rules_cache.rules[0], "admin|10.0.4.23")]
    assert st["events"] == [] and st["pending"] is None


async def test_conflits_d_ecriture_reessayes(rules_cache):
    store = FakeStore()
    store.conflicts_to_inject = 3
    w = worker(rules_cache, store=store)
    await feed(w, burst(5, start=NOW - 5 * 60_000))
    assert len(w._broker.alerts()) == 1


async def test_duree_de_vie_de_l_etat(rules_cache):
    store = FakeStore()
    w = worker(rules_cache, store=store)
    await feed(w, burst(2, start=NOW - 60_000))
    ttls = set(store.ttls.values())
    assert 600 + 120 in ttls                    # AUTH-001/002 : fenêtre 10m + tolérance 2m
    assert 300 + 120 in ttls                    # AUTH-003 : fenêtre 5m + tolérance 2m


async def test_evenement_illisible_en_file_de_rejet(rules_cache):
    w = worker(rules_cache)
    m = Msg(b"{pas du json")
    await w._one(m)
    assert m.calls == ["ack"]
    (subject, dlq, _), = w._broker.sent
    assert subject == "dlq.detection-worker" and dlq["reason_code"] == "validation_error"
    assert dlq["original_stream"] == "normalized-events"


async def test_regle_simple_publiee_une_fois_meme_relivree(rules_cache):
    w = worker(rules_cache)
    ev = event(ts=NOW, category="process", outcome="success", event__code="4688", host="PC-WIN-COMPTA",
               process__command_line="powershell -enc SQBFAFgA")
    await feed(w, [ev, ev])
    assert [a["rule"]["id"] for a in w._broker.alerts()] == ["SYS-001"]
