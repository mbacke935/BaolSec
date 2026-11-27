"""Écriture dans le journal d'audit acces.audit_log (ES-07, C4 4.1).

Le journal est en ajout seul : le compte svc_api n'a pas le droit UPDATE sur la table
(0005_comptes.sql). Une écriture d'audit en échec est journalisée mais ne fait jamais
échouer la requête de l'utilisateur.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from .database import get_pool

log = logging.getLogger("baolsec.audit")

OUTCOMES = frozenset({"succes", "refus", "echec"})


def outcome_from_status(status_code: int) -> str:
    """succes (2xx/3xx), refus (401/403/423/429), echec (autres erreurs)."""
    if status_code < 400:
        return "succes"
    if status_code in (401, 403, 423, 429):
        return "refus"
    return "echec"


async def record(
    *,
    actor_id: str | None,
    actor_username: str,
    action: str,
    target_type: str,
    target_id: str,
    outcome: str,
    details: dict[str, Any] | None = None,
    client_ip: str | None = None,
) -> None:
    if outcome not in OUTCOMES:
        outcome = "echec"
    try:
        pool = get_pool()
        async with pool.connection() as conn:
            await conn.execute(
                """INSERT INTO acces.audit_log
                       (actor_id, actor_username, action, target_type, target_id, outcome, details, client_ip)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (actor_id, actor_username or "anonyme", action, target_type, target_id, outcome,
                 json.dumps(details, ensure_ascii=False, default=str) if details else None, client_ip),
            )
    except Exception as exc:  # noqa: BLE001 — l'audit ne doit jamais casser la requête
        log.warning("écriture d'audit impossible : %s", exc)
