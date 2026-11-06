"""Tests de la collecte (carte C7) : coupure réseau puis reconnexion, comptage avant/après.

Critère : après une coupure réseau puis la reconnexion, les événements émis pendant la coupure
sont reçus, dans la limite du tampon configuré (vérifié par comptage).

Pile : make agents-up (broker, passerelle, agent Fluent Bit de test, relais Syslog). Puis make test-agents.
Variables (valeurs par défaut pour Docker Compose) :
  AGENT_CUT_CMD / AGENT_RESTORE_CMD   coupe / rétablit le réseau de l'agent Fluent Bit
  RELAY_CUT_CMD / RELAY_RESTORE_CMD   coupe / rétablit le réseau du relais Syslog
  AGENT_KILL_CMD / AGENT_START_CMD    arrêt brutal / redémarrage de l'agent
  RELAY_UDP                           adresse d'écoute du relais (défaut localhost:5514)
"""
from __future__ import annotations

import asyncio
import json
import os
import shlex
import socket
import subprocess
import time
import uuid
from pathlib import Path

import nats
import pytest
from nats.js.api import AckPolicy, ConsumerConfig, DeliverPolicy

ROOT = Path(__file__).resolve().parents[3]
LOG = ROOT / "test-data" / "runtime" / "agent" / "auth-test.log"
BROKER_URL = os.environ.get("BROKER_URL", "nats://localhost:4222")
BROKER_TOKEN = os.environ.get("BROKER_TOKEN")
NET = "baolsec-internal"
AGENT_CUT = os.environ.get("AGENT_CUT_CMD", f"docker network disconnect {NET} baolsec-agent-test-1")
AGENT_RESTORE = os.environ.get("AGENT_RESTORE_CMD", f"docker network connect {NET} baolsec-agent-test-1")
RELAY_CUT = os.environ.get("RELAY_CUT_CMD", f"docker network disconnect {NET} baolsec-syslog-relay-1")
RELAY_RESTORE = os.environ.get("RELAY_RESTORE_CMD", f"docker network connect {NET} baolsec-syslog-relay-1")
AGENT_KILL = os.environ.get("AGENT_KILL_CMD", "docker kill baolsec-agent-test-1")
AGENT_START = os.environ.get("AGENT_START_CMD", "docker start baolsec-agent-test-1")
RELAY_HOST, RELAY_PORT = os.environ.get("RELAY_UDP", "localhost:5514").rsplit(":", 1)

BEFORE, DURING = 50, 200     # événements émis avant puis pendant la coupure


def run(cmd: str) -> None:
    subprocess.run(shlex.split(cmd), cwd=ROOT, check=True, timeout=60)


async def count(marker: str) -> int:
    """Nombre d'événements de RAW_EVENTS (dernière heure) qui contiennent `marker`."""
    nc = await asyncio.wait_for(nats.connect(BROKER_URL, token=BROKER_TOKEN, allow_reconnect=False), 10)
    try:
        js = nc.jetstream()
        sub = await js.pull_subscribe("raw-events", durable=None, stream="RAW_EVENTS", config=ConsumerConfig(
            deliver_policy=DeliverPolicy.BY_START_TIME,
            opt_start_time=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 3600)),
            ack_policy=AckPolicy.NONE))
        n = 0
        while True:
            try:
                msgs = await sub.fetch(1000, timeout=1)
            except (asyncio.TimeoutError, nats.errors.TimeoutError):
                return n
            n += sum(1 for m in msgs if marker.encode() in m.data)
    finally:
        await nc.close()


async def wait_count(marker: str, expected: int, timeout: float) -> int:
    deadline = time.monotonic() + timeout
    n = 0
    while time.monotonic() < deadline:
        n = await count(marker)
        if n >= expected:
            return n
        await asyncio.sleep(2)
    return n


def write_lines(marker: str, start: int, n: int) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        for i in range(start, start + n):
            f.write(f"Nov  5 10:00:00 srv-test sshd[4242]: Failed password for invalid user u{i} "
                    f"from 10.0.4.23 port {40000 + i} ssh2 {marker} {i}\n")


def send_udp(marker: str, start: int, n: int) -> None:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    for i in range(start, start + n):
        msg = f"<134>Nov  5 10:00:00 fw-edge-01 filterlog[3012]: 5,,,1000000103,em0,match,block,in,4 {marker} {i}"
        s.sendto(msg.encode(), (RELAY_HOST, int(RELAY_PORT)))
        time.sleep(0.005)   # UDP sans contrôle de flux : on évite de saturer le tampon de réception
    s.close()


async def test_agent_fluent_bit_coupure_reseau():
    marker = f"agent-{uuid.uuid4().hex}"
    write_lines(marker, 0, BEFORE)
    assert await wait_count(marker, BEFORE, 60) == BEFORE, "avant la coupure"

    run(AGENT_CUT)
    try:
        write_lines(marker, BEFORE, DURING)
        await asyncio.sleep(10)
        assert await count(marker) == BEFORE, "pendant la coupure, rien ne doit passer"
    finally:
        run(AGENT_RESTORE)

    total = await wait_count(marker, BEFORE + DURING, 120)
    assert total == BEFORE + DURING, f"{BEFORE + DURING - total} événement(s) perdu(s)"
    await asyncio.sleep(5)
    assert await count(marker) == BEFORE + DURING, "aucun doublon après la reprise"


async def test_agent_arrete_brutalement_pendant_la_coupure():
    """Le tampon est sur disque : un arrêt brutal de l'agent pendant la coupure ne perd rien."""
    marker = f"agent-kill-{uuid.uuid4().hex}"
    run(AGENT_CUT)
    try:
        write_lines(marker, 0, 100)
        await asyncio.sleep(5)
        run(AGENT_KILL)
        write_lines(marker, 100, 50)            # écrit pendant que l'agent est arrêté
        run(AGENT_START)
        await asyncio.sleep(5)
    finally:
        run(AGENT_RESTORE)
    total = await wait_count(marker, 150, 120)
    assert total == 150, f"{150 - total} événement(s) perdu(s)"
    await asyncio.sleep(5)
    assert await count(marker) == 150, "aucun doublon après la reprise"


async def test_relais_syslog_coupure_reseau():
    marker = f"relay-{uuid.uuid4().hex}"
    send_udp(marker, 0, BEFORE)
    assert await wait_count(marker, BEFORE, 60) == BEFORE, "avant la coupure"

    run(RELAY_CUT)
    try:
        send_udp(marker, BEFORE, DURING)
        await asyncio.sleep(10)
        assert await count(marker) == BEFORE, "pendant la coupure, rien ne doit passer"
    finally:
        run(RELAY_RESTORE)

    total = await wait_count(marker, BEFORE + DURING, 120)
    assert total == BEFORE + DURING, f"{BEFORE + DURING - total} événement(s) perdu(s)"
