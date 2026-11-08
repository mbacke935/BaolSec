"""Tests d'intégration de la passerelle d'ingestion (carte C6, C3 4.3).

Pile démarrée : broker + passerelle (make gateway-up), certificats et sources de
développement créés (bash scripts/development/init_dev_gateway.sh). Puis : make test-gateway.

Variables (valeurs par défaut adaptées à Docker Compose) :
  GATEWAY_URL           https://localhost:8443
  GATEWAY_SYSLOG        localhost:6514
  BROKER_URL, BROKER_TOKEN
  BROKER_STOP_CMD / BROKER_START_CMD / GATEWAY_RESTART_CMD  commandes de panne
  GATEWAY_REFRESH_S     période de rafraîchissement du cache des sources (défaut 5)
"""
from __future__ import annotations

import asyncio
import json
import os
import shlex
import ssl
import subprocess
import time
import uuid
from pathlib import Path

import httpx
import nats
import pytest
from nats.js.api import AckPolicy, ConsumerConfig, DeliverPolicy

ROOT = Path(__file__).resolve().parents[3]
DEV = ROOT / "infrastructure" / "tls" / "dev"
COMPOSE = "docker compose --env-file .env -f infrastructure/compose/compose.yaml"
URL = os.environ.get("GATEWAY_URL", "https://localhost:8443")
SYSLOG_HOST, SYSLOG_PORT = os.environ.get("GATEWAY_SYSLOG", "localhost:6514").rsplit(":", 1)
BROKER_URL = os.environ.get("BROKER_URL", "nats://localhost:4222")
BROKER_TOKEN = os.environ.get("BROKER_TOKEN")
BROKER_STOP = os.environ.get("BROKER_STOP_CMD", f"{COMPOSE} stop broker")
BROKER_START = os.environ.get("BROKER_START_CMD", f"{COMPOSE} up -d --wait broker")   # attend que le broker soit sain
GATEWAY_RESTART = os.environ.get("GATEWAY_RESTART_CMD", f"{COMPOSE} restart ingestion-gateway")
REFRESH_S = float(os.environ.get("GATEWAY_REFRESH_S", "5"))

TOKENS = dict(line.strip().split("=", 1) for line in (DEV / "tokens.env").read_text().splitlines() if "=" in line)
LINUX = TOKENS["DEV_TOKEN_LINUX"]
WINDOWS = TOKENS["DEV_TOKEN_WINDOWS"]


def run(cmd: str) -> None:
    subprocess.run(shlex.split(cmd), cwd=ROOT, check=True, timeout=120)


def client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=URL, verify=ssl.create_default_context(cafile=str(DEV / "sources-ca.crt")), timeout=15)


def headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "User-Agent": "Fluent-Bit/4.1.0"}


def unique(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex}"


async def wait_gateway(timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    async with client() as c:
        while time.monotonic() < deadline:
            try:
                r = await c.post("/ingest", json=[{"log": "ping"}], headers=headers("bsk_x"))
                if r.status_code == 401:
                    return
            except httpx.TransportError:
                pass
            await asyncio.sleep(1)
    pytest.fail(f"passerelle injoignable à {URL}")


async def raw_events_containing(marker: str, timeout: float = 10) -> list[dict]:
    """Événements de RAW_EVENTS dont le contenu contient `marker` (lecture sans consommateur durable).

    Après un redémarrage du broker, JetStream peut mettre quelques secondes à recharger ses flux :
    la connexion et la création du lecteur sont réessayées jusqu'à `timeout`.
    """
    deadline = time.monotonic() + timeout
    found: list[dict] = []
    while True:
        try:
            nc = await asyncio.wait_for(nats.connect(BROKER_URL, token=BROKER_TOKEN, allow_reconnect=False), 5)
            js = nc.jetstream()
            sub = await js.pull_subscribe("raw-events", durable=None, stream="RAW_EVENTS", config=ConsumerConfig(
                deliver_policy=DeliverPolicy.BY_START_TIME,
                opt_start_time=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 600)),
                ack_policy=AckPolicy.NONE))
            break
        except (OSError, asyncio.TimeoutError, nats.errors.Error) as exc:
            if time.monotonic() > deadline:
                pytest.fail(f"broker non prêt : {exc!r}")
            await asyncio.sleep(1)
    try:
        while time.monotonic() < deadline:
            try:
                msgs = await sub.fetch(500, timeout=1)
            except (asyncio.TimeoutError, nats.errors.TimeoutError):   # aucun nouveau message pour l'instant
                if found:
                    break
                continue
            found += [json.loads(m.data) for m in msgs if marker.encode() in m.data]
    finally:
        await nc.close()
    return found


