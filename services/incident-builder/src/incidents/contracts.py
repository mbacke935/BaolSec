"""Validation des messages par les contrats de shared/contracts (C5) : alert/v1 et incident_command/v1."""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema_rs


def _validator(contracts_dir: Path, *parts: str):
    schema = json.loads(contracts_dir.joinpath(*parts).read_text(encoding="utf-8"))
    return jsonschema_rs.validator_for(schema, validate_formats=True)


def _first_errors(validator, doc, limit: int = 3) -> str | None:
    errors = [f"{'/'.join(map(str, e.instance_path)) or '(racine)'} : {e.message}" for e in validator.iter_errors(doc)]
    return "; ".join(errors[:limit]) if errors else None


class Contracts:
    """Charge les schémas une fois ; `*_errors` renvoie None si le document est conforme, sinon les premiers écarts."""

    def __init__(self, contracts_dir: Path):
        self._alert = _validator(contracts_dir, "alert", "v1", "schema.json")
        self._command = _validator(contracts_dir, "incident_command", "v1", "schema.json")

    def alert_errors(self, doc) -> str | None:
        return _first_errors(self._alert, doc)

    def command_errors(self, doc) -> str | None:
        return _first_errors(self._command, doc)
