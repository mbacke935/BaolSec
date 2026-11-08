"""Journal Sécurité Windows, tel que l'envoie l'entrée winevtlog de Fluent Bit (C7).

L'agent est configuré avec event_data_as_map : les données de l'événement arrivent nommées
dans EventData. Si Windows ne fournit pas la description de l'événement, Fluent Bit envoie
à la place la liste StringInserts : les champs utiles sont alors lus par leur position.
TimeCreated : « 2026-11-02 10:40:52 +0000 » (Fluent Bit) ou ISO 8601.
"""
from __future__ import annotations

import json
import ntpath
from datetime import datetime

from .. import severity
from .base import Parsed, action_name, clean, ip_or_none, parse_iso, port_or_none, put, unparsable

# Position des champs dans StringInserts (schéma d'événement documenté par Microsoft)
POSITIONS = {
    4624: {"TargetUserName": 5, "LogonType": 8, "IpAddress": 18, "IpPort": 19},
    4625: {"TargetUserName": 5, "LogonType": 10, "IpAddress": 19, "IpPort": 20},
    4634: {"TargetUserName": 1, "LogonType": 4},
    4688: {"SubjectUserName": 1, "NewProcessId": 4, "NewProcessName": 5, "CommandLine": 8},
}
TABLE = {   # C5, section 3
    4624: (["authentication"], ["start"], "logon", "success"),
    4625: (["authentication"], ["start"], "logon", "failure"),
    4634: (["authentication"], ["end"], "logoff", "success"),
    4688: (["process"], ["start"], "process_start", "success"),
}


def _time(value) -> datetime | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    dt = parse_iso(text)
    if dt:
        return dt
    try:
        return datetime.strptime(text, "%Y-%m-%d %H:%M:%S %z")
    except ValueError:
        return None


def _data(record: dict, event_id: int) -> dict:
    data = record.get("EventData")
    if isinstance(data, dict):
        return data
    inserts = record.get("StringInserts")
    if isinstance(inserts, list):
        return {name: inserts[i] for name, i in POSITIONS.get(event_id, {}).items() if i < len(inserts)}
    return {}


def _pid(value) -> int | None:
    text = clean(value)
    if not text:
        return None
    try:
        return int(text, 16) if text.lower().startswith("0x") else int(text)
    except ValueError:
        return None


def parse(raw: dict, received: datetime) -> Parsed:
    if raw["payload_format"] != "json":
        raise unparsable("un événement Windows doit être un enregistrement JSON")
    try:
        record = json.loads(raw["payload"])
    except ValueError as exc:
        raise unparsable(f"JSON illisible : {exc}") from exc
    if not isinstance(record, dict):
        raise unparsable("enregistrement Windows : objet JSON attendu")
    try:
        event_id = int(record["EventID"])
    except (KeyError, TypeError, ValueError) as exc:
        raise unparsable("enregistrement Windows sans EventID") from exc

    data = _data(record, event_id)
    computer = clean(record.get("Computer"))
    provider = clean(record.get("ProviderName"))
    doc: dict = {"event": {"code": str(event_id), "dataset": "windows.security"}}
    put(doc, "event.provider", provider)
    put(doc, "host.name", computer)

    if event_id in TABLE:
        category, types, action, outcome = TABLE[event_id]
    else:   # hors de la table C5 : conservé sans interprétation
        category, types, action, outcome = ["host"], ["info"], action_name(f"windows_{event_id}"), "unknown"
    doc["event"].update({"category": category, "type": types, "action": action, "outcome": outcome})

    user = ip = None
    if event_id in (4624, 4625, 4634):
        user = clean(data.get("TargetUserName"))
        ip = ip_or_none(data.get("IpAddress"))
        put(doc, "user.name", user)
        put(doc, "source.ip", ip)
        put(doc, "source.port", port_or_none(data.get("IpPort")))
        put(doc, "baolsec.windows.logon_type", clean(data.get("LogonType")))
    elif event_id == 4688:
        user = clean(data.get("SubjectUserName"))
        exe = clean(data.get("NewProcessName"))
        put(doc, "user.name", user)
        put(doc, "process.pid", _pid(data.get("NewProcessId")))
        put(doc, "process.executable", exe)
        put(doc, "process.name", ntpath.basename(exe) if exe else None)
        put(doc, "process.command_line", clean(data.get("CommandLine")))

    origin = f" depuis {ip}" if ip else ""
    who = user or "?"
    if event_id == 4624:
        message = f"Ouverture de session réussie pour {who}{origin}"
    elif event_id == 4625:
        message = f"Échec d'ouverture de session pour {who}{origin}"
    elif event_id == 4634:
        message = f"Fermeture de session pour {who}"
    elif event_id == 4688:
        message = f"Processus créé par {who} : {doc.get('process', {}).get('executable', '?')}"
    else:
        text = clean(record.get("Message"))
        message = text.splitlines()[0] if text else f"Événement Windows {event_id}"

    return Parsed(doc, _time(record.get("TimeCreated")), severity.from_windows(event_id), message)
