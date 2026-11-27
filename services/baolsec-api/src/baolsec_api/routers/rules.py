"""Routes règles de détection (C20, C5, EF-05), schéma C4 config.rules / rule_versions / rule_requirements.

GET  /rules                       liste (Admin + Analyste)
POST /rules                       créer une règle (version 1) à partir de sa définition YAML (Admin)
GET  /rules/{id}                  règle et définition de la version appliquée (Admin + Analyste)
PUT  /rules/{id}                  nouvelle définition → nouvelle version ; ou activation (Admin)
GET  /rules/{id}/versions         historique des versions (Admin + Analyste)
POST /rules/{id}/enable|disable   activer / désactiver (Admin)
DELETE /rules/{id}                = désactivation (les règles ne sont jamais supprimées, C4 2.2)

La définition YAML (contrat rule/v1) est la source de vérité : nom, sévérité, type et exigences
de données en sont dérivés, comme le fait infrastructure/database/load_rules.py. L'identifiant
est l'UUID v5 du code de la règle (même calcul que detection-worker). detection-worker relit
la version courante des règles actives toutes les 30 s : une règle créée ou modifiée ici est
appliquée sans redémarrage.
"""
from __future__ import annotations

import uuid
from typing import Annotated

import yaml
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from .. import rulecheck
from ..dependencies import get_conn, get_current_user, paginate, require_role
from ..models import Page, RuleCreate, RuleResponse, RuleUpdate, TokenPayload, UserRole

router = APIRouter(prefix="/rules", tags=["rules"])

_READ = Depends(require_role(UserRole.ANALYST, UserRole.ADMIN))
_WRITE = Depends(require_role(UserRole.ADMIN))

_COLS = """r.id, r.name, r.description, r.rule_type::text AS rule_type, r.severity::text AS severity,
           r.is_enabled AS enabled, r.current_version AS version, r.created_at, r.updated_at,
           v.definition_yaml"""
_FROM = """FROM config.rules r
           LEFT JOIN config.rule_versions v ON v.rule_id = r.id AND v.version = r.current_version"""


def _contracts(request: Request):
    return request.app.state.settings.contracts_path


def _to_response(row: dict) -> dict:
    """Ajoute code, catégories et résumé de logique, lus dans la définition YAML."""
    data = dict(row)
    definition = {}
    if data.get("definition_yaml"):
        try:
            loaded = yaml.safe_load(data["definition_yaml"])
            definition = loaded if isinstance(loaded, dict) else {}
        except yaml.YAMLError:
            definition = {}
    data["code"] = definition.get("id")
    data["category"] = list(definition.get("category", []))
    data["logic"] = rulecheck.logic_summary(definition)
    return data


def _parse_or_422(text: str, request: Request) -> dict:
    try:
        return rulecheck.parse(text, _contracts(request))
    except rulecheck.RuleDefinitionError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


async def _write_requirements(cur, rule_id: uuid.UUID, data: dict) -> None:
    await cur.execute("DELETE FROM config.rule_requirements WHERE rule_id = %s", (rule_id,))
    for req in data.get("requires", []):
        await cur.execute(
            "INSERT INTO config.rule_requirements (rule_id, source_type, required_fields) "
            "VALUES (%s, %s::config.source_type, %s)",
            (rule_id, req["source_type"], req.get("fields") or None),
        )


async def _fetch(cur, rule_id) -> dict | None:
    await cur.execute(f"SELECT {_COLS} {_FROM} WHERE r.id = %s", (rule_id,))
    row = await cur.fetchone()
    return _to_response(row) if row else None


@router.get("", response_model=Page[RuleResponse])
async def list_rules(
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    _user=_READ,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    enabled_only: bool = False,
):
    where = " WHERE r.is_enabled = TRUE" if enabled_only else ""
    select_sql = f"SELECT {_COLS} {_FROM}{where} ORDER BY r.name"
    count_sql = f"SELECT COUNT(*) AS count FROM config.rules r{where}"
    page = await paginate(conn, select_sql, count_sql, [], limit, offset)
    page["items"] = [_to_response(r) for r in page["items"]]
    return page


@router.post("", response_model=RuleResponse, status_code=status.HTTP_201_CREATED)
async def create_rule(
    body: RuleCreate,
    request: Request,
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    current: Annotated[TokenPayload, Depends(get_current_user)],
    _user=_WRITE,
):
    data = _parse_or_422(body.definition_yaml, request)
    rule_id = rulecheck.rule_uuid(data["id"])
    enabled = data.get("enabled", True) if body.enabled is None else body.enabled
    async with conn.transaction():
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("SELECT 1 FROM config.rules WHERE id = %s OR name = %s", (rule_id, data["name"]))
            if await cur.fetchone() is not None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                    detail=f"Une règle porte déjà le code {data['id']} ou le nom « {data['name']} »")
            await cur.execute(
                """INSERT INTO config.rules (id, name, description, rule_type, severity, is_enabled,
                                             current_version, created_by)
                   VALUES (%s, %s, %s, %s::config.rule_type, %s::config.severity, %s, 1, %s)""",
                (rule_id, data["name"], data.get("description"), data["type"], data["severity"],
                 enabled, current.sub),
            )
            await cur.execute(
                "INSERT INTO config.rule_versions (rule_id, version, definition_yaml, checksum, created_by) "
                "VALUES (%s, 1, %s, %s, %s)",
                (rule_id, body.definition_yaml, rulecheck.checksum(body.definition_yaml), current.sub),
            )
            await _write_requirements(cur, rule_id, data)
            return await _fetch(cur, rule_id)


