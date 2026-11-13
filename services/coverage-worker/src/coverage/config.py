"""Configuration du service Couverture, lue dans les variables d'environnement (préfixe COVERAGE_).

Les variables obligatoires sont contrôlées au démarrage : un service mal configuré ne démarre pas (C3 4.1).
"""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="COVERAGE_", extra="ignore")

    broker_url: str = Field("nats://broker:4222", validation_alias="BROKER_URL")
    broker_token: str | None = Field(None, validation_alias="BROKER_TOKEN")

    # Flux NATS consommés (C3 W6)
    raw_stream: str = "RAW_EVENTS"
    raw_durable: str = "coverage-worker-raw"
    normalized_stream: str = "NORMALIZED_EVENTS"
    normalized_durable: str = "coverage-worker-norm"
    fetch_batch: int = Field(100, ge=1, le=1000)

    # PostgreSQL : compte svc_couverture (C4 2.2, 0005_comptes.sql)
    postgres_dsn: str = Field(..., min_length=1)
    db_pool_size: int = Field(3, ge=1, le=20)
    db_timeout_s: float = Field(5.0, gt=0)

    # Cadence d'évaluation (SourceStateEvaluator)
    eval_interval_s: float = Field(60.0, gt=0, description="Intervalle entre deux évaluations de couverture (secondes)")

    metrics_host: str = "0.0.0.0"
    metrics_port: int = 9001
