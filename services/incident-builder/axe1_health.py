"""Serveur HTTP interne du service Incidents (C3 4.1, C5 section 6) : /health, /metrics et POST /commands.

Un seul port, jamais publié hors du réseau Docker interne. /commands exige le secret partagé avec l'API
(en-tête Authorization: Bearer) ; /health et /metrics n'en ont pas besoin, comme dans les autres services.
"""
from __future__ import annotations

import hmac
import logging
from typing import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

import uuid

from .commands import CommandService
from .contracts import Contracts
from .repositories import DatabaseUnavailable
from .repositories import incidents as inc_repo
from .timeline import timeline_to_response

log = logging.getLogger(__name__)


def problem(status: int, title: str, detail: str) -> JSONResponse:
    return JSONResponse({"title": title, "detail": detail}, status_code=status, media_type="application/problem+json")


def create_app(*, broker_connected: Callable[[], bool], db_ready: Callable[[], Awaitable[bool]],
               commands: CommandService, contracts: Contracts, command_token: str,
               db=None) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    secret = command_token.encode("utf-8")

    @app.get("/health")
    async def health():
        broker_ok, db_ok = broker_connected(), await db_ready()
        body = {"status": "ok" if broker_ok and db_ok else "degraded",
                "broker": "connected" if broker_ok else "disconnected",
                "postgresql": "reachable" if db_ok else "unreachable"}
        return JSONResponse(body, status_code=200 if body["status"] == "ok" else 503)

    @app.get("/metrics")
    async def prometheus():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.get("/incidents/{incident_id}/timeline")
    async def get_timeline(incident_id: str, request: Request):
        header = request.headers.get("authorization", "")
        if not (header.startswith("Bearer ") and hmac.compare_digest(header[7:].encode("utf-8"), secret)):
            return problem(401, "Non authentifié", "secret de l'API absent ou incorrect")
        try:
            iid = uuid.UUID(incident_id)
        except ValueError:
            return problem(400, "Identifiant invalide", f"{incident_id!r} n'est pas un UUID valide")
        if db is None:
            return problem(503, "Base indisponible", "aucune base configurée")
        try:
            async with db.connection() as conn:
                inc = await inc_repo.get_incident(conn, iid)
                if inc is None:
                    return problem(404, "Incident introuvable", f"aucun incident avec l'identifiant {incident_id}")
                entries = await inc_repo.list_timeline(conn, iid)
        except DatabaseUnavailable as exc:
            log.warning("timeline %s : PostgreSQL indisponible (%s)", incident_id, exc)
            return problem(503, "Base indisponible", "impossible de lire la chronologie")
        return JSONResponse(timeline_to_response(incident_id, entries))

    @app.post("/commands")
    async def command(request: Request):
        header = request.headers.get("authorization", "")
        if not (header.startswith("Bearer ") and hmac.compare_digest(header[7:].encode("utf-8"), secret)):
            return problem(401, "Non authentifié", "secret de l'API absent ou incorrect")
        try:
            cmd = await request.json()
        except ValueError:
            return problem(400, "Commande illisible", "le corps n'est pas du JSON")
        errors = contracts.command_errors(cmd)
        if errors:
            return problem(400, "Commande non conforme à incident_command/v1", errors)
        try:
            return JSONResponse(await commands.apply(cmd))
        except DatabaseUnavailable as exc:
            log.warning("commande %s : PostgreSQL indisponible (%s)", cmd.get("command_id"), exc)
            return problem(503, "Base indisponible", "rien n'a été enregistré : renvoyer la commande avec le même command_id")
        except Exception:
            log.exception("commande %s : erreur interne", cmd.get("command_id"))
            return problem(500, "Erreur interne", "rien n'a été enregistré : renvoyer la commande avec le même command_id")

    return app
