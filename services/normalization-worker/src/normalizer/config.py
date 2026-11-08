"""Configuration du service de normalisation, lue dans les variables d'environnement."""
from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NORMALIZER_", extra="ignore")

    # Broker (ADR 0002) — variables communes à tous les services, sans préfixe
    broker_url: str = Field("nats://broker:4222", validation_alias="BROKER_URL")
    broker_token: str | None = Field(None, validation_alias="BROKER_TOKEN")
    stream: str = "RAW_EVENTS"
    durable: str = "normalization"              # consommateur créé par init_broker.py (topologie C8)
    output_subject: str = "normalized-events"
    fetch_batch: int = 200
    publish_timeout_s: float = 5.0

    # Contrats (shared/contracts) : schémas utilisés pour contrôler l'entrée et la sortie
    contracts_dir: Path = Path("/opt/baolsec/contracts")

    # Référentiel des sources (C10) : PostgreSQL (compte svc_normalisation, lecture seule) ou fichier
    source_registry: Literal["postgres", "file"] = "postgres"
    postgres_dsn: str | None = Field(None, validation_alias="NORMALIZER_POSTGRES_DSN")
    sources_file: Path | None = None
    sources_refresh_s: float = 30.0
    sources_max_stale_s: float = 300.0

    # Fuseau des horodatages Syslog sans fuseau (RFC 3164). Africa/Dakar = UTC, sans heure d'été.
    syslog_timezone: str = "UTC"
    # Réseaux à classer « private » en plus des plages internes standard (ex. bloc public de l'entreprise)
    internal_networks: Annotated[list[str], NoDecode] = []

    # Supervision (réseau interne uniquement)
    metrics_host: str = "0.0.0.0"
    metrics_port: int = 9000

    @field_validator("internal_networks", mode="before")
    @classmethod
    def _split(cls, value):
        if isinstance(value, str):
            return [v.strip() for v in value.split(",") if v.strip()]
        return value

    @model_validator(mode="after")
    def _check(self) -> "Settings":
        if self.source_registry == "postgres" and not self.postgres_dsn:
            raise ValueError("NORMALIZER_POSTGRES_DSN est obligatoire avec NORMALIZER_SOURCE_REGISTRY=postgres")
        if self.source_registry == "file" and not self.sources_file:
            raise ValueError("NORMALIZER_SOURCES_FILE est obligatoire avec NORMALIZER_SOURCE_REGISTRY=file")
        ZoneInfo(self.syslog_timezone)          # fuseau inconnu : erreur au démarrage
        return self

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.syslog_timezone)
