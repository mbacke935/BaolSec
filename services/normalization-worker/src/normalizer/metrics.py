"""Métriques Prometheus du service de normalisation (EF-12)."""
from prometheus_client import Counter, Gauge, Histogram

EVENTS = Counter(
    "baolsec_normalizer_events_total",
    "Messages raw-events traités, par type de source et issue",
    ["source_type", "outcome"],      # published, duplicate, dlq, retry
)
DATASETS = Counter("baolsec_normalizer_datasets_total", "Événements normalisés par jeu de données (event.dataset)",
                   ["dataset", "action"])
REJECTIONS = Counter("baolsec_normalizer_rejections_total", "Messages envoyés en file de rejet, par motif",
                     ["reason_code"])
SECONDS = Histogram("baolsec_normalizer_seconds", "Durée de traitement d'un message (analyse, contrôle, PubAck)",
                    buckets=(0.0005, 0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5))
UNKNOWN_SOURCES = Counter("baolsec_normalizer_unknown_sources_total",
                          "Événements dont la source n'est plus dans le référentiel (non enrichis)")
SOURCES_CACHE_AGE = Gauge("baolsec_normalizer_sources_cache_age_seconds", "Âge du cache des sources")
PAUSED = Gauge("baolsec_normalizer_paused", "1 si la lecture de raw-events est suspendue (référentiel indisponible)")
