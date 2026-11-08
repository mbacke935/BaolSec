"""Conversion d'un raw_event/v1 en normalized_event/v1 (ECS 9.5.0, table C5).

Étapes : contrôle du message reçu → parseur de la source → enveloppe commune → enrichissement (C10)
→ champs related.* → contrôle par le schéma du contrat. Un échec de ces étapes dépend
du contenu seul : il est définitif (file de rejet sans nouvelle tentative).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, tzinfo
from pathlib import Path

import jsonschema_rs

from baolsec_common.messaging import ProcessingError

from . import severity
from .enrich import Enricher
from .parsers import parse

ECS_VERSION = "9.5.0"
CONTRACT = "normalized_event/v1"


def load_validator(contracts_dir: Path, name: str):
    """Validateur JSON Schema 2020-12 compilé (jsonschema-rs), formats contrôlés (date-time, ipv4, ipv6, uuid).

    Choisi pour son coût : environ 4 µs par événement, contre 450 µs avec la bibliothèque jsonschema
    (mesure du 8 novembre 2026). Les tests contrôlent aussi chaque sortie avec jsonschema.
    """
    schema = json.loads((contracts_dir / name / "v1" / "schema.json").read_text(encoding="utf-8"))
    return jsonschema_rs.validator_for(schema, validate_formats=True)


def iso(dt: datetime) -> str:
    """Horodatage UTC ; millisecondes seulement si la source les fournit."""
    dt = dt.astimezone(timezone.utc)
    if dt.microsecond:
        return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _datetime(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _unique(values) -> list:
    out = []
    for v in values:
        if v and v not in out:
            out.append(v)
    return out


def _error(validator, doc: dict) -> str | None:
    if validator.is_valid(doc):
        return None
    errors = sorted(validator.iter_errors(doc), key=lambda e: [str(p) for p in e.instance_path])
    first = errors[0]
    where = "/".join(str(p) for p in first.instance_path) or "(racine)"
    more = f" (+{len(errors) - 1} autre(s))" if len(errors) > 1 else ""
    return f"{where} : {first.message}{more}"[:1500]


class Normalizer:
    def __init__(self, contracts_dir: Path, enricher: Enricher, syslog_tz: tzinfo):
        self._raw = load_validator(contracts_dir, "raw_event")
        self._normalized = load_validator(contracts_dir, "normalized_event")
        self._enricher = enricher
        self._tz = syslog_tz

    def decode(self, data: bytes) -> dict:
        try:
            raw = json.loads(data)
        except ValueError as exc:
            raise ProcessingError("validation_error", f"message raw-events illisible : {exc}", permanent=True) from exc
        if not isinstance(raw, dict):
            raise ProcessingError("validation_error", "message raw-events : objet JSON attendu", permanent=True)
        problem = _error(self._raw, raw)
        if problem:
            raise ProcessingError("validation_error", f"raw_event/v1 non conforme : {problem}", permanent=True)
        return raw

    def normalize(self, raw: dict) -> dict:
        received = _datetime(raw["received_at"])
        read_at = _datetime(raw.get("agent", {}).get("read_at"))
        parsed = parse(raw, received, read_at, self._tz)

        frag = parsed.doc
        event = {"id": raw["event_id"], "kind": "event", **frag.pop("event")}
        if read_at:
            event["created"] = raw["agent"]["read_at"]
        event["original"] = raw["payload"]
        extra_baolsec = frag.pop("baolsec", {})

        timestamp = parsed.timestamp
        doc = {
            "@timestamp": iso(timestamp or received),
            "ecs": {"version": ECS_VERSION},
            "event": event,
            **frag,
            "message": parsed.message[:8000] or raw["payload"][:200],
            "baolsec": {
                "contract": CONTRACT,
                "source": dict(raw["source"]),
                "received_at": raw["received_at"],
                "timestamp_source": "original" if timestamp else "received",
                "severity": severity.block(parsed.severity),
                **extra_baolsec,
            },
        }
        self._enricher.apply(doc)

        related = {
            "ip": _unique([doc.get("source", {}).get("ip"), doc.get("destination", {}).get("ip")]),
            "user": _unique([doc.get("user", {}).get("name"), *parsed.extra_users]),
            "hosts": _unique([doc.get("host", {}).get("name"), doc.get("observer", {}).get("name")]),
        }
        related = {k: v for k, v in related.items() if v}
        if related:
            doc["related"] = related
        return self._ordered(doc)

    @staticmethod
    def _ordered(doc: dict) -> dict:
        """Ordre des champs des exemples du contrat (lecture plus facile, sans effet sur le sens)."""
        order = ["@timestamp", "ecs", "event", "user", "host", "observer", "source", "destination", "network",
                 "rule", "process", "http", "url", "user_agent", "log", "related", "message", "baolsec"]
        return {k: doc[k] for k in sorted(doc, key=lambda k: order.index(k) if k in order else len(order))}

    def check(self, doc: dict) -> None:
        problem = _error(self._normalized, doc)
        if problem:
            raise ProcessingError("mapping_error", f"normalized_event/v1 non conforme : {problem}", permanent=True)

    def run(self, data: bytes) -> dict:
        doc = self.normalize(self.decode(data))
        self.check(doc)
        return doc
