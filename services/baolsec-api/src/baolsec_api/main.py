"""Point d'entrée de l'API BaolSec (C20).

Responsabilités :
  - Lifespan : pool PostgreSQL, auth JWT (verrouillage ES-01), client OpenSearch, broker (DLQ)
  - Middlewares : protection ES-05 (débit, taille, en-têtes), audit ES-07, CORS, métriques
  - Montage des routers sous /api/v1
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
from . import broker
from . import commandclient
from .config import Settings
from .database import close_pool, init_pool
from .middleware import AuditMiddleware
from .middleware.security import SecurityMiddleware
from .routers import admin, alerts, auth as auth_router, coverage, incidents, rules, search, sources, system, users


# ── Logging JSON ──────────────────────────────────────────────────────────────

class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # Sans ceci, la trace d'une exception non gérée (erreur 500) était perdue : seul
        # « Exception in ASGI application » apparaissait dans les journaux.
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


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
    app.state.settings = s

    # PostgreSQL
    await init_pool(s.postgres_dsn, max_size=s.db_pool_size, timeout_s=s.db_timeout_s)

    # JWT (jetons courts + renouvellement, C3/C5)
    auth.configure(
        s.jwt_secret,
        algorithm=s.jwt_algorithm,
        expire_minutes=s.jwt_expire_minutes,
        refresh_expire_minutes=s.jwt_refresh_expire_minutes,
        failed_attempts=s.auth_max_failed_attempts,
        lockout_mins=s.auth_lockout_minutes,
    )

    # File de rejet (lecture seule) et état des flux
    broker.configure(s.broker_url, s.broker_token, s.dlq_stream)

    # Commandes vers le service Incidents (C5 §6)
    commandclient.configure(s.incidents_command_url, s.command_token, s.incidents_command_timeout_s)

    # OpenSearch
    use_ssl = s.opensearch_url.startswith("https")
    os_kwargs: dict = {
        "hosts": s.opensearch_url,
        "use_ssl": use_ssl,
        "http_compress": True,
    }
    if s.opensearch_user and s.opensearch_password:
        os_kwargs["http_auth"] = (s.opensearch_user, s.opensearch_password)
    if use_ssl:
        if s.opensearch_ca_cert:
            os_kwargs["verify_certs"] = True
            os_kwargs["ca_certs"] = s.opensearch_ca_cert
        elif not s.opensearch_verify_certs:
            # Développement avec le certificat de démonstration d'OpenSearch : chiffré, non authentifié.
            logging.getLogger("baolsec.api").warning(
                "OpenSearch en HTTPS sans vérification du certificat (OPENSEARCH_VERIFY_CERTS=false) : "
                "réservé au développement.")
            os_kwargs["verify_certs"] = False
            os_kwargs["ssl_show_warn"] = False
        else:
            raise RuntimeError(
                "OPENSEARCH_CA_CERT est obligatoire quand l'URL OpenSearch est HTTPS "
                "(ou OPENSEARCH_VERIFY_CERTS=false en développement uniquement)."
            )
    else:
        # HTTP local en développement uniquement.
        os_kwargs["verify_certs"] = False
    os_client = AsyncOpenSearch(**os_kwargs)
    search.set_opensearch_client(os_client)
    system.configure(s.health_targets, os_client)

    logging.getLogger("baolsec.api").info("API démarrée")
    yield

    await broker.close()
    await close_pool()
    await os_client.close()
    logging.getLogger("baolsec.api").info("API arrêtée")


# ── Application ───────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    s = Settings()
    # /docs et /redoc sont désactivés en production (DEBUG=false).
    # En développement, positionner DEBUG=true dans le .env.
    _docs_url = "/docs" if s.debug else None
    _redoc_url = "/redoc" if s.debug else None

    app = FastAPI(
        title="BaolSec API",
        version="1.0.0",
        description="API REST du SIEM BaolSec",
        lifespan=lifespan,
        docs_url=_docs_url,
        redoc_url=_redoc_url,
    )

    app.state.settings = s

    # Audit des actions sensibles (ES-07) : acces.audit_log, ajout seul
    app.add_middleware(AuditMiddleware)

    # CORS restreint (ES-05) : origines explicites, jamais « * »
    origins = [o.strip() for o in s.cors_origins.split(",") if o.strip() and o.strip() != "*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
    )

    # Protection (ES-05) : limitation de débit, taille maximale, en-têtes de sécurité.
    # Ajouté en dernier : c'est la couche la plus externe.
    app.add_middleware(SecurityMiddleware, max_body_bytes=s.max_body_bytes,
                       rate_per_minute=s.rate_limit_per_minute, login_per_minute=s.login_rate_limit_per_minute)

    # Middleware Prometheus
    @app.middleware("http")
    async def prometheus_middleware(request: Request, call_next):
        import time
        method = request.method
        start = time.monotonic()
        response = await call_next(request)
        duration = time.monotonic() - start
        # Modèle de route (/api/v1/sources/{source_id}) et non chemin brut : sinon une série
        # Prometheus par identifiant (cardinalité non bornée).
        route = request.scope.get("route")
        path = getattr(route, "path", None) or "non_route"
        REQUEST_COUNT.labels(method=method, path=path, status=response.status_code).inc()
        REQUEST_LATENCY.labels(method=method, path=path).observe(duration)
        return response

    # Routers — montés sous le préfixe /api/v1 (C5).
    # /health et /metrics restent à la racine (supervision).
    api_v1 = APIRouter(prefix="/api/v1")
    for r in (
        auth_router.router, sources.router, rules.router, incidents.router,
        alerts.router, coverage.router, users.router, search.router, search.events_router,
        admin.router, system.router,
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
        app,
        host=s.api_host,
        port=s.api_port,
        log_config=None,  # On utilise notre propre logging
        proxy_headers=True,
        forwarded_allow_ips=os.getenv("FORWARDED_ALLOW_IPS", "127.0.0.1"),
    )
