"""Évaluation d'une règle sur un événement normalisé (C12) et état des fenêtres (C14).

Ce module ne fait aucune entrée-sortie : il reçoit l'état lu dans le KV et rend le nouvel état
et, s'il y a lieu, l'alerte à publier. Le worker se charge de la lecture, de l'écriture
conditionnelle et de la publication.

Règle « window » (fenêtre glissante sur l'horodatage d'origine des événements) :
- chaque événement retenu est mémorisé avec son event_id : un message relivré n'est jamais compté deux fois ;
- les événements plus anciens que (plus récent - fenêtre) sortent du compte ;
- seuil atteint : une alerte, dont l'identifiant dépend de (règle, clé, début de fenêtre) ;
  le compteur repart de zéro et les événements de la même rafale (avant fin de fenêtre) ne déclenchent rien ;
- followed_by : l'alerte n'est émise que lorsqu'un événement déclencheur (ex. un succès) arrive
  alors que le seuil est atteint dans la fenêtre qui le précède.
Événement en retard (source directe) : plus ancien que maintenant - fenêtre - tolérance ; il n'est pas compté.
Une source rejouée (ingestion_mode = rejeu) est évaluée sur ses seules dates, sans contrôle de retard.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from . import fields
from .rules.model import Rule
from .timeutil import parse_ms

ENTITIES = (("u", "user.name"), ("ip", "source.ip"), ("h", "host.name"), ("d", "destination.ip"))
MAX_EVENTS = 1000              # au-delà, les plus anciens sont oubliés (taille d'une entrée KV : 256 Kio)


@dataclass
class Decision:
    outcome: str                      # ignored, late, duplicate, suppressed, counted, fired
    state: dict | None = None         # nouvel état à écrire (None : rien à écrire)
    fire: dict | None = None          # éléments de l'alerte à construire


def group_values(rule: Rule, doc: dict) -> list[str] | None:
    out = []
    for path in rule.group_by:
        vals = fields.values(doc, path)
        if not vals or vals[0] in ("", None):
            return None
        out.append(str(vals[0]))
    return out


def group_key(rule: Rule, values: list[str], event_id: str) -> str:
    return "|".join(values) if values else event_id


def alert_id(code: str, key: str, window_start_iso: str) -> str:
    return hashlib.sha256(f"{code}\n{key}\n{window_start_iso}".encode("utf-8")).hexdigest()


def entities(doc: dict) -> dict:
    return {k: fields.get(doc, p) for k, p in ENTITIES if fields.get(doc, p) not in (None, "")}


def evaluate_simple(rule: Rule, doc: dict) -> Decision:
    if not rule.matches(doc):
        return Decision("ignored")
    values = group_values(rule, doc) if rule.group_by else []
    if values is None:
        return Decision("ignored")
    ts = parse_ms(doc["@timestamp"])
    entry = [doc["event"]["id"], ts, None, entities(doc)]
    return Decision("fired", fire={"key": group_key(rule, values, doc["event"]["id"]), "values": values,
                                   "window_start": ts, "events": [entry], "count": 1, "trigger": doc})


def evaluate_window(rule: Rule, doc: dict, state: dict | None, now_ms: int, tolerance_s: int) -> Decision:
    counted = rule.matches(doc)
    trigger = rule.trigger(doc) if rule.trigger else False
    if not counted and not trigger:
        return Decision("ignored")
    values = group_values(rule, doc)
    if values is None:
        return Decision("ignored")
    ts = parse_ms(doc["@timestamp"])
    window_ms = rule.window_s * 1000
    replay = fields.get(doc, "baolsec.source.ingestion_mode") == "rejeu"
    if not replay and ts < now_ms - window_ms - tolerance_s * 1000:
        return Decision("late")

    key = group_key(rule, values, doc["event"]["id"])
    st = state or {"rule": rule.code, "group": key, "events": [], "suppress_until": 0, "pending": None}
    st = {**st, "events": [list(e) for e in st["events"]], "version": rule.version}
    event_id = doc["event"]["id"]
    if any(e[0] == event_id for e in st["events"]) or event_id in st.get("seen_triggers", []):
        return Decision("duplicate")
    if ts < st["suppress_until"]:
        return Decision("suppressed")

    if counted:
        distinct = None
        if rule.distinct:
            dv = fields.values(doc, rule.distinct)
            if not dv:
                return Decision("ignored")
            distinct = str(dv[0])
        st["events"].append([event_id, ts, distinct, entities(doc)])
        newest = max(e[1] for e in st["events"])
        st["events"] = sorted((e for e in st["events"] if e[1] > newest - window_ms), key=lambda e: e[1])[-MAX_EVENTS:]
        if rule.trigger is None and _count(st["events"]) >= rule.threshold:
            return _fire(rule, st, values, key, st["events"], _count(st["events"]), doc, ts)
        return Decision("counted", state=st)

    # Événement déclencheur (followed_by) : le seuil doit être atteint dans la fenêtre qui le précède.
    before = [e for e in st["events"] if ts - window_ms < e[1] <= ts]
    if _count(before) >= rule.threshold:
        trig = [event_id, ts, None, entities(doc)]
        return _fire(rule, st, values, key, before + [trig], _count(before), doc, ts)
    return Decision("counted", state=st) if state is not None else Decision("ignored")


def _count(events: list) -> int:
    distinct = {e[2] for e in events if e[2] is not None}
    return len(distinct) if distinct else len(events)


def _fire(rule: Rule, st: dict, values: list[str], key: str, events: list, count: int, doc: dict, ts: int) -> Decision:
    window_start = min(e[1] for e in events)
    st["events"] = []
    st["suppress_until"] = (ts if rule.trigger else window_start) + rule.window_s * 1000
    st["seen_triggers"] = [doc["event"]["id"]] if rule.trigger else []
    return Decision("fired", state=st, fire={"key": key, "values": values, "window_start": window_start,
                                             "events": events, "count": count, "trigger": doc})
