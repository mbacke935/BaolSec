"""Limitation de débit par source (seau à jetons, en nombre d'événements).

Chaque instance de la passerelle a ses propres compteurs : avec N instances, une source
peut atteindre N fois la limite. Cette limite protège la passerelle et le broker d'une
source qui s'emballe ; elle n'est pas un quota contractuel.
"""
from __future__ import annotations

import asyncio
import math
import time
from dataclasses import dataclass


@dataclass
class _Bucket:
    tokens: float
    updated: float


class RateLimiter:
    def __init__(self, rate_per_s: float, burst: int, clock=time.monotonic):
        self.rate = rate_per_s
        self.burst = burst
        self._clock = clock
        self._buckets: dict[str, _Bucket] = {}

    def _bucket(self, key: str) -> _Bucket:
        now = self._clock()
        b = self._buckets.get(key)
        if b is None:
            b = self._buckets[key] = _Bucket(float(self.burst), now)
        else:
            b.tokens = min(self.burst, b.tokens + (now - b.updated) * self.rate)
            b.updated = now
        return b

    def try_acquire(self, key: str, n: int) -> float:
        """Prend n jetons et renvoie 0, ou ne prend rien et renvoie l'attente conseillée (s)."""
        b = self._bucket(key)
        if n <= b.tokens:
            b.tokens -= n
            return 0.0
        if n > self.burst:
            return math.inf
        return (n - b.tokens) / self.rate

    async def acquire(self, key: str, n: int = 1) -> None:
        """Attend que n jetons soient disponibles (Syslog : on ralentit la lecture au lieu de rejeter)."""
        while (wait := self.try_acquire(key, n)) > 0:
            await asyncio.sleep(min(wait, 1.0))
