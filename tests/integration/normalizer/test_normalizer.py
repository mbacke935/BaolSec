"""Tests d'intégration de la normalisation et de l'enrichissement (cartes C9 et C10, workflow W2).

Pile : broker + passerelle + normalisation (make normalizer-up), environnement de développement
créé par scripts/development/init_dev_gateway.sh. Puis : make test-normalizer.

Variables (valeurs par défaut pour Docker Compose) :
  GATEWAY_URL, BROKER_URL, BROKER_TOKEN
  NORMALIZER_KILL_CMD / NORMALIZER_START_CMD     arrêt brutal / redémarrage du service
  NORMALIZER_SCALE2_CMD / NORMALIZER_SCALE1_CMD  passage à deux instances / retour à une
  NORMALIZER_REFRESH_S                           rafraîchissement du référentiel des sources (défaut 5)
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import shlex
import ssl
import subprocess
import time
import uuid
from pathlib import Path

import httpx
import nats
import pytest
from jsonschema import Draft202012Validator, FormatChecker
from nats.js.api import AckPolicy, ConsumerConfig, DeliverPolicy

ROOT = Path(__file__).resolve().parents[3]
DEV = ROOT / "infrastructure" / "tls" / "dev"
CONTRACTS = ROOT / "shared" / "contracts"
COMPOSE = "docker compose --env-file .env -f infrastructure/compose/compose.yaml"
URL = os.environ.get("GATEWAY_URL", "https://localhost:8443")
BROKER_URL = os.environ.get("BROKER_URL", "nats://localhost:4222")
BROKER_TOKEN = os.environ.get("BROKER_TOKEN")
KILL = os.environ.get("NORMALIZER_KILL_CMD", f"{COMPOSE} kill normalization-worker")
START = os.environ.get("NORMALIZER_START_CMD", f"{COMPOSE} up -d --wait normalization-worker")
SCALE2 = os.environ.get("NORMALIZER_SCALE2_CMD", f"{COMPOSE} up -d --wait --scale normalization-worker=2 normalization-worker")
SCALE1 = os.environ.get("NORMALIZER_SCALE1_CMD", f"{COMPOSE} up -d --wait --scale normalization-worker=1 normalization-worker")
REFRESH_S = float(os.environ.get("NORMALIZER_REFRESH_S", "5"))

TOKENS = dict(line.strip().split("=", 1) for line in (DEV / "tokens.env").read_text().splitlines() if "=" in line)
SOURCES = {s["name"]: s for s in json.loads((DEV / "sources.json").read_text())["sources"]}


def validator(name: str) -> Draft202012Validator:
    return Draft202012Validator(json.loads((CONTRACTS / name / "v1" / "schema.json").read_text()),
                                format_checker=FormatChecker())


NORMALIZED, DLQ = validator("normalized_event"), validator("dlq_message")


def run(cmd: str) -> None:
    subprocess.run(shlex.split(cmd), cwd=ROOT, check=True, timeout=180)


def unique(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:16]}"


async def post(token: str, records: list[dict]) -> None:
    ctx = ssl.create_default_context(cafile=str(DEV / "sources-ca.crt"))
    async with httpx.AsyncClient(base_url=URL, verify=ctx, timeout=30) as c:
        for i in range(0, len(records), 500):
            r = await c.post("/ingest", json=records[i:i + 500], headers={"Authorization": f"Bearer {token}"})
            assert r.status_code == 202, r.text


async def read(stream: str, subject: str, marker: str, expected: int, timeout: float = 60) -> list[dict]:
    """Messages récents de `stream` contenant `marker`, dès que `expected` sont présents (ou à l'échéance)."""
    deadline = time.monotonic() + timeout
    found: list[dict] = []
    while time.monotonic() < deadline:
        nc = await asyncio.wait_for(nats.connect(BROKER_URL, token=BROKER_TOKEN, allow_reconnect=False), 10)
        try:
            sub = await nc.jetstream().pull_subscribe(subject, durable=None, stream=stream, config=ConsumerConfig(
                deliver_policy=DeliverPolicy.BY_START_TIME, ack_policy=AckPolicy.NONE,
                opt_start_time=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 900))))
            found = []
            while True:
                try:
                    msgs = await sub.fetch(1000, timeout=1)
                except (asyncio.TimeoutError, nats.errors.TimeoutError):
                    break
                found += [json.loads(m.data) for m in msgs if marker.encode() in m.data]
        finally:
            await nc.close()
        if len(found) >= expected:
            return found
        await asyncio.sleep(2)
    return found


def linux_line(marker: str, i: int) -> dict:
    return {"log": f"Nov  8 10:00:00 srv-test sshd[{4000 + i % 1000}]: Failed password for invalid user {marker}-{i} "
                   f"from 203.0.113.{i % 250 + 1} port {40000 + i} ssh2"}


