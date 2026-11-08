"""Référentiel des sources pour l'enrichissement (C10) : nom, hôte et criticité (C4 : config.sources).

Le service ne fait que lire ce référentiel ; c'est l'API qui l'écrit (I-3). Toutes les sources
sont chargées, y compris les désactivées : un événement déjà accepté reste enrichi.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Protocol

log = logging.getLogger(__name__)
CRITICALITIES = {"faible", "moyenne", "elevee", "critique"}


@dataclass(frozen=True)
class SourceInfo:
    id: str
    name: str
    source_type: str
    host: str | None = None
    criticality: str | None = None     # faible, moyenne, elevee, critique ; None si non renseignée


class SourceRegistry(Protocol):
    async def load(self) -> list[SourceInfo]: ...


class SourcesCache:
    """Index en mémoire, rafraîchi périodiquement. Si le rafraîchissement échoue, l'index précédent
    reste utilisé jusqu'à `max_stale_s` ; au-delà, le service suspend la lecture de raw-events
    plutôt que de publier des événements mal enrichis."""

    def __init__(self, registry: SourceRegistry, refresh_s: float, max_stale_s: float):
        self._registry = registry
        self._refresh_s = refresh_s
        self._max_stale_s = max_stale_s
        self._by_id: dict[str, SourceInfo] = {}
        self._loaded_at: float | None = None
        self.last_error: str | None = None

    async def refresh(self) -> None:
        sources = await self._registry.load()
        self._by_id = {s.id: s for s in sources}
        self._loaded_at = time.monotonic()
        self.last_error = None

    async def run(self) -> None:
        while True:
            try:
                await self.refresh()
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"
                log.error("rafraîchissement des sources impossible : %s", self.last_error)
            await asyncio.sleep(self._refresh_s)

    @property
    def age_s(self) -> float | None:
        return None if self._loaded_at is None else time.monotonic() - self._loaded_at

    @property
    def usable(self) -> bool:
        age = self.age_s
        return age is not None and age <= self._max_stale_s

    def get(self, source_id: str) -> SourceInfo | None:
        return self._by_id.get(source_id)

    def __len__(self) -> int:
        return len(self._by_id)
