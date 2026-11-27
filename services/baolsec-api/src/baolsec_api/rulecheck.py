"""Validation d'une définition de règle avant enregistrement (EF-05, contrat rule/v1).

L'API refuse ce que detection-worker refuserait (detector/rules/model.py) : contrat rule/v1,
expressions régulières compilables, fenêtre de 24 h au plus. Une règle enregistrée est donc
toujours chargeable par le moteur ; sans ce contrôle, une règle invalide serait acceptée par
l'interface puis écartée en silence par le moteur.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

# Même espace que detection-worker et load_rules.py : config.rules.id = UUID v5 (espace, code)
RULE_NAMESPACE = uuid.UUID("6f1c0d5e-2b7a-5c3e-9a41-baa15ec00001")
MAX_WINDOW_S = 24 * 3600
_UNITS = {"s": 1, "m": 60, "h": 3600}


class RuleDefinitionError(ValueError):
    pass


@lru_cache(maxsize=4)
def _validator(contracts_dir: str) -> Draft202012Validator:
    schema = json.loads((Path(contracts_dir) / "rule" / "v1" / "schema.json").read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def rule_uuid(code: str) -> uuid.UUID:
    return uuid.uuid5(RULE_NAMESPACE, code)


def checksum(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _duration_s(text: str) -> int:
    return int(text[:-1]) * _UNITS[text[-1]]


def _check_regexes(match: dict, where: str) -> None:
    for path, cond in match.items():
        if isinstance(cond, dict) and "regex" in cond:
            try:
                re.compile(cond["regex"])
            except re.error as exc:
                raise RuleDefinitionError(f"{where}.{path} : expression régulière invalide ({exc})") from exc


def parse(text: str, contracts_dir: Path) -> dict[str, Any]:
    """Définition YAML → dictionnaire validé. Lève RuleDefinitionError avec un message explicite."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise RuleDefinitionError(f"YAML illisible : {exc}") from exc
    if not isinstance(data, dict):
        raise RuleDefinitionError("La définition doit être un objet YAML (clé: valeur).")
    errors = sorted(_validator(str(contracts_dir)).iter_errors(data), key=lambda e: list(e.path))
    if errors:
        msgs = [f"{'/'.join(map(str, e.path)) or '(racine)'} : {e.message}" for e in errors[:5]]
        raise RuleDefinitionError("Non conforme au contrat rule/v1 — " + " ; ".join(msgs))
    if "window" in data and _duration_s(data["window"]) > MAX_WINDOW_S:
        raise RuleDefinitionError("Fenêtre supérieure à 24 h.")
    if data.get("type") == "window" and "window" not in data:
        raise RuleDefinitionError("Une règle de type « window » doit préciser sa fenêtre (window).")
    _check_regexes(data["match"], "match")
    if isinstance(data.get("followed_by"), dict):
        _check_regexes(data["followed_by"].get("match", {}), "followed_by.match")
    return data


def logic_summary(data: dict[str, Any]) -> dict[str, Any]:
    """Résumé lisible de la logique pour l'interface (la définition complète reste le YAML)."""
    keys = ("match", "group_by", "window", "threshold", "distinct", "followed_by", "requires")
    return {k: data[k] for k in keys if k in data}
