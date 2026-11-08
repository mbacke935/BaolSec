"""Choix du parseur selon le type de la source authentifiée par la passerelle (raw_event.source.type)."""
from __future__ import annotations

from datetime import datetime, tzinfo

from . import linux, pfsense, web, windows
from .base import Parsed, unparsable


def parse(raw: dict, received: datetime, read_at: datetime | None, tz: tzinfo) -> Parsed:
    kind = raw["source"]["type"]
    if kind == "linux":
        return linux.parse(raw, received, read_at, tz)
    if kind == "windows":
        return windows.parse(raw, received)
    if kind == "firewall":
        return pfsense.parse(raw, received, tz)
    if kind == "http":
        return web.parse(raw)
    raise unparsable(f"type de source sans parseur : {kind}")


__all__ = ["Parsed", "parse"]
