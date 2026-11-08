"""/health et /metrics sur un port interne (C3 4.1)."""
from __future__ import annotations

from typing import Callable

from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from . import metrics
from .sources import SourcesCache


def create_health_app(cache: SourcesCache, broker_connected: Callable[[], bool]) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/health")
    async def health():
        broker_ok, sources_ok = broker_connected(), cache.usable
        body = {
            "status": "ok" if broker_ok and sources_ok else "degraded",
            "broker": "connected" if broker_ok else "disconnected",
            "sources_cache": {"usable": sources_ok, "sources": len(cache),
                              "age_s": None if cache.age_s is None else round(cache.age_s, 1),
                              "last_error": cache.last_error},
        }
        return JSONResponse(body, status_code=200 if body["status"] == "ok" else 503)

    @app.get("/metrics")
    async def prometheus():
        if cache.age_s is not None:
            metrics.SOURCES_CACHE_AGE.set(cache.age_s)
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app
