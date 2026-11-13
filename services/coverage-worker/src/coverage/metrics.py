"""Métriques Prometheus du service Couverture (C17).

Exposées sur /metrics du serveur HTTP interne (port 9001).
"""
from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# ---- trackers ----
EVENTS_RECEIVED = Counter(
    "baolsec_coverage_events_received_total",
    "Nombre total d'événements bruts reçus (raw-events)",
    ["source"],
)
EVENTS_PROCESSED = Counter(
    "baolsec_coverage_events_processed_total",
    "Nombre total d'événements normalisés reçus (normalized-events)",
    ["source"],
)

# ---- évaluateur ----
EVAL_RUNS = Counter(
    "baolsec_coverage_eval_runs_total",
    "Nombre d'évaluations de couverture exécutées",
)
EVAL_DURATION = Histogram(
    "baolsec_coverage_eval_duration_seconds",
    "Durée d'une évaluation de couverture",
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0],
)
STATE_TRANSITIONS = Counter(
    "baolsec_coverage_state_transitions_total",
    "Nombre de transitions d'état de couverture",
    ["source", "previous_state", "new_state"],
)

# ---- état courant (gauge) ----
SOURCE_STATE = Gauge(
    "baolsec_coverage_source_state",
    "État de couverture actuel d'une source (1 = actif, 0 = autre)",
    ["source", "state"],
)
