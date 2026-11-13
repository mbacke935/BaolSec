"""Middleware AuditLog — journalise chaque requête authentifiée (C21).

Pour chaque requête HTTP qui touche des endpoints sensibles :
  - Extrait le JWT (si présent) pour récupérer user_id
  - Insère une entrée dans acces.audit_log après la réponse

Endpoints exclus de l'audit : /health, /metrics, /docs, /redoc, /openapi.json
"""
from __future__ import annotations

import json
import logging
import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from ..auth import decode_token
from ..database import get_pool

logger = logging.getLogger("baolsec.audit")

# Endpoints qui ne génèrent pas d'entrée d'audit
_SKIP_PATHS = frozenset({"/health", "/metrics", "/docs", "/redoc", "/openapi.json", "/api/v1/auth/login", "/api/v1/auth/refresh"})


class AuditMiddleware(BaseHTTPMiddleware):
    """Journalise les actions des utilisateurs authentifiés dans acces.audit_log."""

    def __init__(self, app: ASGIApp, skip_paths: frozenset[str] = _SKIP_PATHS) -> None:
        super().__init__(app)
        self._skip = skip_paths

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Exécuter la requête d'abord
        start = time.monotonic()
        response: Response = await call_next(request)
        duration_ms = int((time.monotonic() - start) * 1000)

        path = request.url.path
        # Ignorer les endpoints système
        if any(path.startswith(p) for p in self._skip):
            return response

        # Extraire l'auteur depuis le JWT (Authorization: Bearer <token>)
        payload = None
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            payload = decode_token(auth_header[7:])

        # Ne journaliser que les requêtes authentifiées
        if payload is None:
            return response

        actor_id = payload.sub
        actor_username = payload.email or payload.sub  # actor_username est NOT NULL (C4)
        client_ip = request.client.host if request.client else None

        # Construire l'entrée d'audit (schéma normalisé acces.audit_log, C4)
        action = f"{request.method} {path}"
        # outcome : succès (2xx/3xx), refus (401/403) ou échec (autres erreurs)
        if response.status_code < 400:
            outcome = "succes"
        elif response.status_code in (401, 403):
            outcome = "refus"
        else:
            outcome = "echec"
        details = {
            "method": request.method,
            "path": path,
            "status": response.status_code,
            "duration_ms": duration_ms,
            "query": str(request.query_params) if request.query_params else None,
        }

        # Écriture asynchrone (best-effort — on ne bloque pas la réponse)
        try:
            pool = get_pool()
            async with pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """INSERT INTO acces.audit_log
                               (actor_id, actor_username, action, target_type,
                                target_id, outcome, details, client_ip)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                        (
                            actor_id,
                            actor_username,
                            action,
                            "endpoint",
                            path,
                            outcome,
                            json.dumps(details),
                            client_ip,
                        ),
                    )
        except Exception as exc:  # noqa: BLE001
            logger.warning("AuditLog write failed: %s", exc)

        return response
