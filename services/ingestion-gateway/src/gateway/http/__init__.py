"""Point d'entrée HTTPS : POST /ingest (C3 4.3, W1).

Codes de réponse et comportement de Fluent Bit (sortie http, vérifié dans son code source) :
- 202 : lot accepté ; les événements invalides sont listés dans « rejected » et ne sont pas renvoyés.
- 400, 401, 413 : l'agent abandonne le lot sans réessayer.
- 429, 503 : l'agent garde le lot dans son tampon et réessaie.
Les réponses d'erreur suivent RFC 9457 (application/problem+json), comme l'API.
"""
from __future__ import annotations

import json
import math

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from baolsec_common.messaging import BrokerUnavailable

from .. import metrics
from ..auth import bearer_token, hash_token
from ..config import Settings
from ..publisher import RawEventPublisher
from ..rate_limit import RateLimiter
from ..sources_cache import SourcesCache
from ..validation import agent_name_from, http_records, utc_now

T = "https"


def problem(status: int, title: str, detail: str, headers: dict | None = None, **extra) -> JSONResponse:
    body = {"type": "about:blank", "title": title, "status": status, "detail": detail, **extra}
    return JSONResponse(body, status_code=status, headers=headers, media_type="application/problem+json")


def create_app(settings: Settings, cache: SourcesCache, limiter: RateLimiter, publisher: RawEventPublisher) -> FastAPI:
    app = FastAPI(title="BaolSec — passerelle d'ingestion", docs_url=None, redoc_url=None, openapi_url=None)

    @app.post("/ingest")
    async def ingest(request: Request):
        # 1. Authentification de la source
        if not cache.usable:
            metrics.REJECTIONS.labels(T, "sources_unavailable").inc()
            return problem(503, "Service indisponible", "Référentiel des sources indisponible.",
                           {"Retry-After": "10"})
        token = bearer_token(request.headers.get("authorization"))
        source = cache.by_token_hash(hash_token(token)) if token else None
        if source is None:
            metrics.REJECTIONS.labels(T, "unauthenticated").inc()
            return problem(401, "Source non authentifiée", "Jeton absent, inconnu, expiré ou révoqué.",
                           {"WWW-Authenticate": "Bearer"})

        # 2. Taille et format du lot
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > settings.max_body_bytes:
            metrics.REJECTIONS.labels(T, "too_large").inc()
            return problem(413, "Lot trop volumineux", f"Taille maximale : {settings.max_body_bytes} octets.")
        body = bytearray()
        async for chunk in request.stream():
            body += chunk
            if len(body) > settings.max_body_bytes:
                metrics.REJECTIONS.labels(T, "too_large").inc()
                return problem(413, "Lot trop volumineux", f"Taille maximale : {settings.max_body_bytes} octets.")
        try:
            records = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            metrics.REJECTIONS.labels(T, "malformed").inc()
            return problem(400, "Lot invalide", "Le corps n'est pas du JSON valide.")
        if not isinstance(records, list) or not records:
            metrics.REJECTIONS.labels(T, "malformed").inc()
            return problem(400, "Lot invalide", "Le corps doit être un tableau JSON non vide d'événements.")
        if len(records) > settings.max_events_per_batch:
            metrics.REJECTIONS.labels(T, "too_many_events").inc()
            return problem(413, "Lot trop volumineux",
                           f"{len(records)} événements ; maximum {settings.max_events_per_batch} par lot.")

        # 3. Limitation de débit par source
        wait = limiter.try_acquire(source.id, len(records))
        if wait > 0:
            metrics.REJECTIONS.labels(T, "rate_limited").inc()
            retry = "60" if math.isinf(wait) else str(max(1, math.ceil(wait)))
            return problem(429, "Limite de débit dépassée", f"Source {source.name} : réessayer plus tard.",
                           {"Retry-After": retry})

        # 4. Validation événement par événement
        events, rejected = http_records(records, source, utc_now(), settings.max_event_chars,
                                        agent_name_from(request.headers.get("user-agent")))
        if rejected:
            metrics.EVENTS.labels(source.id, T, "rejected").inc(len(rejected))
        if not events:
            return problem(400, "Lot invalide", "Aucun événement valide dans le lot.",
                           rejected=[r.__dict__ for r in rejected])

        # 5. Publication durable, réponse après les PubAck
        try:
            summary = await publisher.publish_all(events)
        except BrokerUnavailable:
            return problem(503, "Service indisponible", "Broker indisponible, renvoyer le lot.",
                           {"Retry-After": "5"})
        metrics.EVENTS.labels(source.id, T, "stored").inc(summary.stored)
        metrics.EVENTS.labels(source.id, T, "duplicate").inc(summary.duplicates)
        return JSONResponse(
            {"accepted": len(events), "stored": summary.stored, "duplicates": summary.duplicates,
             "rejected": [r.__dict__ for r in rejected]},
            status_code=202,
        )

    return app
