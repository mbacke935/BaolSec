"""Configuration de l'API BaolSec (C20)."""
from __future__ import annotations
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # PostgreSQL
    postgres_dsn: str
    db_pool_size: int = 10
    db_timeout_s: float = 5.0

    # OpenSearch
    opensearch_url: str = "http://localhost:9200"
    opensearch_user: str = ""
    opensearch_password: str = ""

    # Auth JWT — jetons de courte durée avec renouvellement (C3/C5)
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 15           # jeton d'accès (court)
    jwt_refresh_expire_minutes: int = 480  # jeton de renouvellement (8 h)

    # Token de commande pour incident-builder
    command_token: str = ""

    # Supervision
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    metrics_host: str = "0.0.0.0"
    metrics_port: int = 9107
