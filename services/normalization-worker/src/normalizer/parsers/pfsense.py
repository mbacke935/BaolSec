"""Pare-feu pfSense : messages « filterlog » reçus par le collecteur Syslog (C7).

Format des champs (documentation Netgate, « Filter Log Format ») :
  règle, sous-règle, ancre, tracker, interface, motif, action, sens, version IP, puis
  IPv4 : TOS, ECN, TTL, ID, offset, drapeaux, n° de protocole, protocole, longueur, source, destination
  IPv6 : classe, flow label, hop limit, protocole, n° de protocole, longueur, source, destination
  TCP / UDP : port source, port destination, longueur des données (puis drapeaux TCP…)
pfSense n'envoie que les événements du pare-feu (voir agents/README.md) : tout autre message
d'un pare-feu part en file de rejet.
"""
from __future__ import annotations

import re
from datetime import datetime

from .. import severity
from .base import Parsed, ip_or_none, parse_syslog, port_or_none, put, unparsable

ACTIONS = {"pass": ("connection_allowed", "allowed", "autorisée"),
           "block": ("connection_denied", "denied", "bloquée"),
           "reject": ("connection_denied", "denied", "rejetée")}
DIRECTIONS = {"in": "ingress", "out": "egress"}


def _transport(name: str) -> str:
    name = name.lower()
    return "icmp" if name in ("ipv6-icmp", "icmp6", "icmpv6") else re.sub(r"[^a-z0-9]", "", name)


def parse_filterlog(csv: str, observer_name: str | None, timestamp: datetime | None, code: int | None) -> Parsed:
    f = csv.strip().split(",")
    if len(f) < 9:
        raise unparsable("message filterlog trop court")
    rule, iface, reason, act, way, version = f[0], f[4], f[5], f[6].lower(), f[7].lower(), f[8]
    if act not in ACTIONS:
        raise unparsable(f"action filterlog inconnue : {act!r}")
    try:
        if version == "4":
            proto, src, dst, rest = f[16], f[18], f[19], f[20:]
        elif version == "6":
            proto, src, dst, rest = f[12], f[15], f[16], f[17:]
        else:
            raise unparsable(f"version IP filterlog inconnue : {version!r}")
    except IndexError as exc:
        raise unparsable("message filterlog incomplet") from exc

    transport = _transport(proto)
    sport = dport = None
    if transport in ("tcp", "udp") and len(rest) >= 2:
        sport, dport = port_or_none(rest[0]), port_or_none(rest[1])
    src_ip, dst_ip = ip_or_none(src), ip_or_none(dst)
    if not src_ip or not dst_ip:
        raise unparsable("adresses source ou destination illisibles dans filterlog")

    action, decision, verb = ACTIONS[act]
    outcome = "failure" if action == "connection_denied" else "success"
    doc: dict = {"event": {"category": ["network"], "type": ["connection", decision], "action": action,
                           "outcome": outcome, "provider": "filterlog", "dataset": "pfsense.filterlog"}}
    put(doc, "observer.name", observer_name)
    doc["observer"] = {**doc.get("observer", {}), "vendor": "Netgate", "product": "pfSense", "type": "firewall"}
    put(doc, "source.ip", src_ip)
    put(doc, "source.port", sport)
    put(doc, "destination.ip", dst_ip)
    put(doc, "destination.port", dport)
    put(doc, "network.transport", transport or None)
    put(doc, "network.direction", DIRECTIONS.get(way, "unknown"))
    put(doc, "rule.id", rule or None)
    put(doc, "log.syslog.severity.code", code)

    target = f"{dst_ip}:{dport}" if dport else dst_ip
    why = "" if reason == "match" else f", motif {reason}"
    message = f"Connexion {transport.upper() or 'IP'} {verb} de {src_ip} vers {target} (interface {iface}{why})"
    return Parsed(doc, timestamp, severity.from_firewall(action), message)


def parse(raw: dict, received: datetime, tz) -> Parsed:
    if raw["payload_format"] != "text":
        raise unparsable("un événement de pare-feu doit être une ligne Syslog")
    line = parse_syslog(raw["payload"], received, tz)
    if line is None:
        raise unparsable("ligne de pare-feu sans en-tête Syslog reconnaissable")
    if line.program == "filterlog":
        return parse_filterlog(line.message, line.host, line.timestamp, line.severity_code)
    if line.program == "kernel":       # pare-feu Linux enregistré comme source de type firewall
        from .iptables import is_iptables, parse_message
        if is_iptables(line.message):
            return parse_message(line.message, line.host, line.timestamp, line.severity_code)
    raise unparsable(f"message de pare-feu non pris en charge (programme {line.program or 'absent'})")
