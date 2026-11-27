"""Middleware AuditLog — trace les actions sensibles des utilisateurs authentifiés (C21, ES-07).

ES-07 demande un journal « des connexions, des actions d'administration, des changements de
règles et des changements de statut d'alerte et d'incident, en ajout seul ». Le middleware
trace donc toutes les requêtes de modification authentifiées (POST, PUT, PATCH, DELETE) :
gestion des utilisateurs, sources, identifiants, règles, paramètres, commandes sur les
alertes et les incidents, déconnexion. Les connexions (réussies ou refusées) sont tracées
par la route /auth/login elle-même, qui connaît l'issue réelle et le compte visé.

Les lectures ne sont pas tracées : un tableau de bord qui s'actualise toutes les 30 s
noierait le journal sans rien apporter à la traçabilité exigée.

Pour qu'une personne non technique comprenne chaque ligne, l'entrée enregistre aussi :
- ``label`` : le nom lisible de l'élément touché (source, compte, règle, incident, paramètre) ;
- ``changes`` : ce qui a été demandé, limité à une liste de champs sans secret (jamais de mot de
  passe ni de jeton ; un mot de passe modifié est seulement signalé) ;
- ``reason`` : en cas de refus ou d'échec, le message renvoyé par l'API.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from .. import audit
from ..auth import decode_token
from ..database import get_pool

MUTATING = frozenset({"POST", "PUT", "PATCH", "DELETE"})
# Tracées ailleurs (login) ou sans portée d'audit (renouvellement de jeton)
_SKIP_PATHS = frozenset({"/api/v1/auth/login", "/api/v1/auth/refresh"})
_PREFIX = "/api/v1/"


def target_of(path: str) -> tuple[str, str]:
    """('sources', '<id>') pour /api/v1/sources/<id>/credentials ; ('settings', 'cle') ; …"""
    parts = [p for p in path[len(_PREFIX):].split("/") if p] if path.startswith(_PREFIX) else [p for p in path.split("/") if p]
    if not parts:
        return "api", path
    return parts[0], (parts[1] if len(parts) > 1 else parts[0])


_MAX_BODY = 64 * 1024

# Champs de la requête recopiés dans l'audit : valeur courte, jamais de secret.
_KEEP = ("status", "state", "enabled", "active", "is_active", "role", "silence_threshold_s", "type",
         "name", "username", "email", "value", "reason")
_KEEP_CONFIG = ("transport", "environment", "criticality", "hostname", "ip_address", "responsible")


def _short(value: Any, limit: int = 300) -> Any:
    if isinstance(value, str):
        return value if len(value) <= limit else value[:limit] + "…"
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False)
        return value if len(text) <= limit else text[:limit] + "…"
    return value


def summarize_changes(body: Any) -> dict[str, Any]:
    """Résumé sûr de la demande : champs utiles à la lecture du journal, sans aucun secret."""
    if not isinstance(body, dict):
        return {}
    out: dict[str, Any] = {k: _short(body[k]) for k in _KEEP if k in body and body[k] is not None}
    if "assignee_id" in body:
        out["assignee_id"] = body["assignee_id"]
    if isinstance(body.get("config"), dict):
        cfg = {k: body["config"][k] for k in _KEEP_CONFIG if body["config"].get(k) is not None}
        if cfg:
            out["config"] = cfg
    if body.get("password"):
        out["password_changed"] = True
    if body.get("definition_yaml"):
        out["definition_changed"] = True
    if isinstance(body.get("body"), str):
        out["comment_length"] = len(body["body"])
    if body.get("comment"):
        out["comment_length"] = len(str(body["comment"]))
    if body.get("cert_fingerprint"):
        out["cert_fingerprint"] = str(body["cert_fingerprint"])[:23] + "…"
    return out


_GENERIC_PYDANTIC = {"string_type", "int_parsing", "int_type", "bool_parsing", "enum", "literal_error",
                     "string_too_short", "string_too_long", "greater_than_equal", "less_than_equal",
                     "uuid_parsing", "json_invalid", "extra_forbidden", "model_attributes_type"}


_FIELD_FR = {"name": "nom", "type": "type", "email": "adresse e-mail", "username": "identifiant",
             "password": "mot de passe", "role": "rôle", "ip_address": "adresse IP", "hostname": "nom de machine",
             "reason": "motif", "comment": "commentaire", "body": "texte", "value": "valeur",
             "silence_threshold_s": "seuil de silence", "definition_yaml": "définition", "limit": "nombre de résultats"}


def _reason(raw: bytes) -> str | None:
    try:
        detail = json.loads(raw).get("detail")
    except (ValueError, AttributeError):
        return None
    if isinstance(detail, str):
        return detail[:300]
    # Erreur de validation : préfixe technique de Pydantic retiré (« Value error, … »)
    if isinstance(detail, list) and detail and isinstance(detail[0], dict):
        # Erreur de validation FastAPI : premier message, avec le champ concerné
        # Les validateurs de l'API rédigent leurs messages en français : ils sont gardés tels quels.
        # Les messages génériques de Pydantic (en anglais) sont remplacés et nomment le champ.
        first = detail[0]
        loc = [str(x) for x in first.get("loc", [])[1:]]
        where = _FIELD_FR.get(loc[-1], ".".join(loc)) if loc else "requête"
        msg = str(first.get("msg", "")).removeprefix("Value error, ")
        kind = str(first.get("type", ""))
        if kind == "missing":
            return f"information obligatoire manquante : {where}"[:300]
        if not msg or kind in _GENERIC_PYDANTIC or msg[:1].isascii() and msg.split(" ")[0] in {"Input", "Field", "String", "Value", "Extra"}:
            return f"valeur non valable pour « {where} »"[:300]
        return msg[:300]
    return None


_LABEL_SQL = {
    "sources": "SELECT name FROM config.sources WHERE id = %s",
    "users": "SELECT username FROM acces.users WHERE id = %s",
    "rules": "SELECT name FROM config.rules WHERE id = %s",
    "incidents": "SELECT title FROM incidents.incidents WHERE id = %s",
    "alerts": """SELECT r.name FROM incidents.alert_state a JOIN config.rules r ON r.id = a.rule_id
                  WHERE a.alert_id = %s""",
}


async def lookup_label(target_type: str, target_id: str) -> str | None:
    """Nom lisible de l'élément visé ; None s'il est introuvable (best-effort, jamais bloquant)."""
    if target_type == "settings":
        return target_id
    sql = _LABEL_SQL.get(target_type)
    if sql is None:
        return None
    if target_type != "alerts":
        try:
            uuid.UUID(target_id)
        except ValueError:
            return None
    try:
        async with get_pool().connection() as conn:
            row = await (await conn.execute(sql, (target_id,))).fetchone()
        return row[0] if row else None
    except Exception:  # noqa: BLE001
        return None


async def lookup_username(user_id: Any) -> str | None:
    if not user_id:
        return None
    return await lookup_label("users", str(user_id))


class AuditMiddleware(BaseHTTPMiddleware):
    """Journalise les actions de modification des utilisateurs authentifiés dans acces.audit_log."""

    def __init__(self, app: ASGIApp, skip_paths: frozenset[str] = _SKIP_PATHS) -> None:
        super().__init__(app)
        self._skip = skip_paths

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start = time.monotonic()
        path = request.url.path
        traced = (request.method in MUTATING and path not in self._skip and path.startswith(_PREFIX))
        request_body: Any = None
        if traced and "json" in request.headers.get("content-type", ""):
            raw = await request.body()          # mis en cache : la route le relit normalement
            if len(raw) <= _MAX_BODY:
                try:
                    request_body = json.loads(raw) if raw else None
                except ValueError:
                    request_body = None
        response: Response = await call_next(request)
        if not traced:
            return response

        auth_header = request.headers.get("Authorization", "")
        payload = decode_token(auth_header[7:]) if auth_header.startswith("Bearer ") else None
        if payload is None and not path.endswith("/auth/logout"):
            return response          # anonyme : refusé en 401 avant toute action

        target_type, target_id = target_of(path)
        created = request.method == "POST" and target_id == target_type
        response_body = b""
        command = target_type in ("incidents", "alerts")   # résultat de commande dans le corps (C5 §6)
        if response.status_code >= 400 or created or command:
            # Corps relu pour le motif d'un refus ou l'identifiant d'un élément créé, puis renvoyé tel quel.
            response_body = b"".join([chunk async for chunk in response.body_iterator])
            response = Response(content=response_body, status_code=response.status_code,
                                headers=dict(response.headers), media_type=response.media_type)

        details: dict[str, Any] = {
            "status": response.status_code,
            "duration_ms": int((time.monotonic() - start) * 1000),
            "role": payload.role.value if payload else None,
        }
        changes = summarize_changes(request_body)
        if "assignee_id" in changes:
            changes["assignee_name"] = await lookup_username(changes["assignee_id"])
        if changes:
            details["changes"] = changes
        outcome = audit.outcome_from_status(response.status_code)
        if response.status_code >= 400:
            details["reason"] = _reason(response_body)
        elif command:
            # 200 avec une commande refusée par le service Incidents : c'est un refus, pas un succès.
            try:
                result = json.loads(response_body)
            except ValueError:
                result = {}
            if isinstance(result, dict) and result.get("result") in ("refusee", "en_erreur"):
                outcome = "refus" if result["result"] == "refusee" else "echec"
                err = result.get("error") or {}
                details["reason"] = str(err.get("message") or err.get("code") or result["result"])[:300]
        label = None
        if created and response.status_code < 400:
            try:
                created_doc = json.loads(response_body)
                target_id = str(created_doc.get("id") or target_id)
                label = created_doc.get("name") or created_doc.get("username") or created_doc.get("code")
            except (ValueError, AttributeError):
                pass
        if label is None and target_id != target_type:
            label = await lookup_label(target_type, target_id)
        if label:
            details["label"] = label

        await audit.record(
            actor_id=payload.sub if payload else None,
            actor_username=(payload.email or payload.sub) if payload else "anonyme",
            action=f"{request.method} {path}",
            target_type=target_type,
            target_id=target_id,
            outcome=outcome,
            details=details,
            client_ip=request.client.host if request.client else None,
        )
        return response
