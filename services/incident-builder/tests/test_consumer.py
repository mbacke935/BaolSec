"""Consommation du flux alerts avec broker et destination simulés (C15, W4 étape 1)."""
from __future__ import annotations

import asyncio
import json

import pytest
from prometheus_client import REGISTRY

from conftest import FakeBroker, FakeSink, Msg, alert_doc, msg
from incidents.consumer import AlertConsumer
from incidents.repositories import DatabaseUnavailable, UnknownRule


def consumer(broker, sink, contracts, **kw):
    return AlertConsumer(broker, sink, contracts, **kw)


def counter(name, **labels):
    return REGISTRY.get_sample_value(name, labels) or 0.0


async def test_alerte_valide_enregistree_puis_acquittee(broker, sink, contracts):
    m = msg(alert_doc())
    await consumer(broker, sink, contracts)._one(m)
    assert m.calls == ["ack"] and len(sink.alerts) == 1 and broker.dlq() == []


async def test_alerte_livree_deux_fois_enregistree_une_fois(broker, sink, contracts):
    doc = alert_doc()
    before = counter("baolsec_incidents_alert_duplicates_total")
    c = consumer(broker, sink, contracts)
    m1, m2 = msg(doc), msg(doc, stream_sequence=2)
    await c._one(m1)
    await c._one(m2)
    assert m1.calls == m2.calls == ["ack"]
    assert len(sink.alerts) == 1 and sink.record_calls == 2
    assert counter("baolsec_incidents_alert_duplicates_total") == before + 1


async def test_compteur_par_severite(broker, sink, contracts):
    before = counter("baolsec_incidents_alerts_received_total", severity="critique")
    await consumer(broker, sink, contracts)._one(msg(alert_doc()))      # l'exemple du contrat est « critique »
    assert counter("baolsec_incidents_alerts_received_total", severity="critique") == before + 1


async def test_message_illisible_va_en_file_de_rejet_des_la_premiere_tentative(broker, sink, contracts):
    m = Msg(b"\xff\xfenot json", msg_id="x")
    await consumer(broker, sink, contracts)._one(m)
    assert m.calls == ["ack"] and sink.alerts == {}
    [d] = broker.dlq()
    assert d["reason_code"] == "parse_error" and d["original_stream"] == "alerts" and d["service"] == "incident-builder"
    assert d["attempts"] == 1


@pytest.mark.parametrize("mutate", [
    lambda d: d.pop("rule"),
    lambda d: d.update(unexpected=1),
    lambda d: d["event"].update(id="pas-un-sha256"),
    lambda d: d.update({"@timestamp": "hier"}),
])
async def test_alerte_non_conforme_va_en_file_de_rejet(broker, sink, contracts, mutate):
    doc = alert_doc()
    mutate(doc)
    m = msg(doc, msg_id="m")
    await consumer(broker, sink, contracts)._one(m)
    assert m.calls == ["ack"] and sink.alerts == {} and sink.record_calls == 0
    assert broker.dlq()[0]["reason_code"] == "validation_error"
    assert "alert/v1" in broker.dlq()[0]["reason"]


async def test_severite_info_conforme_au_contrat_mais_refusee(broker, sink, contracts):
    doc = alert_doc(severity="info")
    doc["baolsec"]["severity"]["score"] = 0
    m = msg(doc)
    await consumer(broker, sink, contracts)._one(m)
    assert m.calls == ["ack"] and sink.alerts == {}
    assert broker.dlq()[0]["reason_code"] == "validation_error" and "info" in broker.dlq()[0]["reason"]


async def test_regle_inconnue_rejetee_sans_nouvelles_tentatives(broker, sink, contracts):
    sink.errors = [UnknownRule("règle AUTH-001 absente de config.rules")]
    m = msg(alert_doc())
    await consumer(broker, sink, contracts)._one(m)
    assert m.calls == ["ack"] and sink.record_calls == 1
    assert broker.dlq()[0]["reason_code"] == "processing_error" and "config.rules" in broker.dlq()[0]["reason"]


async def test_postgresql_indisponible_nouvelle_livraison_puis_succes(broker, sink, contracts):
    c = consumer(broker, sink, contracts)
    doc = alert_doc()
    sink.errors = [DatabaseUnavailable("OperationalError : connexion refusée")]
    first = msg(doc)
    await c._one(first)
    assert first.calls == ["nak"] and sink.alerts == {} and broker.dlq() == [] and not c.sink_ok
    second = msg(doc, delivery_count=2)
    await c._one(second)
    assert second.calls == ["ack"] and len(sink.alerts) == 1


async def test_cinquieme_echec_va_en_file_de_rejet(broker, sink, contracts):
    sink.errors = [DatabaseUnavailable("coupure")]
    m = msg(alert_doc(), delivery_count=5)
    await consumer(broker, sink, contracts)._one(m)
    assert m.calls == ["ack"] and broker.dlq()[0]["attempts"] == 5


async def test_file_de_rejet_injoignable_message_non_acquitte(broker, sink, contracts):
    broker.fail_next = 1
    m = Msg(b"pas du json", msg_id="x")
    await consumer(broker, sink, contracts)._one(m)
    assert m.calls == []                       # sera relivré par le broker


class Sub:
    def __init__(self, batches, boom=0):
        self.batches, self.boom, self.fetches = list(batches), boom, 0

    async def fetch(self, batch, timeout=1.0):
        self.fetches += 1
        if self.boom:
            self.boom -= 1
            raise ConnectionError("broker coupé")
        if self.batches:
            return self.batches.pop(0)
        await asyncio.sleep(0.005)
        return []


class BrokerWithSub(FakeBroker):
    def __init__(self, sub):
        super().__init__()
        self.sub, self.subscribed = sub, 0

    async def subscribe(self, stream, durable):
        self.subscribed += 1
        return self.sub


async def run_for(c, seconds):
    task = asyncio.create_task(c.run())
    await asyncio.sleep(seconds)
    c.stop()
    await asyncio.wait_for(task, 2)


async def test_boucle_ne_lit_pas_le_flux_tant_que_postgresql_est_injoignable(contracts):
    m = msg(alert_doc())
    sub = Sub([[m]])
    sink = FakeSink()
    sink.up = False
    c = consumer(BrokerWithSub(sub), sink, contracts, retry_pause_s=0.01)
    await run_for(c, 0.1)
    assert sub.fetches == 0 and m.calls == []             # l'alerte attend dans le broker
    sink.up = True
    await run_for(consumer(BrokerWithSub(sub), sink, contracts, retry_pause_s=0.01), 0.1)
    assert m.calls == ["ack"] and len(sink.alerts) == 1


async def test_boucle_se_reabonne_apres_une_erreur_de_lecture(contracts):
    m = msg(alert_doc())
    broker = BrokerWithSub(Sub([[m]], boom=2))
    sink = FakeSink()
    await run_for(consumer(broker, sink, contracts, retry_pause_s=0.01), 0.2)
    assert broker.subscribed == 3 and m.calls == ["ack"]


async def test_boucle_traite_un_lot_dans_l_ordre(contracts):
    docs = [alert_doc() for _ in range(5)]
    msgs = [msg(d, stream_sequence=i + 1) for i, d in enumerate(docs)]
    sink = FakeSink()
    await run_for(consumer(BrokerWithSub(Sub([msgs])), sink, contracts, retry_pause_s=0.01), 0.1)
    assert [m.calls for m in msgs] == [["ack"]] * 5
    assert list(sink.alerts) == [d["event"]["id"] for d in docs]
