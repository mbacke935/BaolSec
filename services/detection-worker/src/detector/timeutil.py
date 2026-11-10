"""Dates ISO 8601 et durées des règles (10m, 30s, 1h)."""
from __future__ import annotations

from datetime import datetime, timezone

_UNITS = {"s": 1, "m": 60, "h": 3600}


def duration_s(text: str) -> int:
    return int(text[:-1]) * _UNITS[text[-1]]


def parse_ms(value: str) -> int:
    """Horodatage ISO 8601 → millisecondes depuis l'époque Unix (UTC)."""
    t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return int(t.timestamp() * 1000)


def iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def human(seconds: int) -> str:
    if seconds % 3600 == 0:
        return f"{seconds // 3600} h"
    if seconds % 60 == 0:
        return f"{seconds // 60} min"
    return f"{seconds} s"
