"""Configuration de la passerelle, lue dans les variables d'environnement et validée au démarrage."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GATEWAY_", extra="ignore")

    # Broker (ADR 0002) — variables communes à tous les services, sans préfixe
    broker_url: str = Field("nats://broker:4222", validation_alias="BROKER_URL")
    broker_token: str | None = Field(None, validation_alias="BROKER_TOKEN")
    publish_timeout_s: float = 5.0
    publish_concurrency: int = 64

    # Référentiel des sources : PostgreSQL (lecture seule, compte svc_gateway) ou fichier (tests, développement)
    source_registry: Literal["postgres", "file"] = "postgres"
    postgres_dsn: str | None = Field(None, validation_alias="GATEWAY_POSTGRES_DSN")
    sources_file: Path | None = None
    sources_refresh_s: float = 30.0
    sources_max_stale_s: float = 300.0   # au-delà, refus (503) : une révocation ne peut pas rester ignorée

    # HTTPS
    http_host: str = "0.0.0.0"
    http_port: int = 8443
    tls_cert: Path = Path("/run/secrets/gateway.crt")
    tls_key: Path = Path("/run/secrets/gateway.key")
    max_body_bytes: int = 5 * 1024 * 1024
    max_events_per_batch: int = 1000

    # Syslog TCP/TLS (RFC 5425) — certificat client obligatoire
    syslog_enabled: bool = True
    syslog_host: str = "0.0.0.0"
    syslog_port: int = 6514
    syslog_client_ca: Path = Path("/run/secrets/sources-ca.crt")
    syslog_idle_timeout_s: float = 300.0

    # Limites
    max_event_chars: int = 65536          # raw_event/v1 : payload.maxLength
    rate_limit_events_per_s: float = 500.0
    rate_limit_burst: int = 5000

    # Supervision (réseau interne uniquement)
    metrics_host: str = "0.0.0.0"
    metrics_port: int = 9000

    @model_validator(mode="after")
    def _registry(self) -> "Settings":
        if self.source_registry == "postgres" and not self.postgres_dsn:
            raise ValueError("GATEWAY_POSTGRES_DSN est obligatoire avec GATEWAY_SOURCE_REGISTRY=postgres")
        if self.source_registry == "file" and not self.sources_file:
            raise ValueError("GATEWAY_SOURCES_FILE est obligatoire avec GATEWAY_SOURCE_REGISTRY=file")
        return self
