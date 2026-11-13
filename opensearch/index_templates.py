"""Création des index templates OpenSearch pour BaolSec (C19).

Lance ce script une fois après le démarrage d'OpenSearch :
    python opensearch/index_templates.py

Il crée deux index templates :
  - baolsec-events-*  : événements normalisés
  - baolsec-alerts-*  : alertes
  - baolsec-incidents-* : incidents (résumés dénormalisés pour recherche)
"""
from __future__ import annotations

import os
import sys
import json
import urllib.request
import urllib.error

OPENSEARCH_URL = os.environ.get("OPENSEARCH_URL", "http://localhost:9200")


def put_template(name: str, body: dict) -> None:
    url = f"{OPENSEARCH_URL}/_index_template/{name}"
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method="PUT",
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as resp:
            print(f"  ✓ template '{name}' : {resp.status}")
    except urllib.error.HTTPError as e:
        print(f"  ✗ template '{name}' : HTTP {e.code} — {e.read().decode()}", file=sys.stderr)
        sys.exit(1)


EVENTS_TEMPLATE = {
    "index_patterns": ["baolsec-events-*"],
    "template": {
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
            "index.refresh_interval": "5s",
        },
        "mappings": {
            "dynamic": "strict",
            "properties": {
                "@timestamp":   {"type": "date"},
                "source_id":    {"type": "keyword"},
                "source_name":  {"type": "keyword"},
                "event_id":     {"type": "keyword"},
                "category":     {"type": "keyword"},
                "action":       {"type": "keyword"},
                "severity":     {"type": "keyword"},
                "criticality":  {"type": "integer"},
                "host":         {"type": "keyword"},
                "user":         {"type": "keyword"},
                "ip_src":       {"type": "ip"},
                "ip_dst":       {"type": "ip"},
                "port_src":     {"type": "integer"},
                "port_dst":     {"type": "integer"},
                "message":      {"type": "text", "analyzer": "standard"},
                "raw":          {"type": "text", "index": False},
                "extra":        {"type": "object", "dynamic": True},
            },
        },
    },
    "priority": 100,
}

ALERTS_TEMPLATE = {
    "index_patterns": ["baolsec-alerts-*"],
    "template": {
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
        },
        "mappings": {
            "dynamic": "strict",
            "properties": {
                "@timestamp":   {"type": "date"},
                "alert_id":     {"type": "keyword"},
                "incident_id":  {"type": "keyword"},
                "rule_id":      {"type": "keyword"},
                "rule_name":    {"type": "keyword"},
                "source_id":    {"type": "keyword"},
                "source_name":  {"type": "keyword"},
                "severity":     {"type": "keyword"},
                "title":        {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                "detail":       {"type": "object", "dynamic": True},
                "fired_at":     {"type": "date"},
            },
        },
    },
    "priority": 100,
}

INCIDENTS_TEMPLATE = {
    "index_patterns": ["baolsec-incidents-*"],
    "template": {
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
        },
        "mappings": {
            "dynamic": "strict",
            "properties": {
                "@timestamp":    {"type": "date"},
                "incident_id":   {"type": "keyword"},
                "title":         {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                "description":   {"type": "text"},
                "state":         {"type": "keyword"},
                "severity":      {"type": "keyword"},
                "opened_at":     {"type": "date"},
                "closed_at":     {"type": "date"},
                "alert_count":   {"type": "integer"},
                "source_ids":    {"type": "keyword"},
                "rule_ids":      {"type": "keyword"},
            },
        },
    },
    "priority": 100,
}


def main() -> None:
    print(f"Connexion à {OPENSEARCH_URL} …")
    put_template("baolsec-events", EVENTS_TEMPLATE)
    put_template("baolsec-alerts", ALERTS_TEMPLATE)
    put_template("baolsec-incidents", INCIDENTS_TEMPLATE)
    print("Index templates créés.")


if __name__ == "__main__":
    main()
