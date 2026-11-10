"""Construction d'une alerte alert/v1 (C5) à partir d'une décision du moteur."""
from __future__ import annotations

import re

from . import fields
from .engine import alert_id
from .rules.model import Rule
from .timeutil import human, iso

SCORES = {"faible": 1, "moyenne": 2, "elevee": 3, "critique": 4}
MAX_EVENT_IDS = 200
_VAR = re.compile(r"\{([a-z@][a-z0-9_.]*)\}")


def _message(rule: Rule, fire: dict) -> str:
    known = dict(zip(rule.group_by, fire["values"]))
    known["count"] = str(fire["count"])
    known["window"] = human(rule.window_s) if rule.window_s else ""

    def sub(m: re.Match) -> str:
        name = m.group(1)
        if name in known:
            return known[name]
        v = fields.values(fire["trigger"], name)
        return str(v[0]) if v else "?"
    return _VAR.sub(sub, rule.message)[:2000]


def build(rule: Rule, fire: dict) -> dict:
    trigger = fire["trigger"]
    window_start = iso(fire["window_start"])
    group = dict(zip(rule.group_by, fire["values"]))

    def pick(path: str):
        if path in group:
            return group[path]
        v = fields.values(trigger, path)
        return v[0] if v else None

    doc: dict = {
        "@timestamp": iso(fire["events"][-1][1]),
        "ecs": {"version": "9.5.0"},
        "event": {"id": alert_id(rule.code, fire["key"], window_start), "kind": "alert", "category": list(rule.category)},
        "rule": {"id": rule.code, "name": rule.name, "version": str(rule.version)},
    }
    for path, (top, leaf) in {"user.name": ("user", "name"), "source.ip": ("source", "ip"),
                              "host.name": ("host", "name"), "destination.ip": ("destination", "ip")}.items():
        v = pick(path)
        if v not in (None, ""):
            doc[top] = {leaf: str(v)}

    related = {"ip": [], "user": [], "hosts": []}
    for _eid, _ts, _d, ent in fire["events"]:
        for k, target in (("ip", "ip"), ("d", "ip"), ("u", "user"), ("h", "hosts")):
            v = ent.get(k)
            if v and str(v) not in related[target]:
                related[target].append(str(v))
    related = {k: v for k, v in related.items() if v}
    if related:
        doc["related"] = related

    ids = list(dict.fromkeys(e[0] for e in fire["events"]))[-MAX_EVENT_IDS:]
    doc["message"] = _message(rule, fire)
    doc["baolsec"] = {
        "contract": "alert/v1",
        "severity": {"label": rule.severity, "score": SCORES[rule.severity]},
        "alert": {"window_start": window_start, "group_key": fire["key"], "event_ids": ids},
    }
    return doc
