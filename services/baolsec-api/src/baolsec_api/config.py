"""Configuration de l'API BaolSec (C20)."""
from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Contrats partagés : /opt/baolsec/contracts dans l'image, shared/contracts dans le dépôt.
_REPO_CONTRACTS = Path(__file__).resolve().parents[4] / "shared" / "contracts"

DEFAULT_SERVICE_HEALTH = (
    "ingestion-gateway=http://ingestion-gateway:9000/health,"
    "normalization-worker=http://normalization-worker:9000/health,"
    "detection-worker=http://detection-worker:9000/health,"
    "incident-builder=http://incident-builder:9000/health,"
    "coverage-worker=http://coverage-worker:9001/health,"
    "indexing-worker=http://indexing-worker:9106/health"
)


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
    # Chemin vers le CA d'OpenSearch (recommandé quand l'URL est HTTPS), ex. /certs/root-ca.pem.
    opensearch_ca_cert: str = ""
    # HTTPS sans CA fourni : refus de démarrer, sauf désactivation explicite de la vérification
    # (développement avec le certificat de démonstration d'OpenSearch uniquement).
    opensearch_verify_certs: bool = True

    # Auth JWT — jetons de courte durée avec renouvellement (C3/C5)
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 15           # jeton d'accès (court)
    jwt_refresh_expire_minutes: int = 480  # jeton de renouvellement (8 h)

    # Verrouillage temporaire après des échecs répétés (ES-01, C3 4.6)
    auth_max_failed_attempts: int = Field(5, ge=1)
    auth_lockout_minutes: int = Field(15, ge=1)

    # Protection de l'API (ES-05) : limites par adresse cliente, taille des requêtes, CORS
    rate_limit_per_minute: int = Field(600, ge=10)
    login_rate_limit_per_minute: int = Field(10, ge=1)
    max_body_bytes: int = Field(1_048_576, ge=1024)
    cors_origins: str = "http://localhost:5174,http://localhost:3000"

    # Commandes vers le service Incidents (C5 §6) : appel HTTP interne authentifié
    # par un secret partagé. L'API ne modifie jamais incidents/alertes directement.
    command_token: str = ""
    incidents_command_url: str = "http://incident-builder:9000/commands"
    incidents_command_timeout_s: float = 10.0

    # File de rejet (GET /dlq, C5) : lecture seule du flux DLQ du broker
    broker_url: str = Field("nats://broker:4222", validation_alias="BROKER_URL")
    broker_token: str | None = Field(None, validation_alias="BROKER_TOKEN")
    dlq_stream: str = "DLQ"

    # Santé des services internes pour la page Supervision (EF-12) : nom=url, séparés par des virgules
    service_health_urls: str = DEFAULT_SERVICE_HEALTH

    # Règles : contrat rule/v1 (validation avant enregistrement, EF-05)
    contracts_dir: Path = Path("/opt/baolsec/contracts")

    # Supervision
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    metrics_host: str = "0.0.0.0"
    metrics_port: int = 9107

    # Mode debug — désactiver impérativement en production.
    # Contrôle l'exposition de /docs, /redoc et /openapi.json.
    debug: bool = False

    @property
    def contracts_path(self) -> Path:
        return self.contracts_dir if self.contracts_dir.exists() else _REPO_CONTRACTS

    @property
    def health_targets(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for item in self.service_health_urls.split(","):
            if "=" in item:
                name, url = item.split("=", 1)
                out[name.strip()] = url.strip()
        return out
