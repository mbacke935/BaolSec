"""Journaux du pare-feu Linux (cible LOG d'iptables ou nftables) : « PRÉFIXE IN=… OUT=… SRC=… DST=… ».

Reçus d'un serveur Linux (journal du noyau). Décrits par observer.*, comme un pare-feu (C5).
La décision vient du préfixe choisi dans la règle LOG : DROP, REJECT, BLOCK ou DENY → refus ;
ACCEPT, ALLOW ou PASS → autorisation ; sinon la connexion est seulement journalisée.
"""
from __future__ import annotations

import re
from datetime import datetime

from .. import severity
from .base import Parsed, ip_or_none, port_or_none, put

_FIELDS = re.compile(r"\b(IN|OUT|SRC|DST|PROTO|SPT|DPT)=(\S*)")
_UPTIME = re.compile(r"^\[\s*\d+\.\d+\]\s*")
DENY_WORDS = ("DROP", "REJECT", "BLOCK", "DENY")
ALLOW_WORDS = ("ACCEPT", "ALLOW", "PASS")


def is_iptables(message: str) -> bool:
    return " SRC=" in message and " DST=" in message and "IN=" in message


def parse_message(message: str, observer_name: str | None, timestamp: datetime | None,
                  syslog_code: int | None) -> Parsed:
    fields = dict(_FIELDS.findall(message))
    prefix = _UPTIME.sub("", message.split("IN=", 1)[0]).strip().rstrip(":").strip()
    upper = prefix.upper()
    if any(w in upper for w in DENY_WORDS):
        action, types, verb = "connection_denied", ["connection", "denied"], "bloquée"
    elif any(w in upper for w in ALLOW_WORDS):
        action, types, verb = "connection_allowed", ["connection", "allowed"], "autorisée"
    else:
        action, types, verb = "connection_logged", ["connection"], "journalisée"

    src, dst = ip_or_none(fields.get("SRC")), ip_or_none(fields.get("DST"))
    proto = (fields.get("PROTO") or "").lower()
    proto = "icmp" if proto in ("icmpv6", "ipv6-icmp") else re.sub(r"[^a-z0-9]", "", proto)
    sport, dport = port_or_none(fields.get("SPT")), port_or_none(fields.get("DPT"))
    nic_in, nic_out = fields.get("IN"), fields.get("OUT")
    direction = "ingress" if nic_in and not nic_out else "egress" if nic_out and not nic_in else "unknown"

    outcome = "failure" if action == "connection_denied" else "success" if action == "connection_allowed" else "unknown"
    doc: dict = {"event": {"category": ["network"], "type": types, "action": action, "outcome": outcome,
                           "provider": "kernel", "dataset": "iptables.log"}}
    put(doc, "observer.name", observer_name)
    put(doc, "observer.product", "iptables")
    put(doc, "observer.type", "firewall")
    put(doc, "source.ip", src)
    put(doc, "source.port", sport)
    put(doc, "destination.ip", dst)
    put(doc, "destination.port", dport)
    put(doc, "network.transport", proto or None)
    put(doc, "network.direction", direction)
    put(doc, "rule.id", prefix or None)
    put(doc, "log.syslog.severity.code", syslog_code)

    target = f"{dst}:{dport}" if dst and dport else (dst or "?")
    message_fr = f"Connexion {proto.upper() or 'IP'} {verb} de {src or '?'} vers {target}"
    return Parsed(doc, timestamp, severity.from_firewall(action), message_fr)
