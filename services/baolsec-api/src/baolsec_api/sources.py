"""Routes de gestion des sources (C20), schéma C4 config.sources.

GET /sources · POST /sources (ADMIN) · GET /sources/{id} · PUT /sources/{id} (ADMIN)
· DELETE /sources/{id} = désactivation (ADMIN).

Les colonnes C4 (source_type, is_enabled, transport, host, criticality…) sont
exposées sous la forme de réponse de l'API via des alias.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from ..dependencies import get_conn, paginate, require_role
from ..models import Page, SourceCreate, SourceResponse, SourceUpdate, UserRole

router = APIRouter(prefix="/sources", tags=["sources"])

_READ = Depends(require_role(UserRole.ANALYST, UserRole.ADMIN))
_WRITE = Depends(require_role(UserRole.ADMIN))

# Projection des colonnes C4 vers la forme de réponse SourceResponse.
# Les 5 nouveaux champs (hostname, ip_address, environment, tags, responsible)
# sont inclus dans le jsonb_build_object retourné en tant que config.
_COLS = """id, name, description, source_type AS type, is_enabled AS active,
           silence_threshold_s,
           jsonb_build_object(
               'transport', transport,
               'ingestion_mode', ingestion_mode,
               'host', host,
               'criticality', criticality,
               'expected_min_events_per_h', expected_min_events_per_h,
               'hostname', hostname,
               'ip_address', ip_address::TEXT,
               'environment', environment,
               'tags', COALESCE(tags, '{}'),
               'responsible', responsible
           ) AS config,
           created_at, updated_at"""


@router.get("", response_model=Page[SourceResponse])
async def list_sources(
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    _user=_READ,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    active_only: bool = False,
):
    where = " WHERE is_enabled = TRUE" if active_only else ""
    select_sql = f"SELECT {_COLS} FROM config.sources{where} ORDER BY name"
    count_sql = f"SELECT COUNT(*) AS count FROM config.sources{where}"
    return await paginate(conn, select_sql, count_sql, [], limit, offset)


@router.post("", response_model=SourceResponse, status_code=status.HTTP_201_CREATED)
async def create_source(
    body: SourceCreate,
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    _user=_WRITE,
):
    cfg = body.config.model_dump()
    async with conn.cursor(row_factory=dict_row) as cur:
        try:
            await cur.execute(
                f"""INSERT INTO config.sources
                    (name, description, source_type, transport, ingestion_mode, host,
                     criticality, silence_threshold_s, expected_min_events_per_h, is_enabled,
                     hostname, ip_address, environment, tags, responsible)
                    VALUES (%s, %s, %s::config.source_type, %s::config.transport,
                            %s::config.ingestion_mode, %s, %s::config.criticality,
                            %s, %s, %s,
                            %s, %s::INET, %s, %s, %s)
                    RETURNING {_COLS}""",
                (
                    body.name,
                    body.description,
                    body.type,
                    cfg.get("transport", "https"),
                    cfg.get("ingestion_mode", "direct"),
                    cfg.get("host"),
                    cfg.get("criticality"),
                    body.silence_threshold_s,
                    cfg.get("expected_min_events_per_h"),
                    body.active,
                    cfg.get("hostname"),
                    cfg.get("ip_address"),
                    cfg.get("environment"),
                    cfg.get("tags") or [],
                    cfg.get("responsible"),
                ),
            )
        except Exception as exc:
            if "unique" in str(exc).lower():
                raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                    detail="Nom de source déjà utilisé")
            raise
        return await cur.fetchone()


@router.get("/{source_id}", response_model=SourceResponse)
async def get_source(
    source_id: uuid.UUID,
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    _user=_READ,
):
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            f"SELECT {_COLS} FROM config.sources WHERE id = %s", (source_id,)
        )
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source introuvable")
    return row


@router.put("/{source_id}", response_model=SourceResponse)
async def update_source(
    source_id: uuid.UUID,
    body: SourceUpdate,
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    _user=_WRITE,
):
    src = body.model_dump(exclude_unset=True)
    # Traduction des champs de la requête vers les colonnes C4.
    col_map = {
        "type": "source_type",
        "active": "is_enabled",
        "silence_threshold_s": "silence_threshold_s",
        "description": "description",
    }
    set_parts: list[str] = []
    values: list = []

    for key, col in col_map.items():
        if key in src:
            set_parts.append(f"{col} = %s")
            values.append(src[key])

    cfg = src.get("config") or {}

    # Champs config avec cast ENUM ou INET
    cfg_cast_map = {
        "transport":                ("transport",   "::config.transport"),
        "ingestion_mode":           ("ingestion_mode", "::config.ingestion_mode"),
        "criticality":              ("criticality", "::config.criticality"),
        "host":                     ("host",        ""),
        "expected_min_events_per_h":("expected_min_events_per_h", ""),
        "hostname":                 ("hostname",    ""),
        "ip_address":               ("ip_address",  "::INET"),
        "environment":              ("environment", ""),
        "tags":                     ("tags",        ""),
        "responsible":              ("responsible", ""),
    }

    for cfg_key, (col, cast) in cfg_cast_map.items():
        if cfg_key in cfg:
            set_parts.append(f"{col} = %s{cast}")
            values.append(cfg[cfg_key])

    if not set_parts:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Aucun champ à modifier",
        )

    values.append(source_id)
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            f"UPDATE config.sources SET {', '.join(set_parts)}, updated_at = NOW() "
            f"WHERE id = %s RETURNING {_COLS}",
            values,
        )
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source introuvable")
    return row


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def disable_source(
    source_id: uuid.UUID,
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    _user=_WRITE,
):
    async with conn.cursor() as cur:
        await cur.execute(
            "UPDATE config.sources SET is_enabled = FALSE, updated_at = NOW() "
            "WHERE id = %s RETURNING id",
            (source_id,),
        )
        if await cur.fetchone() is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source introuvable")


# ── Identifiants de source (C4 config.source_credentials, C5) ─────────────────

@router.get("/{source_id}/credentials")
async def list_credentials(
    source_id: uuid.UUID,
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    _user=_WRITE,
):
    """Métadonnées des identifiants d'une source (jamais le secret)."""
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """SELECT id, credential_type, cert_fingerprint, created_at, expires_at, revoked_at
                 FROM config.source_credentials WHERE source_id = %s ORDER BY created_at DESC""",
            (source_id,),
        )
        return await cur.fetchall()


