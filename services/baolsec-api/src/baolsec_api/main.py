"""Point d'entrée de l'API BaolSec (C20).

Responsabilités :
  - Lifespan : init pool PostgreSQL, auth JWT, client OpenSearch, Prometheus
  - CORS + logging middleware
  - Montage des routers
  - Endpoints /health et /metrics
"""
from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

import uvicorn
from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from opensearchpy import AsyncOpenSearch
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from . import auth
from . import commandclient
from .config import Settings
from .database import close_pool, init_pool
from .routers import admin, alerts, auth as auth_router, coverage, incidents, rules, search, sources, users


# ── Logging JSON ──────────────────────────────────────────────────────────────

class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        })


def _setup_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)


# ── Prometheus ─────────────────────────────────────────────────────────────────

REQUEST_COUNT = Counter(
    "baolsec_api_requests_total",
    "Total des requêtes HTTP",
    ["method", "path", "status"],
)
REQUEST_LATENCY = Histogram(
    "baolsec_api_request_duration_seconds",
    "Durée des requêtes HTTP",
    ["method", "path"],
)


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    _setup_logging()
    s = Settings()

    # PostgreSQL
    await init_pool(s.postgres_dsn)

    # JWT (jetons courts + renouvellement, C3/C5)
    auth.configure(
        s.jwt_secret,
        algorithm=s.jwt_algorithm,
        expire_minutes=s.jwt_expire_minutes,
        refresh_expire_minutes=s.jwt_refresh_expire_minutes,
    )

    # Commandes vers le service Incidents (C5 §6)
    commandclient.configure(s.incidents_command_url, s.command_token, s.incidents_command_timeout_s)

    # OpenSearch
    os_client = AsyncOpenSearch(
        hosts=s.opensearch_url,
        use_ssl=s.opensearch_url.startswith("https"),
        verify_certs=False,
        http_compress=True,
    )
    search.set_opensearch_client(os_client)

    logging.getLogger("baolsec.api").info("API démarrée")
    yield

    await close_pool()
    await os_client.close()
    logging.getLogger("baolsec.api").info("API arrêtée")


# ── Application ───────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(
        title="BaolSec API",
        version="1.0.0",
        description="API REST du SIEM BaolSec",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS (restreint en production via env var)
    origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:3001").split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Middleware Prometheus
    @app.middleware("http")
    async def prometheus_middleware(request: Request, call_next):
        import time
        path = request.url.path
        method = request.method
        start = time.monotonic()
        response = await call_next(request)
        duration = time.monotonic() - start
        REQUEST_COUNT.labels(method=method, path=path, status=response.status_code).inc()
        REQUEST_LATENCY.labels(method=method, path=path).observe(duration)
        return response

    # Routers — montés sous le préfixe /api/v1 (C5).
    # /health et /metrics restent à la racine (supervision).
    api_v1 = APIRouter(prefix="/api/v1")
    for r in (
        auth_router.router, sources.router, rules.router, incidents.router,
        alerts.router, coverage.router, users.router, search.router, admin.router,
    ):
        api_v1.include_router(r)
    app.include_router(api_v1)

    # Health check
    @app.get("/health", include_in_schema=False)
    async def health():
        return JSONResponse({"status": "ok", "service": "baolsec-api"})

    # Métriques Prometheus
    @app.get("/metrics", include_in_schema=False)
    async def metrics():
        return PlainTextResponse(
            generate_latest().decode(),
            media_type=CONTENT_TYPE_LATEST,
        )

    return app


app = create_app()


if __name__ == "__main__":
    s = Settings()
    uvicorn.run(
        "baolsec_api.main:app",
        host="0.0.0.0",
        port=s.api_port,
        log_config=None,  # On utilise notre propre logging
    )
