"""Référentiel des sources lu dans un fichier JSON (tests et développement avant PostgreSQL).

Même fichier que la passerelle (scripts/development/init_dev_gateway.sh), mêmes colonnes que config.sources.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import CRITICALITIES, SourceInfo


class FileSourceRegistry:
    def __init__(self, path: Path):
        self._path = path

    async def load(self) -> list[SourceInfo]:
        data = json.loads(self._path.read_text(encoding="utf-8"))
        out = []
        for s in data["sources"]:
            crit = s.get("criticality")
            out.append(SourceInfo(id=s["id"], name=s["name"], source_type=s["source_type"],
                                  host=s.get("host") or None,
                                  criticality=crit if crit in CRITICALITIES else None))
        return out
