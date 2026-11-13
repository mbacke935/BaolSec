"""Routes recherche OpenSearch (C20).

POST /search/events    → recherche full-text dans baolsec-events-*
POST /search/alerts    → recherche dans baolsec-alerts-*
POST /search/incidents → recherche dans baolsec-incidents-*
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from opensearchpy import AsyncOpenSearch
from pydantic import BaseModel, Field

from ..dependencies import get_current_user, require_role
from ..models import TokenPayload, UserRole

router = APIRouter(prefix="/search", tags=["search"])

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
    q: str = Field(..., description="Requête Lucene / query string")
    size: int = Field(20, ge=1, le=100)
    from_: int = Field(0, ge=0, alias="from")
    filters: dict[str, Any] = Field(default_factory=dict, description="Filtres supplémentaires (term queries)")

    model_config = {"populate_by_name": True}


def _build_query(sq: SearchQuery) -> dict:
    must: list = [{"query_string": {"query": sq.q, "default_operator": "AND"}}]
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
            index="baolsec-events-*",
            body={**_build_query(body), "size": body.size, "from": body.from_},
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"OpenSearch error: {exc}")
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
            index="baolsec-alerts-*",
            body={**_build_query(body), "size": body.size, "from": body.from_},
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"OpenSearch error: {exc}")
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
            index="baolsec-incidents-*",
            body={**_build_query(body), "size": body.size, "from": body.from_},
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"OpenSearch error: {exc}")
    hits = resp["hits"]
    return {
        "total": hits["total"]["value"],
        "hits": [h["_source"] | {"_id": h["_id"]} for h in hits["hits"]],
    }
