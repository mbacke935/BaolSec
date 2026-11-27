"""Client des commandes vers le service Incidents (C5 §6).

L'API ne modifie jamais les incidents ni les alertes directement : elle envoie une
commande `incident_command/v1` par un appel HTTP interne authentifié (secret
partagé), puis relaie le résultat `incident_command_result/v1`. L'en-tête
Idempotency-Key fourni par l'interface sert de command_id (clé d'idempotence).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import HTTPException

_url: str = "http://incident-builder:9104/commands"
_token: str = ""
_timeout: float = 10.0


def configure(url: str, token: str, timeout_s: float = 10.0) -> None:
    global _url, _token, _timeout
    _url, _token, _timeout = url, token, timeout_s


class CommandError(Exception):
    """Échec d'envoi/traitement d'une commande ; porte le code HTTP à relayer."""

    def __init__(self, status_code: int, detail: Any):
        super().__init__(str(detail))
        self.status_code = status_code
        self.detail = detail


async def send_command(
    *,
    command_type: str,
    target: dict[str, str],
    issued_by: dict[str, str],
    payload: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Construit l'enveloppe incident_command/v1 et la transmet à incident-builder.

    `target` = {"incident_id": ...} ou {"alert_id": ...}.
    `issued_by` = {"user_id": ..., "username": ...}.
    Renvoie le résultat JSON du service ; lève CommandError sur refus/erreur.
    """
    cmd = {
        "contract": "incident_command/v1",
        "command_id": idempotency_key or str(uuid.uuid4()),
        "command_type": command_type,
        "target": target,
        "issued_by": issued_by,
        "issued_at": datetime.now(timezone.utc).isoformat(),
        "payload": payload or {},
    }
    try:
        async with httpx.AsyncClient(timeout=_timeout) as client:
            resp = await client.post(_url, json=cmd, headers={"Authorization": f"Bearer {_token}"})
    except httpx.HTTPError as exc:
        raise CommandError(503, f"Service Incidents injoignable : {exc}") from exc

    if resp.status_code >= 400:
        try:
            detail = resp.json()
        except ValueError:
            detail = resp.text
        raise CommandError(resp.status_code, detail)
    return resp.json()


def is_uuid(value: str | None) -> bool:
    try:
        uuid.UUID(str(value))
        return value is not None
    except ValueError:
        return False


def assignee_from(body: dict) -> str | None:
    """Identifiant de l'analyste à assigner (None = désassigner), validé avant envoi."""
    raw = body.get("assignee_id", body.get("assigned_to", body.get("user_id")))
    if raw in (None, ""):
        return None
    if not is_uuid(raw):
        raise HTTPException(status_code=422, detail="Identifiant d'analyste invalide")
    return str(uuid.UUID(str(raw)))
