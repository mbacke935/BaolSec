# BaolSec — SIEM distribué

Plateforme SIEM (Security Information and Event Management) distribuée,
développée dans le cadre d'un projet de fin d'études (L3 Informatique).

## Architecture

```
agents (Fluent Bit)
    ↓ HTTPS/Syslog TLS
ingestion-gateway
    ↓ NATS JetStream
normalization-worker → detection-worker → incident-builder
                                        ↓
                              indexing-worker → OpenSearch
                                        ↓
                              coverage-worker → PostgreSQL
                                        ↓
                                   baolsec-api
                                        ↓
                                     frontend (React)
```

## Démarrage rapide

```bash
# 1. Copier et remplir les secrets
cp .env.example .env
# Éditer .env : remplacer tous les "changeme_*"

# 2. Démarrer toute la plateforme
docker compose up -d

# 3. Vérifier les services
docker compose ps
docker compose logs -f
```

## Services exposés

| Service               | Port local | Description                        |
|-----------------------|------------|------------------------------------|
| API BaolSec           | 8000       | API REST principale                |
| Frontend              | 3000       | Interface React (analyste + admin) |
| Grafana               | 3001       | Supervision (admin / voir .env)    |
| Prometheus            | 9090       | Métriques brutes                   |
| OpenSearch            | 9200       | Moteur de recherche (interne)      |
| OpenSearch Dashboards | 5601       | Interface OpenSearch               |
| NATS monitoring       | 8222       | Dashboard broker                   |
| Syslog UDP/TCP        | 5514       | Réception logs équipements         |
| HTTP push             | 8080       | Réception logs HTTP                |

## Versions des images

| Image                           | Version  |
|---------------------------------|----------|
| `nats`                          | 2.15     |
| `postgres`                      | 17       |
| `opensearchproject/opensearch`  | 2.18.0   |
| `opensearchproject/opensearch-dashboards` | 2.18.0 |
| `fluent/fluent-bit`             | 3.2      |
| `prom/prometheus`               | v3.2.1   |
| `grafana/grafana`               | 11.5.2   |

## Réseaux Docker

| Réseau            | Rôle                                      |
|-------------------|-------------------------------------------|
| `baolsec-data`    | Broker, PostgreSQL, OpenSearch (isolé)    |
| `baolsec-ingest`  | Passerelle + agents                       |
| `baolsec-backend` | Workers + API                             |
| `baolsec-obs`     | Prometheus, Grafana, Fluent Bit           |

## Volumes persistants

```
nats-data        # JetStream (broker)
postgres-data    # PostgreSQL
opensearch-data  # Index OpenSearch
prometheus-data  # Métriques 30 jours
grafana-data     # Dashboards Grafana
```

## Commandes utiles

```bash
# Arrêt propre
docker compose down

# Suppression complète (avec données)
docker compose down -v

# Reconstruire un service spécifique
docker compose build coverage-worker
docker compose up -d --no-deps coverage-worker

# Logs d'un service
docker compose logs -f api
docker compose logs -f incident-builder

# État des healthchecks
docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"

# Redémarrer un service sans rebuild
docker compose restart coverage-worker
```

## Variables d'environnement requises (.env)

| Variable                | Description                              |
|-------------------------|------------------------------------------|
| `NATS_TOKEN`            | Jeton d'authentification NATS            |
| `POSTGRES_PASSWORD`     | Mot de passe PostgreSQL (compte baolsec) |
| `SVC_API_PASSWORD`      | Mot de passe compte svc_api              |
| `SVC_PASSERELLE_PASSWORD` | Mot de passe compte svc_passerelle     |
| `SVC_NORMALISATION_PASSWORD` | Mot de passe compte svc_normalisation |
| `SVC_DETECTION_PASSWORD` | Mot de passe compte svc_detection      |
| `SVC_INCIDENTS_PASSWORD` | Mot de passe compte svc_incidents      |
| `SVC_COUVERTURE_PASSWORD` | Mot de passe compte svc_couverture    |
| `OPENSEARCH_PASSWORD`   | Mot de passe admin OpenSearch            |
| `JWT_SECRET`            | Secret JWT pour l'API (min. 32 chars)    |
| `COMMAND_TOKEN`         | Token commandes incidents (min. 32 chars)|
| `GRAFANA_PASSWORD`      | Mot de passe admin Grafana               |

## Structure du dépôt

```
baolsec/
├── compose.yaml                  # Stack complète (C18)
├── docker/                       # Configs Fluent Bit, Prometheus, Grafana
├── services/
│   ├── baolsec-api/              # API REST FastAPI
│   ├── frontend/                 # Interface React + TypeScript
│   ├── coverage-worker/          # Suivi couverture des sources
│   ├── incident-builder/         # Gestion des incidents
│   ├── indexing-worker/          # Indexation OpenSearch
│   ├── detection-worker/         # Moteur de détection
│   ├── normalization-worker/     # Normalisation des événements
│   └── ingestion-gateway/        # Passerelle d'ingestion
├── infrastructure/
│   └── compose/                  # Compose de développement (sans obs)
└── migrations/                   # Migrations Alembic (PostgreSQL)
```
