"""Métriques Prometheus du moteur de détection (C3, fiche Détection)."""
from prometheus_client import Counter, Gauge, Histogram

EVALUATIONS = Counter("baolsec_detector_evaluations_total",
                      "Évaluations règle × événement, par règle et issue",
                      ["rule", "outcome"])     # counted, fired, duplicate, late, suppressed
ALERTS = Counter("baolsec_detector_alerts_total", "Alertes publiées dans alerts, par règle et sévérité",
                 ["rule", "severity"])
EVENTS = Counter("baolsec_detector_events_total", "Messages normalized-events traités, par issue", ["outcome"])
LATE = Counter("baolsec_detector_late_events_total", "Événements en retard non comptés (fenêtre expirée)", ["rule"])
CONFLICTS = Counter("baolsec_detector_state_conflicts_total", "Écritures conditionnelles refusées (autre instance)")
PENDING = Gauge("baolsec_detector_pending_alerts", "Alertes en attente de publication au dernier contrôle")
REPUBLISHED = Counter("baolsec_detector_republished_total", "Alertes en attente republiées par le contrôle périodique")
RULES_LOADED = Gauge("baolsec_detector_rules_loaded", "Règles actives chargées")
RULES_REJECTED = Gauge("baolsec_detector_rules_rejected", "Règles refusées par le contrat rule/v1")
SECONDS = Histogram("baolsec_detector_seconds", "Durée de traitement d'un événement (toutes règles)",
                    buckets=(0.0005, 0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5))
