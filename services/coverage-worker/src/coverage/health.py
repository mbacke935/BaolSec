"""Serveur HTTP interne du service Couverture : /health et /metrics (C17).

Port 9001 (configurable). Pas de route de commande : le service est en lecture/écriture
autonome, sans API de contrôle externe.
"""
from __future__ import annotations

import logging
from typing import Awaitable, Callable

from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

log = logging.getLogger(__name__)


def create_app(
    *,
    broker_connected: Callable[[], bool],
    db_ready: Callable[[], Awaitable[bool]],
) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/health")
    async def health():
        broker_ok = broker_connected()
        db_ok = await db_ready()
        body = {
            "status": "ok" if broker_ok and db_ok else "degraded",
            "broker": "connected" if broker_ok else "disconnected",
            "postgresql": "reachable" if db_ok else "unreachable",
        }
        return JSONResponse(body, status_code=200 if body["status"] == "ok" else 503)

    @app.get("/metrics")
    async def prometheus():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app
