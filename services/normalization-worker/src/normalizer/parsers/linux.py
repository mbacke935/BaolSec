"""Serveurs Linux : auth.log (ligne Syslog) et journald (enregistrement JSON), plus le journal du pare-feu.

Événements reconnus (C5, section 3) : connexions SSH, commandes et authentifications sudo,
échecs d'authentification PAM. Une ligne Syslog lisible mais absente de la table reste
normalisée (catégorie host, type info, action dérivée du programme).
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from .. import severity
from . import iptables
from .base import Parsed, action_name, clean, ip_or_none, parse_syslog, port_or_none, put, unparsable

_REPEATED = re.compile(r"^message repeated \d+ times: \[ ?(?P<inner>.*?) ?\]$", re.S)
_SSH_FAILED = re.compile(r"^Failed (?P<method>\S+) for (?P<invalid>invalid user )?(?P<user>\S*) from (?P<ip>\S+)(?: port (?P<port>\d+))?")
_SSH_ACCEPTED = re.compile(r"^Accepted (?P<method>\S+) for (?P<user>\S+) from (?P<ip>\S+)(?: port (?P<port>\d+))?")
_SSH_INVALID = re.compile(r"^Invalid user (?P<user>\S*) from (?P<ip>\S+)(?: port (?P<port>\d+))?")
_SUDO_CMD = re.compile(r"^\s*(?P<user>\S+) : (?P<info>.*?)\bCOMMAND=(?P<cmd>.*)$", re.S)
_PAM_FAILURE = re.compile(r"(?:pam_unix\((?P<service>[^:)]+)(?::[^)]*)?\): )?authentication failure;(?P<kv>.*)$", re.S)
_KV = re.compile(r"(\w+)=(\S*)")
SUDO_FAILURE_MARKS = ("incorrect password attempt", "NOT in sudoers", "command not allowed", "user NOT")


def _base(program: str | None, pid: int | None, host: str | None, code: int | None) -> dict:
    doc: dict = {"event": {"dataset": "linux.auth"}}
    put(doc, "event.provider", program)
    put(doc, "host.name", host)
    put(doc, "process.name", program)
    put(doc, "process.pid", pid)
    put(doc, "log.syslog.severity.code", code)
    return doc


def _auth(doc: dict, action: str, outcome: str, types: list[str] | None = None, category: str = "authentication") -> dict:
    doc["event"].update({"category": [category], "type": types or ["start"], "action": action, "outcome": outcome})
    return doc


def interpret(program: str | None, pid: int | None, host: str | None, message: str,
              timestamp: datetime | None, code: int | None) -> Parsed:
    """Événement Linux à partir de ses éléments Syslog (ligne d'auth.log ou champs journald)."""
    if program in ("kernel", None) and iptables.is_iptables(message):
        return iptables.parse_message(message, host, timestamp, code)

    m = _REPEATED.match(message)
    if m:   # rsyslog regroupe les répétitions : le message d'origine est entre crochets
        message = m["inner"]
    prog = (program or "").lower()
    base_prog = prog.split("(")[0]
    doc = _base(program, pid, host, code)
    label = severity.from_syslog(code)

    if base_prog == "sshd":
        if m := _SSH_FAILED.match(message):
            user, ip, port = clean(m["user"]), ip_or_none(m["ip"]), port_or_none(m["port"])
            put(doc, "user.name", user)
            put(doc, "source.ip", ip)
            put(doc, "source.port", port)
            return Parsed(_auth(doc, "ssh_login", "failure"), timestamp, label,
                          f"Échec d'authentification SSH pour {user or '?'} depuis {ip or '?'}")
        if m := _SSH_ACCEPTED.match(message):
            user, ip, port = clean(m["user"]), ip_or_none(m["ip"]), port_or_none(m["port"])
            put(doc, "user.name", user)
            put(doc, "source.ip", ip)
            put(doc, "source.port", port)
            return Parsed(_auth(doc, "ssh_login", "success"), timestamp, label,
                          f"Connexion SSH réussie pour {user or '?'} depuis {ip or '?'}")
        if m := _SSH_INVALID.match(message):
            user, ip, port = clean(m["user"]), ip_or_none(m["ip"]), port_or_none(m["port"])
            put(doc, "user.name", user)
            put(doc, "source.ip", ip)
            put(doc, "source.port", port)
            return Parsed(_auth(doc, "ssh_login", "failure"), timestamp, label,
                          f"Connexion SSH avec un utilisateur inconnu ({user or 'vide'}) depuis {ip or '?'}")

    if base_prog == "sudo" and (m := _SUDO_CMD.match(message)):
        user, cmd = clean(m["user"]), m["cmd"].strip()
        info = dict(_KV.findall(m["info"].replace(" ; ", " ")))
        failed = any(mark in message for mark in SUDO_FAILURE_MARKS)
        put(doc, "user.name", user)
        put(doc, "process.command_line", cmd or None)
        _auth(doc, "sudo_command", "failure" if failed else "success", ["start"], "process")
        target = clean(info.get("USER"))
        verb = "refusée" if failed else "exécutée"
        return Parsed(doc, timestamp, label, f"Commande sudo {verb} pour {user or '?'} : {cmd}",
                      extra_users=[target] if target else [])

    if m := _PAM_FAILURE.search(message):
        kv = dict(_KV.findall(m["kv"]))
        service = (m["service"] or base_prog or "").lower()
        user = clean(kv.get("user")) or clean(kv.get("ruser"))
        ip = ip_or_none(kv.get("rhost"))
        put(doc, "user.name", user)
        put(doc, "source.ip", ip)
        action = "sudo_auth" if service == "sudo" else "pam_auth"
        _auth(doc, action, "failure")
        who = f" pour {user}" if user else ""
        where = f" depuis {ip}" if ip else ""
        return Parsed(doc, timestamp, label, f"Échec d'authentification {service or 'PAM'}{who}{where}")

    # Lisible mais hors de la table C5 : conservé, sans interprétation.
    doc["event"].update({"category": ["host"], "type": ["info"],
                         "action": action_name(base_prog or "syslog"), "outcome": "unknown"})
    return Parsed(doc, timestamp, label, message.strip() or f"Message {program or 'Syslog'}")


def parse_text(payload: str, received: datetime, tz) -> Parsed:
    line = parse_syslog(payload, received, tz)
    if line is None:
        # Ligne du noyau sans en-tête Syslog (export de journal, kern.log retraité)
        if iptables.is_iptables(payload):
            return iptables.parse_message(payload, None, None, None)
        raise unparsable("ligne Linux sans en-tête Syslog reconnaissable")
    if line.program is None:
        if iptables.is_iptables(line.message):     # routeur sans étiquette de programme (EdgeOS…)
            return iptables.parse_message(line.message, line.host, line.timestamp, line.severity_code)
        word = re.match(r"^([A-Za-z][\w.-]*)", line.message)   # « syslogd 1.4.1: restart. »
        if not word:
            raise unparsable("ligne Syslog sans nom de programme")
        return interpret(word.group(1), None, line.host, line.message, line.timestamp, line.severity_code)
    return interpret(line.program, line.pid, line.host, line.message, line.timestamp, line.severity_code)


def _int(value) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def parse_journald(record: dict, read_at: datetime | None) -> Parsed:
    """Enregistrement journald transmis par l'entrée systemd de Fluent Bit."""
    message = record.get("MESSAGE")
    if isinstance(message, list):           # journald stocke un message binaire en tableau d'octets
        message = bytes(message).decode("utf-8", "replace")
    if not isinstance(message, str) or not message.strip():
        raise unparsable("enregistrement journald sans MESSAGE")

    usec = _int(record.get("_SOURCE_REALTIME_TIMESTAMP"))
    if usec:
        timestamp = datetime.fromtimestamp(usec / 1_000_000, timezone.utc)
    else:   # Fluent Bit date l'enregistrement avec l'heure du journal : c'est l'heure d'origine
        timestamp = read_at
    code = _int(record.get("PRIORITY"))
    code = code if code is not None and 0 <= code <= 7 else None
    program = record.get("SYSLOG_IDENTIFIER") or record.get("_COMM")
    if record.get("_TRANSPORT") == "kernel":
        program = "kernel"
    return interpret(program, _int(record.get("SYSLOG_PID") or record.get("_PID")),
                     record.get("_HOSTNAME"), message, timestamp, code)


def parse(raw: dict, received: datetime, read_at: datetime | None, tz) -> Parsed:
    if raw["payload_format"] == "json":
        try:
            record = json.loads(raw["payload"])
        except ValueError as exc:
            raise unparsable(f"JSON illisible : {exc}") from exc
        if isinstance(record, dict) and "MESSAGE" in record:
            return parse_journald(record, read_at)
        if isinstance(record, dict) and isinstance(record.get("log"), str):
            return parse_text(record["log"], received, tz)
        raise unparsable("enregistrement JSON Linux sans MESSAGE ni log")
    return parse_text(raw["payload"], received, tz)