async def test_quatre_types_de_sources():
    marker = unique("c9")
    await post(TOKENS["DEV_TOKEN_LINUX"], [linux_line(marker, 0)])
    await post(TOKENS["DEV_TOKEN_PFSENSE"], [{"log": f"<134>Nov  8 10:00:00 fw-{marker} filterlog[3012]: 5,,,1000000103,em0,match,block,in,4,0x0,,64,0,0,DF,6,tcp,60,198.51.100.4,10.0.2.47,49822,22,0,S,1,,64240,,mss"}])
    await post(TOKENS["DEV_TOKEN_WEBAPP"], [{"log": f'10.0.8.31 - - [08/Nov/2026:10:00:00 +0000] "GET /{marker} HTTP/1.1" 404 12 "-" "curl/8.5.0"'}])
    await post(TOKENS["DEV_TOKEN_WINDOWS"], [{
        "EventID": 4625, "Computer": "PC-DEV", "Channel": "Security", "EventRecordID": random.randint(10**8, 10**9),
        "ProviderName": "Microsoft-Windows-Security-Auditing", "TimeCreated": "2026-11-08 10:00:00 +0000",
        "EventData": {"TargetUserName": marker, "LogonType": "3", "IpAddress": "10.0.4.23", "IpPort": "51240"}}])

    docs = await read("NORMALIZED_EVENTS", "normalized-events", marker, 4)
    assert len(docs) == 4
    by_type = {d["baolsec"]["source"]["type"]: d for d in docs}
    for d in docs:
        NORMALIZED.validate(d)
    assert by_type["linux"]["event"]["action"] == "ssh_login"
    assert by_type["firewall"]["event"]["action"] == "connection_denied"
    assert by_type["http"]["http"]["response"]["status_code"] == 404
    assert by_type["windows"]["event"]["code"] == "4625" and by_type["windows"]["user"]["name"] == marker
    # Enrichissement (C10) : nom déclaré dans le référentiel des sources
    assert by_type["linux"]["baolsec"]["source"]["name"] == "dev-linux"
    assert by_type["firewall"]["baolsec"]["ip_scope"] == {"source": "public", "destination": "private"}


async def test_ligne_illisible_en_file_de_rejet():
    marker = unique("illisible")
    await post(TOKENS["DEV_TOKEN_LINUX"], [{"log": f"pas une ligne syslog {marker}"}])
    dlq = await read("DLQ", "dlq.normalization-worker", marker, 1)
    assert len(dlq) == 1
    DLQ.validate(dlq[0])
    assert dlq[0]["reason_code"] == "parse_error" and dlq[0]["attempts"] == 1
    assert dlq[0]["original_stream"] == "raw-events"
    assert await read("NORMALIZED_EVENTS", "normalized-events", marker, 1, timeout=5) == []


async def test_criticite_modifiee_sans_redemarrage():
    path = DEV / "sources.json"
    original = path.read_text()
    data = json.loads(original)
    for s in data["sources"]:
        if s["name"] == "dev-linux":
            s["criticality"] = "critique"
    path.write_text(json.dumps(data, indent=2))
    try:
        await asyncio.sleep(REFRESH_S * 2 + 1)
        marker = unique("crit")
        await post(TOKENS["DEV_TOKEN_LINUX"], [linux_line(marker, 1)])
        docs = await read("NORMALIZED_EVENTS", "normalized-events", marker, 1)
        assert docs and docs[0]["baolsec"]["source"]["criticality"] == "critique"
    finally:
        path.write_text(original)


async def wait_consumer_idle(timeout: float = 120) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        nc = await nats.connect(BROKER_URL, token=BROKER_TOKEN)
        try:
            info = await nc.jetstream().consumer_info("RAW_EVENTS", "normalization")
        finally:
            await nc.close()
        if info.num_pending == 0 and info.num_ack_pending == 0:
            return
        await asyncio.sleep(1)
    pytest.fail(f"messages encore en attente : {info.num_pending} + {info.num_ack_pending} non acquittés")


async def test_arret_brutal_pendant_le_traitement():
    """Arrêt brutal pendant un flux de 3 000 événements : rien n'est perdu ni publié deux fois."""
    marker, n = unique("kill"), 3000
    sender = asyncio.create_task(post(TOKENS["DEV_TOKEN_LINUX"], [linux_line(marker, i) for i in range(n)]))
    await asyncio.sleep(0.5)
    run(KILL)
    await sender
    await asyncio.sleep(2)
    run(START)
    docs = await read("NORMALIZED_EVENTS", "normalized-events", marker, n, timeout=120)
    ids = [d["event"]["id"] for d in docs]
    assert len(set(ids)) == n, f"{n - len(set(ids))} événement(s) perdu(s)"
    assert len(ids) == n, f"{len(ids) - n} doublon(s)"
    await wait_consumer_idle()


async def test_deux_instances_se_partagent_le_flux():
    marker, n = unique("x2"), 2000
    run(SCALE2)
    try:
        await post(TOKENS["DEV_TOKEN_LINUX"], [linux_line(marker, i) for i in range(n)])
        docs = await read("NORMALIZED_EVENTS", "normalized-events", marker, n, timeout=120)
        ids = [d["event"]["id"] for d in docs]
        assert len(ids) == n and len(set(ids)) == n
    finally:
        run(SCALE1)
    await wait_consumer_idle()
