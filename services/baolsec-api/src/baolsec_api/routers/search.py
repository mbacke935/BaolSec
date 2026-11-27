"""Routes recherche OpenSearch (C20, C5, EF-11).

GET  /events              → recherche d'événements : période, source, utilisateur, IP, hôte, texte libre
GET  /events/{event_id}   → un événement normalisé avec son contenu brut (event.original)
POST /search/events       → requête Lucene libre dans baolsec-events-*
POST /search/alerts       → recherche dans baolsec-alerts-*
POST /search/incidents    → recherche dans baolsec-incidents-*

OpenSearch injoignable → 503 « moteur de recherche indisponible » (message explicite, ENF-04) ;
requête refusée par OpenSearch (syntaxe Lucene invalide…) → 400.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from opensearchpy import AsyncOpenSearch
from pydantic import BaseModel, Field

from ..dependencies import get_current_user, require_role
from ..models import TokenPayload, UserRole

router = APIRouter(prefix="/search", tags=["search"])
events_router = APIRouter(prefix="/events", tags=["events"])

_READ = Depends(require_role(UserRole.ANALYST, UserRole.ADMIN))

# Client OpenSearch partagé (initialisé dans main.py)
_os_client: AsyncOpenSearch | None = None


def set_opensearch_client(client: AsyncOpenSearch) -> None:
    global _os_client
    _os_client = client


def _client() -> AsyncOpenSearch:
    if _os_client is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="OpenSearch non disponible")
    return _os_client


class SearchQuery(BaseModel):
    q: str = Field("*", max_length=2000, description="Requête Lucene / query string")
    size: int = Field(20, ge=1, le=100)
    from_: int = Field(0, ge=0, alias="from")
    filters: dict[str, Any] = Field(default_factory=dict, description="Filtres supplémentaires (term queries)")

    model_config = {"populate_by_name": True}


def _os_error(exc: Exception) -> HTTPException:
    from opensearchpy import exceptions as osx
    if isinstance(exc, (osx.ConnectionError, osx.ConnectionTimeout)):
        return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                             detail="Moteur de recherche (OpenSearch) indisponible : réessayez dans un instant.")
    if isinstance(exc, osx.NotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aucun index de recherche disponible.")
    if isinstance(exc, osx.RequestError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                             detail=f"Requête de recherche invalide : {getattr(exc, 'error', exc)}")
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Erreur OpenSearch : {type(exc).__name__}")


def _build_query(sq: SearchQuery) -> dict:
    must: list = [{"query_string": {"query": sq.q or "*", "default_operator": "AND"}}]
    for field, value in sq.filters.items():
        must.append({"term": {field: value}})
    return {"query": {"bool": {"must": must}}}


@router.post("/events")
async def search_events(
    body: SearchQuery,
    _user=_READ,
):
    client = _client()
    try:
        resp = await client.search(
            index="baolsec-events-*", ignore_unavailable=True,
            body={**_build_query(body), "size": body.size, "from": body.from_,
                  "sort": [{"@timestamp": {"order": "desc", "unmapped_type": "date"}}], "track_total_hits": True},
        )
    except Exception as exc:
        raise _os_error(exc) from exc
    hits = resp["hits"]
    return {
        "total": hits["total"]["value"],
        "hits": [h["_source"] | {"_id": h["_id"]} for h in hits["hits"]],
    }


@router.post("/alerts")
async def search_alerts(
    body: SearchQuery,
    _user=_READ,
):
    client = _client()
    try:
        resp = await client.search(
            index="baolsec-alerts-*", ignore_unavailable=True,
            body={**_build_query(body), "size": body.size, "from": body.from_,
                  "sort": [{"@timestamp": {"order": "desc", "unmapped_type": "date"}}], "track_total_hits": True},
        )
    except Exception as exc:
        raise _os_error(exc) from exc
    hits = resp["hits"]
    return {
        "total": hits["total"]["value"],
        "hits": [h["_source"] | {"_id": h["_id"]} for h in hits["hits"]],
    }


@router.post("/incidents")
async def search_incidents(
    body: SearchQuery,
    _user=_READ,
):
    client = _client()
    try:
        resp = await client.search(
            index="baolsec-incidents-*", ignore_unavailable=True,
            body={**_build_query(body), "size": body.size, "from": body.from_,
                  "sort": [{"@timestamp": {"order": "desc", "unmapped_type": "date"}}], "track_total_hits": True},
        )
    except Exception as exc:
        raise _os_error(exc) from exc
    hits = resp["hits"]
    return {
        "total": hits["total"]["value"],
        "hits": [h["_source"] | {"_id": h["_id"]} for h in hits["hits"]],
    }


# ── GET /events (C5, EF-11) ───────────────────────────────────────────────────

def _events_query(q: str | None, start: datetime | None, end: datetime | None, source_id: str | None,
                  user: str | None, ip: str | None, host: str | None, category: str | None,
                  outcome: str | None) -> dict:
    filt: list[dict] = []
    must: list[dict] = []
    if q and q.strip():
        must.append({"simple_query_string": {"query": q.strip(), "default_operator": "and",
                                              "fields": ["message^2", "event.original", "user.name",
                                                         "host.name", "event.action", "*"],
                                              "lenient": True}})
    if start or end:
        rng = {}
        if start:
            rng["gte"] = start.isoformat()
        if end:
            rng["lte"] = end.isoformat()
        filt.append({"range": {"@timestamp": rng}})
    if source_id:
        filt.append({"term": {"baolsec.source.id": source_id}})
    if user:
        filt.append({"bool": {"should": [{"term": {"user.name": user}}, {"term": {"related.user": user}}],
                              "minimum_should_match": 1}})
    if ip:
        filt.append({"bool": {"should": [{"term": {"source.ip": ip}}, {"term": {"destination.ip": ip}},
                                         {"term": {"related.ip": ip}}], "minimum_should_match": 1}})
    if host:
        filt.append({"term": {"host.name": host}})
    if category:
        filt.append({"term": {"event.category": category}})
    if outcome:
        filt.append({"term": {"event.outcome": outcome}})
    return {"bool": {"must": must or [{"match_all": {}}], "filter": filt}}


@events_router.get("")
async def list_events(
    _user=_READ,
    q: str | None = Query(None, max_length=500, description="Texte libre"),
    start: datetime | None = Query(None, alias="from"),
    end: datetime | None = Query(None, alias="to"),
    source_id: str | None = None,
    user: str | None = None,
    ip: str | None = None,
    host: str | None = None,
    category: str | None = None,
    outcome: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=10_000),
):
    client = _client()
    body = {"query": _events_query(q, start, end, source_id, user, ip, host, category, outcome),
            "sort": [{"@timestamp": {"order": "desc", "unmapped_type": "date"}}],
            "size": limit, "from": offset, "track_total_hits": True}
    try:
        resp = await client.search(index="baolsec-events-*", body=body, ignore_unavailable=True)
    except Exception as exc:
        raise _os_error(exc) from exc
    hits = resp["hits"]
    return {"total": hits["total"]["value"], "limit": limit, "offset": offset,
            "items": [h["_source"] | {"_id": h["_id"], "_index": h["_index"]} for h in hits["hits"]]}


@events_router.get("/{event_id}")
async def get_event(event_id: str, _user=_READ):
    client = _client()
    try:
        resp = await client.search(index="baolsec-events-*", ignore_unavailable=True, body={
            "query": {"bool": {"should": [{"ids": {"values": [event_id]}}, {"term": {"event.id": event_id}}],
                               "minimum_should_match": 1}}, "size": 1})
    except Exception as exc:
        raise _os_error(exc) from exc
    hits = resp["hits"]["hits"]
    if not hits:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Événement introuvable")
    return hits[0]["_source"] | {"_id": hits[0]["_id"], "_index": hits[0]["_index"]}


async def alert_evidence(alert_id: str) -> dict[str, Any]:
    """Document d'alerte immuable et événements justificatifs (C5 GET /alerts/{id}).

    Best-effort : si OpenSearch ne répond pas, l'état de triage (PostgreSQL) reste consultable
    et `available` vaut False.
    """
    if _os_client is None:
        return {"available": False}
    try:
        resp = await _os_client.search(index="baolsec-alerts-*", ignore_unavailable=True, body={
            "query": {"bool": {"should": [{"ids": {"values": [alert_id]}}, {"term": {"event.id": alert_id}}],
                               "minimum_should_match": 1}}, "size": 1})
        hits = resp["hits"]["hits"]
        if not hits:
            return {"available": True, "found": False}
        doc = hits[0]["_source"]
        event_ids = ((doc.get("baolsec") or {}).get("alert") or {}).get("event_ids") or []
        events: list = []
        if event_ids:
            ev = await _os_client.search(index="baolsec-events-*", ignore_unavailable=True, body={
                "query": {"bool": {"should": [{"ids": {"values": event_ids[:100]}},
                                              {"terms": {"event.id": event_ids[:100]}}],
                                   "minimum_should_match": 1}},
                "sort": [{"@timestamp": {"order": "asc", "unmapped_type": "date"}}], "size": 100})
            events = [h["_source"] | {"_id": h["_id"]} for h in ev["hits"]["hits"]]
        return {"available": True, "found": True, "alert": doc, "events": events}
    except Exception:  # noqa: BLE001
        return {"available": False}
