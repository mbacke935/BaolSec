"""Application web : journal d'accès (format « combined » ou « common ») et journal applicatif JSON.

Journal applicatif JSON attendu (une ligne par événement, clés reconnues) :
  horodatage : ts, timestamp, @timestamp ou time        niveau : level ou severity
  événement  : event ou action (login_succeeded, login_failed…)
  adresse    : client_ip, ip, remote_addr ou source_ip   compte : user, username ou user_name
  motif      : reason       texte : message ou msg       application : app, service ou application
"""
from __future__ import annotations

import json
import re
from datetime import datetime

from .. import severity
from .base import Parsed, action_name, clean, ip_or_none, parse_iso, put, unparsable

_ACCESS = re.compile(
    r'^(?P<ip>\S+) \S+ (?P<user>\S+) \[(?P<time>[^\]]+)\] "(?P<request>[^"]*)" (?P<status>\d{3}) (?P<size>\S+)'
    r'(?: "(?P<referer>[^"]*)" "(?P<agent>[^"]*)")?')
LOGIN_OK = {"login_succeeded", "login_success", "login_ok", "login"}
LOGIN_KO = {"login_failed", "login_failure", "login_refused", "login_denied"}


def _first(record: dict, *keys):
    for k in keys:
        if k in record and record[k] not in (None, ""):
            return record[k]
    return None


def parse_access(line: str) -> Parsed:
    m = _ACCESS.match(line.strip())
    if not m:
        raise unparsable("ligne de journal d'accès web illisible")
    try:
        timestamp = datetime.strptime(m["time"], "%d/%b/%Y:%H:%M:%S %z")
    except ValueError:
        timestamp = None
    status = int(m["status"])
    method, _, rest = m["request"].partition(" ")
    path = rest.rsplit(" ", 1)[0] if " HTTP/" in rest else rest
    method = method if method.isalpha() and method.isupper() else None
    ip = ip_or_none(m["ip"])
    failed = status >= 400

    doc: dict = {"event": {"category": ["web"], "type": ["access", "error"] if failed else ["access"],
                           "action": "http_request", "outcome": "failure" if failed else "success",
                           "dataset": "web.access"}}
    put(doc, "source.ip", ip)
    put(doc, "user.name", clean(m["user"]))
    put(doc, "http.request.method", method)
    put(doc, "http.response.status_code", status if 100 <= status <= 599 else None)
    put(doc, "url.original", clean(path))
    put(doc, "user_agent.original", clean(m["agent"]))

    short = (clean(path) or "?").split("?", 1)[0]
    result = "refusé" if 400 <= status < 500 else "en erreur" if status >= 500 else "servi"
    message = f"{method or 'Requête'} {short} {result} ({status}) pour {ip or m['ip']}"
    return Parsed(doc, timestamp, severity.from_http_status(status), message)


def parse_app(record: dict) -> Parsed:
    raw_time = _first(record, "ts", "timestamp", "@timestamp", "time")
    timestamp = parse_iso(raw_time) if isinstance(raw_time, str) else None
    level = clean(_first(record, "level", "severity"))
    name = clean(_first(record, "event", "action"))
    ip = ip_or_none(_first(record, "client_ip", "ip", "remote_addr", "source_ip"))
    user = clean(_first(record, "user", "username", "user_name"))
    reason = clean(record.get("reason"))
    text = clean(_first(record, "message", "msg"))

    doc: dict = {"event": {"dataset": "app.log"}}
    put(doc, "event.provider", clean(_first(record, "app", "service", "application")))
    put(doc, "source.ip", ip)
    put(doc, "user.name", user)
    put(doc, "log.level", level.lower() if level else None)

    key = (name or "").lower()
    if key in LOGIN_OK or key in LOGIN_KO:
        outcome = "failure" if key in LOGIN_KO else "success"
        doc["event"].update({"category": ["authentication"], "type": ["start"], "action": "api_login",
                             "outcome": outcome})
        origin = f" depuis {ip}" if ip else ""
        if outcome == "failure":
            message = f"Connexion à l'API refusée{f' ({reason})' if reason else ''}{f' pour {user}' if user else ''}{origin}"
        else:
            message = f"Connexion à l'API réussie pour {user or '?'}{origin}"
    else:
        doc["event"].update({"category": ["web"], "type": ["info"], "action": action_name(name or "app_log"),
                             "outcome": "unknown"})
        message = text or name or "Événement applicatif"
    label = severity.from_app(level, doc["event"]["action"], doc["event"]["outcome"])
    return Parsed(doc, timestamp, label, message)


def parse(raw: dict) -> Parsed:
    payload = raw["payload"]
    record = None
    if raw["payload_format"] == "json" or payload.lstrip().startswith("{"):
        try:
            record = json.loads(payload)
        except ValueError as exc:
            raise unparsable(f"journal applicatif : JSON illisible ({exc})") from exc
        if isinstance(record, dict) and isinstance(record.get("log"), str) and len(record) <= 2:
            payload, record = record["log"], None      # ligne brute emballée par l'agent
            if payload.lstrip().startswith("{"):
                return parse(dict(raw, payload_format="text", payload=payload))
    if isinstance(record, dict):
        return parse_app(record)
    if record is not None:
        raise unparsable("journal applicatif : objet JSON attendu")
    return parse_access(payload)
