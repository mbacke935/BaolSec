"""Éléments communs aux parseurs : résultat d'analyse, valeurs absentes, adresses IP, en-tête Syslog."""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone, tzinfo

from baolsec_common.messaging import ProcessingError

# Valeurs génériques qui signifient « pas d'information » : le champ est omis (C5, conventions).
EMPTY_VALUES = {"", "-", "--", "n/a", "na", "null", "none", "anonymous", "anonymous logon", "(null)", "?"}


@dataclass
class Parsed:
    """Ce qu'un parseur tire d'un événement brut, avant l'enveloppe commune et l'enrichissement.

    doc        : fragment ECS (event, user, host, source, destination, network, observer…)
    timestamp  : heure d'origine si la source la fournit, sinon None (heure de réception utilisée)
    severity   : libellé de sévérité normalisée (C5, section 4)
    message    : texte lisible
    """
    doc: dict
    timestamp: datetime | None
    severity: str
    message: str
    extra_users: list[str] = field(default_factory=list)   # autres comptes cités (related.user)


def unparsable(reason: str) -> ProcessingError:
    """Le contenu ne correspond à aucun format connu : inutile de réessayer (dlq immédiate)."""
    return ProcessingError("parse_error", reason, permanent=True)


def clean(value) -> str | None:
    """Valeur utile ou None (valeurs génériques omises, aucune valeur inventée)."""
    if value is None:
        return None
    text = str(value).strip()
    return None if text.lower() in EMPTY_VALUES else text


def ip_or_none(value) -> str | None:
    """Adresse IP sous forme canonique (IPv6 compressée), ou None si ce n'est pas une adresse."""
    text = clean(value)
    if not text:
        return None
    text = text.strip("[]")
    if text.lower().startswith("::ffff:") and "." in text:      # IPv4 vue par une pile IPv6
        text = text[7:]
    try:
        return str(ipaddress.ip_address(text.split("%")[0]))
    except ValueError:
        return None


def port_or_none(value) -> int | None:
    text = clean(value)
    if not text or not text.isdigit():
        return None
    port = int(text)
    return port if 0 < port <= 65535 else None


def action_name(text: str) -> str:
    """Nom d'action conforme au contrat (^[a-z0-9_]+$), dérivé d'un nom de programme ou d'événement."""
    name = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return name or "unknown"


def put(doc: dict, path: str, value) -> None:
    """doc["a"]["b"] = value pour path « a.b » ; rien si la valeur est absente."""
    if value is None or value == "" or value == []:
        return
    keys = path.split(".")
    node = doc
    for k in keys[:-1]:
        node = node.setdefault(k, {})
    node[keys[-1]] = value


# --- En-tête Syslog ----------------------------------------------------------------------

MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], start=1)}

_PRI = re.compile(r"^<(\d{1,3})>")
# RFC 5424 : <PRI>1 2026-11-05T10:00:00.123Z host app procid msgid [sd] msg
_RFC5424 = re.compile(
    r"^1 (?P<ts>\S+) (?P<host>\S+) (?P<app>\S+) (?P<procid>\S+) (?P<msgid>\S+) "
    r"(?P<sd>-|(?:\[(?:[^\]\\]|\\.)*\])+)(?: (?P<msg>.*))?$", re.S)
# Horodatage ISO 8601 en tête de ligne (rsyslog d'Ubuntu 24.04 : 2026-11-05T10:00:00.123456+00:00)
_ISO = re.compile(r"^(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2}))\s+(?P<rest>.*)$", re.S)
# RFC 3164 : Nov  5 10:00:00 (année et fuseau absents)
_BSD = re.compile(r"^(?P<mon>[A-Z][a-z]{2}) +(?P<day>\d{1,2}) (?P<time>\d{2}:\d{2}:\d{2})(?:\.\d+)?\s+(?P<rest>.*)$", re.S)
# Programme : sshd[1842]:  sshd(pam_unix)[19939]:  kernel:  filterlog[3012]:
_TAG = re.compile(r"^(?P<prog>[^\s\[:]+?(?:\([^)]*\))?)(?:\[(?P<pid>\d+)\])?: ?(?P<msg>.*)$", re.S)


@dataclass
class SyslogLine:
    pri: int | None
    timestamp: datetime | None
    host: str | None
    program: str | None
    pid: int | None
    message: str

    @property
    def severity_code(self) -> int | None:
        return None if self.pri is None else self.pri & 7


def parse_iso(text: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else None


def bsd_timestamp(mon: str, day: str, hms: str, received: datetime, tz: tzinfo) -> datetime | None:
    """RFC 3164 n'a ni année ni fuseau : fuseau configuré (UTC par défaut), année de la réception.

    Un horodatage de plus de 2 jours dans le futur appartient à l'année précédente
    (ligne de décembre reçue en janvier).
    """
    month = MONTHS.get(mon)
    if not month:
        return None
    h, m, s = (int(x) for x in hms.split(":"))
    local_received = received.astimezone(tz)
    for year in (local_received.year, local_received.year - 1):
        try:
            dt = datetime(year, month, int(day), h, m, s, tzinfo=tz)
        except ValueError:          # 29 février d'une année non bissextile, heure invalide
            continue
        if dt <= received + timedelta(days=2):
            return dt.astimezone(timezone.utc)
    return None


def parse_syslog(line: str, received: datetime, tz: tzinfo) -> SyslogLine | None:
    """Analyse l'en-tête Syslog (PRI facultatif ; RFC 5424, ISO 8601 ou RFC 3164 ; hôte facultatif).

    Renvoie None si la ligne n'a pas d'en-tête Syslog reconnaissable.
    """
    text = line.rstrip("\r\n")
    pri = None
    m = _PRI.match(text)
    if m:
        pri = int(m.group(1))
        if pri > 191:
            return None
        text = text[m.end():]

    m = _RFC5424.match(text)
    if m:
        ts = parse_iso(m["ts"]) if m["ts"] != "-" else None
        host = None if m["host"] == "-" else m["host"]
        prog = None if m["app"] == "-" else m["app"]
        pid = int(m["procid"]) if m["procid"].isdigit() else None
        msg = (m["msg"] or "").lstrip("﻿")
        return SyslogLine(pri, ts, host, prog, pid, msg)

    m = _ISO.match(text)
    if m:
        ts, rest = parse_iso(m["ts"]), m["rest"]
    else:
        m = _BSD.match(text)
        if not m:
            return None
        ts, rest = bsd_timestamp(m["mon"], m["day"], m["time"], received, tz), m["rest"]

    # Après l'horodatage : « hôte programme[pid]: message », l'hôte pouvant manquer (pfSense).
    # Le nom d'hôte ne contient ni espace ni « [ » ni « : » : si le premier mot est suivi d'une
    # espace, c'est l'hôte ; s'il est suivi de « [pid]: » ou « : », c'est déjà le programme.
    host = None
    tag = _TAG.match(rest)
    if not tag:
        first, _, after = rest.partition(" ")
        tag = _TAG.match(after)
        if not tag:
            return SyslogLine(pri, ts, first or None, None, None, after)
        host = first
    return SyslogLine(pri, ts, host, tag["prog"], int(tag["pid"]) if tag["pid"] else None, tag["msg"])