@router.post("/{source_id}/credentials/rotate", status_code=status.HTTP_201_CREATED)
async def rotate_credential(
    source_id: uuid.UUID,
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    _user=_WRITE,
):
    """Génère un nouveau jeton de source et révoque les jetons actifs précédents (C5).

    Le secret n'est renvoyé qu'une seule fois ; seul son empreinte SHA-256 est
    stockée (secret_hash), identique au schéma vérifié par la passerelle.
    """
    token = "bsk_" + secrets.token_urlsafe(32)
    secret_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("SELECT 1 FROM config.sources WHERE id = %s", (source_id,))
        if await cur.fetchone() is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source introuvable")
        # Révoquer les jetons actifs précédents.
        await cur.execute(
            """UPDATE config.source_credentials SET revoked_at = NOW()
                WHERE source_id = %s AND credential_type = 'token' AND revoked_at IS NULL""",
            (source_id,),
        )
        await cur.execute(
            """INSERT INTO config.source_credentials (source_id, credential_type, secret_hash)
               VALUES (%s, 'token', %s) RETURNING id, created_at""",
            (source_id, secret_hash),
        )
        row = await cur.fetchone()
    return {
        "credential_id": row["id"],
        "created_at": row["created_at"],
        "token": token,
        "note": "Jeton affiché une seule fois ; à communiquer à la source. Seule l'empreinte est stockée.",
    }
