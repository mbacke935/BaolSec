"""Configuration du service Indexing Worker (C19)."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", env_file=".env", extra="ignore")

    # NATS
    nats_url: str = "nats://localhost:4222"
    nats_token: str = ""

    # Streams à consommer
    normalized_stream: str = "NORMALIZED_EVENTS"
    normalized_durable: str = "indexing-normalized"
    alerts_stream: str = "ALERTS"
    alerts_durable: str = "indexing-alerts"
    incidents_stream: str = "INCIDENTS"
    incidents_durable: str = "indexing-incidents"
    fetch_batch: int = 50

    # OpenSearch
    opensearch_url: str = "http://localhost:9200"
    opensearch_user: str = ""
    opensearch_password: str = ""

    # PostgreSQL (optionnel — pour enrichissement)
    postgres_dsn: str = ""
    db_pool_size: int = 5
    db_timeout_s: float = 5.0

    # Supervision
    metrics_host: str = "0.0.0.0"
    metrics_port: int = 9106
