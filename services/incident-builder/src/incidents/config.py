"""Configuration du service Incidents, lue dans les variables d'environnement (préfixe INCIDENTS_).

Les variables obligatoires sont contrôlées au démarrage : un service mal configuré ne démarre pas (C3 4.1).
"""
from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="INCIDENTS_", extra="ignore")

    broker_url: str = Field("nats://broker:4222", validation_alias="BROKER_URL")
    broker_token: str | None = Field(None, validation_alias="BROKER_TOKEN")
    stream: str = "ALERTS"
    durable: str = "incident-builder"
    fetch_batch: int = Field(50, ge=1, le=500)

    # PostgreSQL : compte svc_incidents, seul écrivain du schéma incidents (C4 2.2)
    postgres_dsn: str = Field(..., min_length=1)
    db_pool_size: int = Field(5, ge=1, le=50)
    db_timeout_s: float = Field(5.0, gt=0)

    # Commandes de l'API (C5 section 6) : appel HTTP interne authentifié par un secret partagé
    command_token: str = Field(..., min_length=32)

    contracts_dir: Path = Path("/opt/baolsec/contracts")
    metrics_host: str = "0.0.0.0"
    metrics_port: int = 9000