def syslog_frame(text: str) -> bytes:
    data = text.encode()
    return f"{len(data)} ".encode() + data


async def syslog_send(cert: str, messages: list[str]) -> None:
    ctx = ssl.create_default_context(cafile=str(DEV / "sources-ca.crt"))
    ctx.load_cert_chain(DEV / f"{cert}.crt", DEV / f"{cert}.key")
    reader, writer = await asyncio.open_connection(SYSLOG_HOST, int(SYSLOG_PORT), ssl=ctx,
                                                   server_hostname="localhost")
    for m in messages:
        writer.write(syslog_frame(m))
    await writer.drain()
    await asyncio.sleep(0.5)
    writer.close()
    try:
        await writer.wait_closed()
    except (ssl.SSLError, ConnectionError):
        pass


@pytest.fixture(autouse=True, scope="module")
def _gateway_ready():
    asyncio.run(wait_gateway())


# ------------------------------------------------------------------ HTTPS

async def test_lot_https_publie_dans_raw_events():
    marker = unique("https")
    async with client() as c:
        r = await c.post("/ingest", headers=headers(LINUX), json=[
            {"date": "2026-11-05T10:00:00Z", "log": f"<38>Nov  5 10:00:00 srv sshd[1]: Failed password {marker} {i}"}
            for i in range(5)])
    assert r.status_code == 202 and r.json()["stored"] == 5
    events = await raw_events_containing(marker)
    assert len(events) == 5 and {e["transport"] for e in events} == {"https"}


async def test_double_envoi_un_seul_stockage():
    marker = unique("double")
    batch = [{"log": f"<38>Nov  5 10:00:00 srv sshd[1]: {marker}"}]
    async with client() as c:
        first = await c.post("/ingest", headers=headers(LINUX), json=batch)
        second = await c.post("/ingest", headers=headers(LINUX), json=batch)
    assert first.json()["stored"] == 1 and second.json()["duplicates"] == 1
    assert len(await raw_events_containing(marker)) == 1


async def test_source_non_authentifiee_et_tls_obligatoire():
    async with client() as c:
        r = await c.post("/ingest", headers=headers("bsk_inconnu"), json=[{"log": "x"}])
    assert r.status_code == 401
    with pytest.raises(httpx.TransportError):
        async with httpx.AsyncClient(timeout=5) as plain:          # HTTP sans TLS : refusé
            await plain.post(URL.replace("https://", "http://") + "/ingest", json=[])


async def test_message_malforme_et_trop_volumineux():
    async with client() as c:
        bad = await c.post("/ingest", headers=headers(LINUX) | {"Content-Type": "application/json"}, content=b"{oops")
        big = await c.post("/ingest", headers=headers(LINUX), json=[{"log": "x" * 60000}] * 150)   # 9 Mo > 8 Mio
    assert bad.status_code == 400 and big.status_code == 413


async def test_evenement_invalide_conserve_dans_la_file_de_rejet():
    marker = unique("invalide")
    async with client() as c:
        r = await c.post("/ingest", headers=headers(LINUX), json=[{"log": f"valide {marker}"}, {"log": 42, "m": marker}])
    assert r.status_code == 202 and r.json()["accepted"] == 1 and len(r.json()["rejected"]) == 1
    nc = await asyncio.wait_for(nats.connect(BROKER_URL, token=BROKER_TOKEN), 10)
    try:
        msg = await nc.jetstream().get_last_msg("DLQ", "dlq.ingestion-gateway")
    finally:
        await nc.close()
    body = json.loads(msg.data)
    assert marker in body["payload"] and body["original_stream"] == "ingest" and body["reason_code"] == "validation_error"


