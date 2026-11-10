"""Configuration du moteur de détection, lue dans les variables d'environnement (préfixe DETECTOR_)."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DETECTOR_", extra="ignore")

    broker_url: str = Field("nats://broker:4222", validation_alias="BROKER_URL")
    broker_token: str | None = Field(None, validation_alias="BROKER_TOKEN")
    stream: str = "NORMALIZED_EVENTS"
    durable: str = "detection"
    output_subject: str = "alerts"
    fetch_batch: int = 100
    publish_timeout_s: float = 5.0

    # État des fenêtres (C14) : bucket KV du broker (ADR 0002)
    kv_bucket: str = "detection-state"
    late_tolerance_s: int = 120          # tolérance des événements en retard (C3 W3)
    pending_interval_s: float = 60.0     # relecture des alertes en attente
    cas_retries: int = 20                # écritures conditionnelles en conflit avant abandon (relivraison)

    # Règles : PostgreSQL (config.rules, compte svc_detection) ou dossier YAML (tests, développement)
    rules_source: Literal["postgres", "file"] = "postgres"
    postgres_dsn: str | None = Field(None, validation_alias="DETECTOR_POSTGRES_DSN")
    rules_dir: Path = Path("rules")
    rules_refresh_s: float = 30.0
    contracts_dir: Path = Path("/opt/baolsec/contracts")

    metrics_host: str = "0.0.0.0"
    metrics_port: int = 9000

    @model_validator(mode="after")
    def _rules(self) -> "Settings":
        if self.rules_source == "postgres" and not self.postgres_dsn:
            raise ValueError("DETECTOR_POSTGRES_DSN est obligatoire avec DETECTOR_RULES_SOURCE=postgres")
        return self
