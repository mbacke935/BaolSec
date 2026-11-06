"""Limitation de débit par source (seau à jetons, en nombre d'événements).

Chaque instance de la passerelle a ses propres compteurs : avec N instances, une source
peut atteindre N fois la limite. Cette limite protège la passerelle et le broker d'une
source qui s'emballe ; elle n'est pas un quota contractuel.
"""
from __future__ import annotations

import asyncio
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
        """Accepte n événements s'il reste des jetons, quitte à passer en négatif (dette) ;
        sinon ne prend rien et renvoie l'attente conseillée (s).

        La dette permet d'accepter un lot plus grand que la rafale (un chunk Fluent Bit peut
        contenir des milliers de lignes courtes) sans jamais le refuser définitivement : la
        source attend ensuite que la dette soit remboursée. Le débit moyen reste borné par `rate`.
        """
        b = self._bucket(key)
        if b.tokens > 0:
            b.tokens -= n
            return 0.0
        return max(-b.tokens / self.rate, 1 / self.rate)

    async def acquire(self, key: str, n: int = 1) -> None:
        """Attend que n jetons soient disponibles (Syslog : on ralentit la lecture au lieu de rejeter)."""
        while (wait := self.try_acquire(key, n)) > 0:
            await asyncio.sleep(min(wait, 1.0))
