"""Cache des sources actives et de leurs identifiants (C4 : config.sources, config.source_credentials).

La passerelle ne fait que lire ce référentiel ; c'est l'API qui l'écrit (I-3).
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Protocol

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Source:
    id: str
    name: str
    source_type: str          # linux, windows, firewall, http
    transport: str            # https, syslog
    ingestion_mode: str       # direct, rejeu


@dataclass(frozen=True)
class Credential:
    source: Source
    credential_type: str      # token, client_cert
    secret_hash: str | None
    cert_fingerprint: str | None


class SourceRegistry(Protocol):
    async def load(self) -> list[Credential]:
        """Identifiants valides (non révoqués, non expirés) des sources activées."""


def normalize_fingerprint(value: str) -> str:
    """« AA:BB:… » (sortie d'openssl) ou « aabb… » → « aabb… »."""
    return value.replace(":", "").strip().lower()


class SourcesCache:
    """Index en mémoire, rafraîchi périodiquement. En cas d'échec du rafraîchissement,
    l'index précédent reste utilisé jusqu'à `max_stale_s`, puis plus aucune source n'est acceptée."""

    def __init__(self, registry: SourceRegistry, refresh_s: float, max_stale_s: float):
        self._registry = registry
        self._refresh_s = refresh_s
        self._max_stale_s = max_stale_s
        self._by_token_hash: dict[str, Source] = {}
        self._by_fingerprint: dict[str, Source] = {}
        self._loaded_at: float | None = None
        self.last_error: str | None = None

    async def refresh(self) -> None:
        creds = await self._registry.load()
        by_token, by_fp = {}, {}
        for c in creds:
            if c.credential_type == "token" and c.secret_hash and c.source.transport == "https":
                by_token[c.secret_hash.lower()] = c.source
            elif c.credential_type == "client_cert" and c.cert_fingerprint and c.source.transport == "syslog":
                by_fp[normalize_fingerprint(c.cert_fingerprint)] = c.source
        self._by_token_hash, self._by_fingerprint = by_token, by_fp
        self._loaded_at = time.monotonic()
        self.last_error = None

    async def run(self) -> None:
        while True:
            try:
                await self.refresh()
            except Exception as exc:   # référentiel injoignable : on garde l'index précédent
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

    def by_token_hash(self, token_hash: str) -> Source | None:
        return self._by_token_hash.get(token_hash) if self.usable else None

    def by_fingerprint(self, fingerprint: str) -> Source | None:
        return self._by_fingerprint.get(normalize_fingerprint(fingerprint)) if self.usable else None
