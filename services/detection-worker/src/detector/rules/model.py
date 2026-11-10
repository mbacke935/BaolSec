"""Règles de détection : lecture du YAML, contrôle par le contrat rule/v1, conditions compilées.

Une règle ne contient que des données : des champs, des valeurs et des opérateurs fixés
(equals, in, exists, contains, regex, gte, lte, not). Rien n'est exécuté comme du code (C3, fiche Détection).
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import jsonschema_rs
import yaml

from .. import fields
from ..timeutil import duration_s

# Espace de noms des identifiants PostgreSQL des règles : config.rules.id = UUID v5 (espace, code).
RULE_NAMESPACE = uuid.UUID("6f1c0d5e-2b7a-5c3e-9a41-baa15ec00001")
MAX_WINDOW_S = 24 * 3600


class RuleError(ValueError):
    """Règle refusée : non conforme au contrat ou expression régulière invalide."""


def rule_uuid(code: str) -> str:
    return str(uuid.uuid5(RULE_NAMESPACE, code))


def _norm(v: Any) -> Any:
    return v.casefold() if isinstance(v, str) else v


def _compile(path: str, cond: Any) -> Callable[[dict], bool]:
    """Condition sur un champ → fonction(événement) → bool. Un champ à plusieurs valeurs est vrai si l'une convient."""
    if isinstance(cond, list):
        wanted = {_norm(c) for c in cond}
        return lambda doc: any(_norm(v) in wanted for v in fields.values(doc, path))
    if not isinstance(cond, dict):
        target = _norm(cond)
        return lambda doc: any(_norm(v) == target for v in fields.values(doc, path))
    (op, arg), = cond.items()
    if op == "equals":
        return _compile(path, arg)
    if op == "in":
        return _compile(path, list(arg))
    if op == "not":
        inner = _compile(path, arg)
        return lambda doc: not inner(doc)
    if op == "exists":
        return lambda doc: bool(fields.values(doc, path)) == arg
    if op == "contains":
        needle = arg.casefold()
        return lambda doc: any(isinstance(v, str) and needle in v.casefold() for v in fields.values(doc, path))
    if op == "regex":
        try:
            rx = re.compile(arg)
        except re.error as exc:
            raise RuleError(f"expression régulière invalide pour {path} : {exc}") from exc
        return lambda doc: any(isinstance(v, str) and rx.search(v) for v in fields.values(doc, path))
    if op == "gte":
        return lambda doc: any(isinstance(v, (int, float)) and not isinstance(v, bool) and v >= arg for v in fields.values(doc, path))
    if op == "lte":
        return lambda doc: any(isinstance(v, (int, float)) and not isinstance(v, bool) and v <= arg for v in fields.values(doc, path))
    raise RuleError(f"opérateur inconnu : {op}")      # écarté par le contrat, gardé par sécurité


def compile_match(match: dict) -> Callable[[dict], bool]:
    tests = [_compile(path, cond) for path, cond in match.items()]
    return lambda doc: all(t(doc) for t in tests)


@dataclass(frozen=True)
class Rule:
    code: str                      # AUTH-001
    name: str
    version: int
    severity: str
    type: str                      # simple | window
    category: tuple[str, ...]
    group_by: tuple[str, ...]
    message: str
    definition: dict
    matches: Callable[[dict], bool] = field(repr=False, compare=False)
    trigger: Callable[[dict], bool] | None = field(default=None, repr=False, compare=False)
    window_s: int = 0
    threshold: int = 1
    distinct: str | None = None
    enabled: bool = True
    # Valeurs de event.category exigées par la condition : sert d'index (None = toutes les catégories)
    needs_category: frozenset[str] | None = None

    @property
    def uuid(self) -> str:
        return rule_uuid(self.code)

    @property
    def requirements(self) -> list[dict]:
        return list(self.definition.get("requires", []))


def _category_index(*matches: dict) -> frozenset[str] | None:
    cats: set[str] = set()
    for m in matches:
        cond = m.get("event.category")
        if cond is None:
            return None
        if isinstance(cond, str):
            cats.add(cond)
        elif isinstance(cond, list):
            cats.update(cond)
        elif isinstance(cond, dict) and set(cond) <= {"equals", "in"}:
            v = next(iter(cond.values()))
            cats.update(v if isinstance(v, list) else [v])
        else:
            return None
    return frozenset(cats)


class RuleValidator:
    def __init__(self, contracts_dir: Path):
        schema = json.loads((contracts_dir / "rule" / "v1" / "schema.json").read_text(encoding="utf-8"))
        self._validator = jsonschema_rs.validator_for(schema)

    def parse(self, text: str, version: int = 1) -> Rule:
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise RuleError(f"YAML illisible : {exc}") from exc
        if not isinstance(data, dict):
            raise RuleError("une règle est un objet YAML")
        errors = [f"{'/'.join(map(str, e.instance_path)) or '(racine)'} : {e.message}" for e in self._validator.iter_errors(data)]
        if errors:
            raise RuleError("; ".join(errors[:5]))
        window_s = duration_s(data["window"]) if "window" in data else 0
        if window_s > MAX_WINDOW_S:
            raise RuleError("fenêtre supérieure à 24 h")
        follow = data.get("followed_by")
        return Rule(
            code=data["id"], name=data["name"], version=version, severity=data["severity"], type=data["type"],
            category=tuple(data["category"]), group_by=tuple(data.get("group_by", ())), message=data["message"],
            definition=data, matches=compile_match(data["match"]),
            trigger=compile_match(follow["match"]) if follow else None,
            window_s=window_s, threshold=data.get("threshold", 1), distinct=data.get("distinct"),
            enabled=data.get("enabled", True),
            needs_category=_category_index(data["match"], *([follow["match"]] if follow else [])),
        )


def checksum(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
