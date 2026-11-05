"""Métriques Prometheus de la passerelle (C3 4.3)."""
from prometheus_client import Counter, Gauge, Histogram

EVENTS = Counter(
    "baolsec_gateway_events_total",
    "Événements reçus par la passerelle, par source, transport et issue",
    ["source_id", "transport", "outcome"],          # outcome : stored, duplicate, rejected
)
REJECTIONS = Counter(
    "baolsec_gateway_rejections_total",
    "Requêtes, connexions ou événements refusés, par motif",
    ["transport", "reason"],
)
PUBLISH_SECONDS = Histogram(
    "baolsec_gateway_publish_seconds",
    "Délai entre la publication et le PubAck",
    buckets=(0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)
BROKER_ERRORS = Counter("baolsec_gateway_broker_errors_total", "Publications non confirmées par le broker")
SOURCES_CACHE_AGE = Gauge("baolsec_gateway_sources_cache_age_seconds", "Âge du cache des sources")
SYSLOG_CONNECTIONS = Gauge("baolsec_gateway_syslog_connections", "Connexions Syslog TLS ouvertes")
