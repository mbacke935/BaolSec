# BaolSec — SIEM distribué

BaolSec collecte les journaux et événements de sécurité, détecte les comportements
suspects via des règles configurables, corrèle les alertes en incidents et offre
une interface de supervision unifiée. La plateforme est distribuée en services
(passerelle d'ingestion, normalisation, détection, construction d'incidents,
couverture, indexation, API, frontend) reliés par un broker NATS JetStream, avec
PostgreSQL (schéma normalisé C4) et OpenSearch.

Deux chemins d'exécution coexistent :

- **Pile complète en conteneurs** — `compose.yaml` à la racine (C18), pour lancer
  toute la plateforme d'une commande.
- **Développement local piloté par le Makefile** — `infrastructure/compose/`, pour
  monter les briques une par une et itérer (c'est le chemin utilisé en dev/tests).

---

## Démarrage rapide — pile complète (Docker Compose)

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

### Services exposés

| Service               | Port local | Description                       |
|-----------------------|------------|-----------------------------------|
| API BaolSec           | 8000       | API REST principale               |
| Frontend (conteneur)  | 3000       | Interface React (build servi)     |
| Grafana               | 3001       | Supervision (admin/changeme)      |
| Prometheus            | 9090       | Métriques brutes                  |
| OpenSearch            | 9200       | Recherche (interne)               |
| OpenSearch Dashboards | 5601       | Exploration des index OpenSearch  |
| NATS (monitoring)     | 8222       | Dashboard NATS                    |

---

## Développement local (Makefile)

Le Makefile monte la pile depuis `infrastructure/compose/` et applique le schéma
normalisé C4 (table `acces` avec rôles en FK) via `make db-up`.

```bash
cp .env.example .env    # renseigner POSTGRES_PASSWORD, SVC_*_PASSWORD, JWT_SECRET, NATS_TOKEN…

make broker-up          # NATS JetStream
make db-up              # PostgreSQL + migrations (schéma normalisé C4) + comptes de service
make incidents-up       # chaîne d'ingestion → normalisation → détection → incidents
```

### API + interface en local

L'API et l'interface se branchent sur **la même base que la pipeline**.

```bash
cd services/baolsec-api

# Compte administrateur de démonstration (propriétaire de la base)
( set -a; . ../../.env; set +a
  POSTGRES_DSN="postgresql://postgres:$POSTGRES_PASSWORD@127.0.0.1:5432/baolsec" \
    uv run --python 3.13 --extra dev python seed_admin.py )

# API (compte de service svc_api, moindre privilège) — http://localhost:8000
( set -a; . ../../.env; set +a
  POSTGRES_DSN="postgresql://svc_api:$SVC_API_PASSWORD@127.0.0.1:5432/baolsec" \
  JWT_SECRET="$JWT_SECRET" \
    uv run --python 3.13 --extra dev uvicorn baolsec_api.main:app --port 8000 )
```

```bash
# Frontend (serveur de dev Vite, proxy /api → localhost:8000) — http://localhost:5173
cd frontend
npm install
npm run dev
```

Connexion de démonstration : `admin@baolsec.local` / `Admin1234!`.

> `make db-up` nécessite au moins `POSTGRES_PASSWORD` dans `.env`. Lancées à la main,
> les commandes ci-dessus sourcent `.env` dans un sous-shell (`set -a; . ../../.env`) ;
> sans cela les secrets sont vides et PostgreSQL refuse la connexion
> (`fe_sendauth: no password supplied`).

---

## Interfaces

Le frontend (React 18 + TypeScript + Vite, design **BaolSec Nexus**) se compose de :

- une **landing publique** (`/`) présentant la plateforme ;
- une **connexion** (`/login`) par identifiants, échangés contre un JWT (jetons
  courts + renouvellement, C3/C5) ;
- un **espace de travail unifié** (`/app`) protégé par authentification, avec une
  barre latérale à sept vues : **Vue générale** (KPI, répartition des alertes,
  alertes récentes), **Événements** (recherche OpenSearch), **Alertes**,
  **Incidents** (+ chronologie), **Sources** (état de couverture), **Détection**
  (règles), **Supervision**. La vue **Utilisateurs** n'apparaît que pour le rôle
  Administrateur.

Les droits sont **vérifiés par l'API à chaque requête** (RBAC côté serveur) : le
masquage d'éléments dans l'interface est un confort, pas un contrôle de sécurité.

---

## Réseaux Docker (pile complète)

- `baolsec-data` : broker, BDD (isolé)
- `baolsec-ingest` : passerelle + agents
- `baolsec-backend` : workers + API
- `baolsec-obs` : Prometheus, Grafana, Fluent Bit

## Volumes persistants

```
nats-data        # JetStream
postgres-data    # PostgreSQL
opensearch-data  # Index OpenSearch
prometheus-data  # Métriques 30j
grafana-data     # Dashboards
```

## Commandes utiles

```bash
# Arrêt propre
docker compose down

# Suppression complète (avec données)
docker compose down -v

# Reconstruire un service
docker compose build incident-builder
docker compose up -d --no-deps incident-builder

# Logs d'un service
docker compose logs -f coverage-worker

# État des healthchecks
docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
```