async def test_surcharge_renvoie_429():
    async with client() as c:
        statuses = set()
        for _ in range(12):     # 12 × 1000 > rafale par défaut (5000)
            r = await c.post("/ingest", headers=headers(WINDOWS),
                             json=[{"log": f"charge {uuid.uuid4().hex}"} for _ in range(1000)])
            statuses.add(r.status_code)
            if r.status_code == 429:
                assert int(r.headers["retry-after"]) >= 1
                break
    assert 429 in statuses


# ------------------------------------------------------------------ Syslog TLS

async def test_syslog_avec_certificat_enregistre():
    marker = unique("syslog")
    await syslog_send("syslog-client", [
        f"<134>1 2026-11-05T10:00:00Z fw-edge-01 filterlog 3012 - - block {marker} {i}" for i in range(3)])
    events = await raw_events_containing(marker)
    assert len(events) == 3 and {e["transport"] for e in events} == {"syslog"}
    assert {e["source"]["type"] for e in events} == {"firewall"}


async def test_syslog_certificat_etranger_refuse():
    marker = unique("rogue")
    try:   # selon la version de TLS, le refus apparaît à la poignée de main ou à la première écriture
        await syslog_send("rogue", [f"<134>1 - - - - - - {marker}"])
    except (ssl.SSLError, ConnectionError, OSError):
        pass
    assert await raw_events_containing(marker, timeout=3) == []


# ------------------------------------------------------------------ révocation

async def test_revocation_prise_en_compte_au_rafraichissement():
    path = DEV / "sources.json"
    original = path.read_text(encoding="utf-8")
    doc = json.loads(original)
    linux = next(s for s in doc["sources"] if s["name"] == "dev-linux")
    linux["credentials"][0]["revoked_at"] = "2026-11-05T00:00:00Z"
    try:
        path.write_text(json.dumps(doc), encoding="utf-8")
        await asyncio.sleep(REFRESH_S + 2)
        async with client() as c:
            r = await c.post("/ingest", headers=headers(LINUX), json=[{"log": "après révocation"}])
        assert r.status_code == 401
    finally:
        path.write_text(original, encoding="utf-8")
        await asyncio.sleep(REFRESH_S + 2)


# ------------------------------------------------------------------ pannes

async def test_broker_arrete_503_puis_reprise():
    marker = unique("panne")
    batch = [{"log": f"<38>Nov  5 10:00:00 srv sshd[1]: {marker}"}]
    run(BROKER_STOP)
    try:
        async with client() as c:
            r = await c.post("/ingest", headers=headers(LINUX), json=batch)
        assert r.status_code == 503 and "retry-after" in r.headers
    finally:
        run(BROKER_START)
    async with client() as c:
        for _ in range(30):                     # l'agent réessaie jusqu'au retour du broker
            r = await c.post("/ingest", headers=headers(LINUX), json=batch)
            if r.status_code == 202:
                break
            await asyncio.sleep(1)
    assert r.status_code == 202
    assert len(await raw_events_containing(marker)) == 1, "un seul exemplaire malgré les renvois"


async def test_syslog_pendant_panne_du_broker_rien_perdu():
    marker = unique("syslog-panne")
    run(BROKER_STOP)
    try:
        send = asyncio.create_task(syslog_send("syslog-client", [f"<134>1 - fw - - - - {marker} {i}" for i in range(3)]))
        await asyncio.sleep(3)
    finally:
        run(BROKER_START)
    await send
    events = await raw_events_containing(marker, timeout=30)
    assert len(events) == 3


async def test_redemarrage_de_la_passerelle():
    run(GATEWAY_RESTART)
    await wait_gateway()
    marker = unique("restart")
    async with client() as c:
        for _ in range(15):                     # attendre le premier chargement du cache
            r = await c.post("/ingest", headers=headers(LINUX), json=[{"log": marker}])
            if r.status_code != 503:
                break
            await asyncio.sleep(1)
    assert r.status_code == 202
    assert len(await raw_events_containing(marker)) == 1
