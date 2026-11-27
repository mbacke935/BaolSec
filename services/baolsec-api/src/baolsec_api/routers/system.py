"""Supervision de la plateforme depuis l'interface (EF-12, page « Supervision »).

GET /system/health : état de chaque service (via son /health interne), de PostgreSQL,
d'OpenSearch et du broker, avec le retard des consommateurs JetStream. Lecture seule ;
les métriques détaillées et l'historique restent dans Prometheus et Grafana.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Depends

from .. import broker
from ..database import get_pool
from ..dependencies import require_role
from ..models import UserRole

router = APIRouter(prefix="/system", tags=["system"])

_READ = Depends(require_role(UserRole.ANALYST, UserRole.ADMIN))

_targets: dict[str, str] = {}
_os_client = None


def configure(targets: dict[str, str], os_client=None) -> None:
    global _targets, _os_client
    _targets, _os_client = dict(targets), os_client


async def _http(name: str, url: str) -> dict[str, Any]:
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(url)
        latency = int((time.monotonic() - start) * 1000)
        body: Any
        try:
            body = resp.json()
        except ValueError:
            body = resp.text[:200]
        ok = resp.status_code == 200 and (not isinstance(body, dict) or body.get("status", "ok") == "ok")
        return {"name": name, "kind": "service", "status": "up" if ok else "degraded",
                "latency_ms": latency, "detail": body}
    except Exception as exc:  # noqa: BLE001
        return {"name": name, "kind": "service", "status": "down", "latency_ms": None,
                "detail": f"injoignable ({type(exc).__name__})"}


async def _postgres() -> dict[str, Any]:
    start = time.monotonic()
    try:
        async with get_pool().connection() as conn:
            await conn.execute("SELECT 1")
        return {"name": "postgresql", "kind": "donnees", "status": "up",
                "latency_ms": int((time.monotonic() - start) * 1000), "detail": "connexion svc_api"}
    except Exception as exc:  # noqa: BLE001
        return {"name": "postgresql", "kind": "donnees", "status": "down", "latency_ms": None,
                "detail": type(exc).__name__}


async def _opensearch() -> dict[str, Any]:
    if _os_client is None:
        return {"name": "opensearch", "kind": "donnees", "status": "down", "latency_ms": None,
                "detail": "client non configuré"}
    start = time.monotonic()
    try:
        health = await asyncio.wait_for(_os_client.cluster.health(), 3)
        color = health.get("status", "red")
        return {"name": "opensearch", "kind": "donnees",
                "status": "up" if color in ("green", "yellow") else "degraded",
                "latency_ms": int((time.monotonic() - start) * 1000), "detail": f"cluster {color}"}
    except Exception as exc:  # noqa: BLE001
        return {"name": "opensearch", "kind": "donnees", "status": "down", "latency_ms": None,
                "detail": f"injoignable ({type(exc).__name__})"}


async def _broker() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    start = time.monotonic()
    try:
        streams = await asyncio.wait_for(broker.streams_status(), 4)
        ok = all(s.get("available") for s in streams)
        return ({"name": "nats-jetstream", "kind": "donnees", "status": "up" if ok else "degraded",
                 "latency_ms": int((time.monotonic() - start) * 1000),
                 "detail": f"{sum(1 for s in streams if s.get('available'))}/{len(streams)} flux disponibles"},
                streams)
    except Exception as exc:  # noqa: BLE001
        return ({"name": "nats-jetstream", "kind": "donnees", "status": "down", "latency_ms": None,
                 "detail": f"injoignable ({type(exc).__name__})"}, [])


@router.get("/health")
async def platform_health(_user=_READ):
    results = await asyncio.gather(
        *(_http(n, u) for n, u in _targets.items()), _postgres(), _opensearch(), _broker(),
    )
    broker_status, streams = results[-1]
    components = [{"name": "baolsec-api", "kind": "service", "status": "up", "latency_ms": 0,
                   "detail": "répond"}] + list(results[:-1]) + [broker_status]
    # Indisponible : la chaîne ne peut plus traiter (base de référence ou broker hors service).
    # Dégradé : un autre composant ne répond pas (ex. OpenSearch : la recherche est coupée mais
    # l'ingestion, la détection et les incidents continuent, les messages attendent dans le broker).
    critical = {"postgresql", "nats-jetstream"}
    if any(c["status"] == "down" and c["name"] in critical for c in components):
        overall = "down"
    elif any(c["status"] != "up" for c in components):
        overall = "degraded"
    else:
        overall = "up"
    return {
        "status": overall,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "components": components,
        "streams": streams,
    }

