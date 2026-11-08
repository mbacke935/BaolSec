"""Tests de POST /ingest avec un broker en mémoire (codes de réponse de C3 4.3)."""
from __future__ import annotations

import json

import httpx
import pytest

from gateway.config import Settings
from gateway.http import create_app
from gateway.publisher import RawEventPublisher
from gateway.rate_limit import RateLimiter

from .conftest import DISABLED_TOKEN, LINUX_TOKEN, OLD_TOKEN, WINDOWS_TOKEN, assert_dlq_message, assert_raw_event


def settings(**kw) -> Settings:
    base = dict(source_registry="file", sources_file="unused.json", max_body_bytes=200_000, max_events_per_batch=50)
    return Settings(**(base | kw))


@pytest.fixture
def make_client(cache, broker):
    def factory(rate=1000.0, burst=1000, **kw):
        app = create_app(settings(**kw), cache, RateLimiter(rate, burst), RawEventPublisher(broker, 1.0, 16))
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://gateway")
    return factory


def auth(token):
    return {"Authorization": f"Bearer {token}", "User-Agent": "Fluent-Bit/4.1.0"}


BATCH = [{"date": "2026-11-05T10:00:00Z", "log": f"<38>Nov  5 10:00:0{i} srv sshd[1]: Failed password"} for i in range(3)]


async def test_lot_valide_202_apres_publication(make_client, broker):
    async with make_client() as c:
        r = await c.post("/ingest", json=BATCH, headers=auth(LINUX_TOKEN))
    assert r.status_code == 202
    assert r.json() == {"accepted": 3, "stored": 3, "duplicates": 0, "rejected": []}
    assert len(broker.on("raw-events")) == 3
    for event in broker.on("raw-events"):
        assert event["transport"] == "https"
        assert_raw_event(event)


async def test_double_envoi_ecarte_par_le_broker(make_client, broker):
    async with make_client() as c:
        await c.post("/ingest", json=BATCH, headers=auth(LINUX_TOKEN))
        r = await c.post("/ingest", json=BATCH, headers=auth(LINUX_TOKEN))
    assert r.status_code == 202 and r.json()["duplicates"] == 3
    assert len(broker.on("raw-events")) == 3


async def test_evenement_windows_identifiant_natif(make_client, broker):
    rec = {"date": 1762336800, "Computer": "PC-COMPTA-02", "Channel": "Security", "EventRecordID": 98765,
           "EventID": 4625, "Message": "An account failed to log on."}
    async with make_client() as c:
        r = await c.post("/ingest", json=[rec], headers=auth(WINDOWS_TOKEN))
    assert r.status_code == 202
    event = broker.messages[0][1]
    assert event["event_id"] == "win:PC-COMPTA-02:Security:98765" and event["source"]["type"] == "windows"
    assert_raw_event(event)


@pytest.mark.parametrize("headers", [
    {}, auth("bsk_inconnu"), auth(OLD_TOKEN), auth(DISABLED_TOKEN), {"Authorization": f"Basic {LINUX_TOKEN}"},
])
async def test_source_non_authentifiee_401(make_client, broker, headers):
    async with make_client() as c:
        r = await c.post("/ingest", json=BATCH, headers=headers)
    assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"
    assert r.headers["content-type"] == "application/problem+json" and broker.messages == []


@pytest.mark.parametrize("body", [b"{pas du json", b'{"log": "objet seul"}', b"[]"])
async def test_lot_malforme_400(make_client, body):
    async with make_client() as c:
        r = await c.post("/ingest", content=body, headers=auth(LINUX_TOKEN) | {"Content-Type": "application/json"})
    assert r.status_code == 400 and r.json()["status"] == 400


async def test_lot_partiellement_invalide_refus_conserves(make_client, broker):
    async with make_client() as c:
        r = await c.post("/ingest", json=[BATCH[0], "texte", {"log": ""}, BATCH[1]], headers=auth(LINUX_TOKEN))
    assert r.status_code == 202
    body = r.json()
    assert body["accepted"] == 2 and [x["index"] for x in body["rejected"]] == [1, 2]
    assert len(broker.on("raw-events")) == 2
    dlq = broker.on("dlq.ingestion-gateway")
    assert len(dlq) == 2, "chaque événement refusé est conservé dans la file de rejet"
    for m in dlq:
        assert_dlq_message(m)
        assert m["original_stream"] == "ingest" and m["source_id"] and m["reason_code"] == "validation_error"


async def test_lot_entierement_invalide_conserve_puis_202(make_client, broker):
    async with make_client() as c:
        r = await c.post("/ingest", json=["a", {}], headers=auth(LINUX_TOKEN))
    assert r.status_code == 202 and r.json()["accepted"] == 0 and len(r.json()["rejected"]) == 2
    assert broker.on("raw-events") == [] and len(broker.on("dlq.ingestion-gateway")) == 2


async def test_refus_renvoye_non_duplique(make_client, broker):
    """Un lot renvoyé après un 503 ne crée pas de second exemplaire des refus (même Msg-Id)."""
    async with make_client() as c:
        await c.post("/ingest", json=[BATCH[0], "texte"], headers=auth(LINUX_TOKEN))
        await c.post("/ingest", json=[BATCH[0], "texte"], headers=auth(LINUX_TOKEN))
    assert len(broker.on("dlq.ingestion-gateway")) == 1 and len(broker.on("raw-events")) == 1


async def test_lot_trop_volumineux_413(make_client):
    async with make_client() as c:
        big = await c.post("/ingest", json=[{"log": "x" * 60000}] * 4, headers=auth(LINUX_TOKEN))
        many = await c.post("/ingest", json=[{"log": "x"}] * 51, headers=auth(LINUX_TOKEN))
    assert big.status_code == 413 and many.status_code == 413


async def test_surcharge_429(make_client, broker):
    async with make_client(rate=1, burst=2) as c:
        ok = await c.post("/ingest", json=BATCH, headers=auth(LINUX_TOKEN))
        r = await c.post("/ingest", json=BATCH, headers=auth(LINUX_TOKEN))
        other = await c.post("/ingest", json=[{"log": "autre source"}], headers=auth(WINDOWS_TOKEN))
    assert ok.status_code == 202
    assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1
    assert other.status_code == 202          # la limite est propre à chaque source


async def test_broker_indisponible_503(make_client, broker):
    broker.down = True
    async with make_client() as c:
        r = await c.post("/ingest", json=BATCH, headers=auth(LINUX_TOKEN))
    assert r.status_code == 503 and r.headers["retry-after"] == "5"
    broker.down = False
    async with make_client() as c:
        r = await c.post("/ingest", json=BATCH, headers=auth(LINUX_TOKEN))
    assert r.status_code == 202 and r.json()["stored"] == 3


async def test_referentiel_indisponible_503(make_client, cache):
    cache._max_stale_s = -1
    async with make_client() as c:
        r = await c.post("/ingest", json=BATCH, headers=auth(LINUX_TOKEN))
    assert r.status_code == 503
