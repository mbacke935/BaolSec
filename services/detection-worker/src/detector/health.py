"""/health et /metrics sur un port interne (C3 4.1)."""
from __future__ import annotations

from typing import Callable

from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from .rules import RulesCache


def create_health_app(rules: RulesCache, broker_connected: Callable[[], bool]) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/health")
    async def health():
        broker_ok, rules_ok = broker_connected(), rules.usable
        body = {
            "status": "ok" if broker_ok and rules_ok else "degraded",
            "broker": "connected" if broker_ok else "disconnected",
            "rules": {"loaded": len(rules), "rejected": rules.rejected, "last_error": rules.last_error},
        }
        return JSONResponse(body, status_code=200 if body["status"] == "ok" else 503)

    @app.get("/metrics")
    async def prometheus():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app
