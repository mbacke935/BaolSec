"""Validation des événements reçus et construction des enveloppes raw_event/v1.

Format reçu en HTTPS : tableau JSON d'enregistrements, tel que l'envoie la sortie `http`
de Fluent Bit (format json). Pour chaque enregistrement :
- `date` : heure de lecture par l'agent (ISO 8601 ou secondes epoch) → agent.read_at ;
- `log` (texte) : ligne brute lue dans un fichier → payload_format « text » ;
- sinon, l'enregistrement entier (journald, journal Windows…) → payload_format « json ».
La passerelle ne parse pas le contenu : c'est le rôle de la normalisation.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from ..event_id import event_id
from ..sources_cache import Source

AGENT_DATE_KEY = "date"


@dataclass(frozen=True)
class Rejection:
    index: int
    reason: str


def utc_now() -> str:
    return iso(datetime.now(timezone.utc))


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _read_at(value) -> str | None:
    """Heure de lecture fournie par l'agent ; omise si absente ou illisible (aucune valeur inventée)."""
    try:
        if isinstance(value, bool):
            return None
        if isinstance(value, int | float):
            return iso(datetime.fromtimestamp(value, timezone.utc))
        if isinstance(value, str):
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return iso(dt) if dt.tzinfo else None
    except (ValueError, OverflowError, OSError):
        return None
    return None


def build_raw_event(
    source: Source, transport: str, received_at: str, payload_format: str, payload: str,
    agent_name: str | None = None, read_at: str | None = None, record: dict | None = None,
) -> dict:
    event = {
        "contract": "raw_event/v1",
        "event_id": event_id(source.id, source.source_type, payload_format, payload, record),
        "source": {"id": source.id, "type": source.source_type, "ingestion_mode": source.ingestion_mode},
        "transport": transport,
        "received_at": received_at,
        "payload_format": payload_format,
        "payload": payload,
    }
    agent = {k: v for k, v in (("name", agent_name), ("read_at", read_at)) if v}
    if agent:
        event["agent"] = agent
    return event


def http_records(
    records: list, source: Source, received_at: str, max_chars: int, agent_name: str | None,
) -> tuple[list[dict], list[Rejection]]:
    events: list[dict] = []
    rejected: list[Rejection] = []
    for i, rec in enumerate(records):
        if not isinstance(rec, dict):
            rejected.append(Rejection(i, "l'événement doit être un objet JSON"))
            continue
        body = {k: v for k, v in rec.items() if k != AGENT_DATE_KEY}
        if "log" in body:
            log_line = body["log"]
            if not isinstance(log_line, str) or not log_line.strip():
                rejected.append(Rejection(i, "champ log vide ou non textuel"))
                continue
            payload_format, payload = "text", log_line.rstrip("\r\n")
            native = None
        else:
            if not body:
                rejected.append(Rejection(i, "événement vide"))
                continue
            payload_format = "json"
            payload = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            native = body
        if len(payload) > max_chars:
            rejected.append(Rejection(i, f"événement trop long ({len(payload)} > {max_chars} caractères)"))
            continue
        events.append(build_raw_event(
            source, "https", received_at, payload_format, payload,
            agent_name=agent_name, read_at=_read_at(rec.get(AGENT_DATE_KEY)), record=native,
        ))
    return events, rejected


def agent_name_from(user_agent: str | None) -> str | None:
    """« Fluent-Bit/4.1.0 » → « fluent-bit »."""
    if not user_agent:
        return None
    product = user_agent.split("/", 1)[0].split(" ", 1)[0].strip().lower()
    return product[:64] or None
