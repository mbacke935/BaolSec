"""Routes état de couverture (C20), schéma C4 couverture.*.

GET /coverage · GET /coverage/history · GET /coverage/{source_id}.
L'état courant vient de couverture.coverage_state ; les compteurs sont agrégés
depuis couverture.coverage_stats ; le nom de la source vient de config.sources.
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from ..dependencies import get_conn, paginate, require_role
from ..models import CoverageStateResponse, Page, UserRole

router = APIRouter(prefix="/coverage", tags=["coverage"])

_READ = Depends(require_role(UserRole.ANALYST, UserRole.ADMIN))

# Toutes les sources déclarées, y compris celles que le service Couverture n'a pas encore évaluées
# (état INCONNUE) ; règles affectées en cours (EF-09 : « les règles dépendant des données
# manquantes sont affichées »).
_SELECT = """
SELECT s.id AS source_id, s.name AS source_name,
       COALESCE(cs.state::text, CASE WHEN s.is_enabled THEN 'INCONNUE' ELSE 'DESACTIVEE' END) AS state,
       cs.last_received_at, cs.last_normalized_at AS last_processed_at,
       COALESCE(st.received, 0) AS received_count,
       COALESCE(st.normalized, 0) AS normalized_count,
       cs.last_evaluated_at AS evaluated_at, cs.state_since,
       s.source_type::text AS source_type, s.silence_threshold_s,
       COALESCE((SELECT jsonb_agg(jsonb_build_object('rule_id', ar.rule_id, 'name', r.name,
                                                     'cause', ar.cause, 'since', ar.since) ORDER BY r.name)
                   FROM couverture.coverage_affected_rules ar JOIN config.rules r ON r.id = ar.rule_id
                  WHERE ar.source_id = s.id AND ar.resolved_at IS NULL), '[]'::jsonb) AS affected_rules
  FROM config.sources s
  LEFT JOIN couverture.coverage_state cs ON cs.source_id = s.id
  LEFT JOIN (SELECT source_id, SUM(received_count) AS received, SUM(normalized_count) AS normalized
               FROM couverture.coverage_stats GROUP BY source_id) st ON st.source_id = s.id
"""


@router.get("", response_model=Page[CoverageStateResponse])
async def list_coverage(
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    _user=_READ,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    select_sql = _SELECT.strip() + " ORDER BY s.name"
    count_sql = "SELECT COUNT(*) AS count FROM config.sources s"
    return await paginate(conn, select_sql, count_sql, [], limit, offset)


@router.get("/history")
async def coverage_history(
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    _user=_READ,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    source_id: uuid.UUID | None = None,
):
    conds, args = [], []
    if source_id:
        conds.append("source_id = %s"); args.append(source_id)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    q = (f"SELECT h.*, s.name AS source_name FROM couverture.coverage_state_history h "
         f"JOIN config.sources s ON s.id = h.source_id {where.replace('source_id', 'h.source_id')} "
         f"ORDER BY h.changed_at DESC LIMIT %s OFFSET %s")
    args.extend([limit, offset])
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(q, args)
        return await cur.fetchall()


@router.get("/{source_id}", response_model=CoverageStateResponse)
async def get_coverage(
    source_id: uuid.UUID,
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    _user=_READ,
):
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(_SELECT + " WHERE s.id = %s", (source_id,))
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source introuvable")
    return row