@router.get("/{rule_id}", response_model=RuleResponse)
async def get_rule(
    rule_id: uuid.UUID,
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    _user=_READ,
):
    async with conn.cursor(row_factory=dict_row) as cur:
        row = await _fetch(cur, rule_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Règle introuvable")
    return row


@router.put("/{rule_id}", response_model=RuleResponse)
async def update_rule(
    rule_id: uuid.UUID,
    body: RuleUpdate,
    request: Request,
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    current: Annotated[TokenPayload, Depends(get_current_user)],
    _user=_WRITE,
):
    if body.definition_yaml is None and body.enabled is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Aucun champ à modifier")
    async with conn.transaction():
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT r.id, r.current_version, v.checksum, v.definition_yaml FROM config.rules r "
                "LEFT JOIN config.rule_versions v ON v.rule_id = r.id AND v.version = r.current_version "
                "WHERE r.id = %s FOR UPDATE OF r",
                (rule_id,),
            )
            current_row = await cur.fetchone()
            if current_row is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Règle introuvable")

            if body.definition_yaml is not None:
                data = _parse_or_422(body.definition_yaml, request)
                old_code = None
                if current_row["definition_yaml"]:
                    try:
                        old_code = (yaml.safe_load(current_row["definition_yaml"]) or {}).get("id")
                    except yaml.YAMLError:
                        old_code = None
                if rulecheck.rule_uuid(data["id"]) != rule_id and old_code not in (None, data["id"]):
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=f"Le code d'une règle ne change pas ({old_code}) : créer une nouvelle règle.")
                digest = rulecheck.checksum(body.definition_yaml)
                if digest != current_row["checksum"]:
                    version = (current_row["current_version"] or 0) + 1
                    await cur.execute(
                        "INSERT INTO config.rule_versions (rule_id, version, definition_yaml, checksum, created_by) "
                        "VALUES (%s, %s, %s, %s, %s)",
                        (rule_id, version, body.definition_yaml, digest, current.sub),
                    )
                    await cur.execute(
                        """UPDATE config.rules SET name = %s, description = %s, rule_type = %s::config.rule_type,
                                  severity = %s::config.severity, current_version = %s, updated_at = now()
                            WHERE id = %s""",
                        (data["name"], data.get("description"), data["type"], data["severity"], version, rule_id),
                    )
                    await _write_requirements(cur, rule_id, data)
            if body.enabled is not None:
                await cur.execute("UPDATE config.rules SET is_enabled = %s, updated_at = now() WHERE id = %s",
                                  (body.enabled, rule_id))
            return await _fetch(cur, rule_id)


@router.get("/{rule_id}/versions")
async def rule_versions(
    rule_id: uuid.UUID,
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    _user=_READ,
):
    """Historique des versions d'une règle (C4 config.rule_versions, C5)."""
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """SELECT v.rule_id, v.version, v.checksum, v.definition_yaml, v.created_by,
                      u.username AS created_by_name, v.created_at
                 FROM config.rule_versions v LEFT JOIN acces.users u ON u.id = v.created_by
                WHERE v.rule_id = %s ORDER BY v.version DESC""",
            (rule_id,),
        )
        return await cur.fetchall()


async def _set_enabled(conn, rule_id: uuid.UUID, enabled: bool) -> None:
    async with conn.cursor() as cur:
        await cur.execute(
            "UPDATE config.rules SET is_enabled = %s, updated_at = NOW() WHERE id = %s RETURNING id",
            (enabled, rule_id),
        )
        if await cur.fetchone() is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Règle introuvable")


@router.post("/{rule_id}/enable", status_code=status.HTTP_204_NO_CONTENT)
async def enable_rule(rule_id: uuid.UUID, conn: Annotated[AsyncConnection, Depends(get_conn)], _user=_WRITE):
    await _set_enabled(conn, rule_id, True)


@router.post("/{rule_id}/disable", status_code=status.HTTP_204_NO_CONTENT)
async def disable_rule_post(rule_id: uuid.UUID, conn: Annotated[AsyncConnection, Depends(get_conn)], _user=_WRITE):
    await _set_enabled(conn, rule_id, False)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def disable_rule(
    rule_id: uuid.UUID,
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    _user=_WRITE,
):
    await _set_enabled(conn, rule_id, False)
