"""Modèles d'index OpenSearch de BaolSec (C19), alignés sur les documents réellement indexés.

Les documents sont les messages des flux, tels quels : normalized_event/v1 et alert/v1 (ECS 9.5.0,
champs imbriqués event.*, source.ip, baolsec.*), et le résumé d'incident publié par l'outbox.
Les anciens modèles « strict » à champs plats (ip_src, raw…) ne correspondaient à aucun de ces
documents : appliqués, ils auraient fait rejeter chaque document. Ici les champs utilisés par la
recherche (EF-11) sont typés explicitement (dates, adresses IP, mots-clés) et le reste est
dynamique, sans analyse du texte brut (event.original) pour limiter la taille des index.

Appliqués par indexing-worker au démarrage (ensure_templates), et par opensearch/index_templates.py.
"""
from __future__ import annotations

KW = {"type": "keyword", "ignore_above": 1024}
IP = {"type": "ip", "ignore_malformed": True}
DATE = {"type": "date"}

_ECS_COMMON = {
    "@timestamp": DATE,
    "message": {"type": "text"},
    "event": {"properties": {
        "id": KW, "kind": KW, "category": KW, "type": KW, "action": KW, "outcome": KW,
        "provider": KW, "dataset": KW, "code": KW,
        "original": {"type": "text", "index": False},
    }},
    "source": {"properties": {"ip": IP, "port": {"type": "long"}}},
    "destination": {"properties": {"ip": IP, "port": {"type": "long"}}},
    "user": {"properties": {"name": KW, "domain": KW, "id": KW}},
    "host": {"properties": {"name": KW, "hostname": KW, "ip": IP}},
    "related": {"properties": {"ip": IP, "user": KW, "hosts": KW}},
    "rule": {"properties": {"id": KW, "name": KW, "version": KW}},
}

_SETTINGS = {"number_of_shards": 1, "number_of_replicas": 0, "index.refresh_interval": "5s",
             "index.mapping.total_fields.limit": 2000}

# Chaînes non déclarées : mot-clé (filtrable) plutôt que texte analysé.
_DYNAMIC = [{"strings_as_keywords": {"match_mapping_type": "string",
                                     "mapping": {"type": "keyword", "ignore_above": 1024}}}]

EVENTS_TEMPLATE = {
    "index_patterns": ["baolsec-events-*"],
    "priority": 100,
    "template": {
        "settings": _SETTINGS,
        "mappings": {"dynamic": True, "dynamic_templates": _DYNAMIC, "properties": {
            **_ECS_COMMON,
            "baolsec": {"properties": {
                "contract": KW, "received_at": DATE, "timestamp_source": KW,
                "source": {"properties": {"id": KW, "type": KW, "name": KW, "ingestion_mode": KW, "criticality": KW}},
                "severity": {"properties": {"label": KW, "score": {"type": "integer"}}},
            }},
        }},
    },
}

ALERTS_TEMPLATE = {
    "index_patterns": ["baolsec-alerts-*"],
    "priority": 100,
    "template": {
        "settings": _SETTINGS,
        "mappings": {"dynamic": True, "dynamic_templates": _DYNAMIC, "properties": {
            **_ECS_COMMON,
            "baolsec": {"properties": {
                "contract": KW,
                "severity": {"properties": {"label": KW, "score": {"type": "integer"}}},
                "alert": {"properties": {"window_start": DATE, "group_key": KW, "event_ids": KW}},
            }},
        }},
    },
}

INCIDENTS_TEMPLATE = {
    "index_patterns": ["baolsec-incidents-*"],
    "priority": 100,
    "template": {
        "settings": _SETTINGS,
        "mappings": {"dynamic": True, "dynamic_templates": _DYNAMIC, "properties": {
            "@timestamp": DATE, "incident_id": KW,
            "title": {"type": "text", "fields": {"keyword": KW}},
            "description": {"type": "text"}, "state": KW, "severity": KW,
            "opened_at": DATE, "closed_at": DATE, "last_activity_at": DATE,
            "alert_count": {"type": "integer"}, "source_ids": KW, "rule_ids": KW,
        }},
    },
}

TEMPLATES = {"baolsec-events": EVENTS_TEMPLATE, "baolsec-alerts": ALERTS_TEMPLATE,
             "baolsec-incidents": INCIDENTS_TEMPLATE}
