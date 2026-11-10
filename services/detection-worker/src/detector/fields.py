"""Lecture des champs d'un événement normalisé par chemin pointé (user.name, event.category…)."""
from __future__ import annotations

from typing import Any

_MISSING = object()


def get(doc: dict, path: str) -> Any:
    """Valeur du champ, ou None s'il est absent. @timestamp est un nom de champ, pas un chemin."""
    if path in doc:
        return doc[path]
    cur: Any = doc
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part, _MISSING)
        if cur is _MISSING:
            return None
    return cur


def values(doc: dict, path: str) -> list:
    """Valeurs du champ sous forme de liste (un champ ECS peut contenir une liste)."""
    v = get(doc, path)
    if v is None:
        return []
    return list(v) if isinstance(v, list) else [v]
