# BaolSec — SIEM distribué

Plateforme de collecte, de normalisation, de détection et de corrélation d'événements de sécurité,
réalisée comme projet de fin d'études. Les documents de conception (C1 à C26) sont dans
`docs/conception/` ; les décisions d'architecture dans `docs/decisions/`.

## Architecture

```text
 Agents Fluent Bit ─HTTPS─┐                                  ┌─ OpenSearch (recherche, 90 j)
 Collecteur Syslog ─HTTPS─┤                                  │
 Équipement Syslog TLS ───┤                                  │
                          ▼                                  │
                 ingestion-gateway ──► NATS JetStream ───────┤
                                          │                  │
            normalization-worker (ECS) ◄──┤                  │
            detection-worker (règles) ◄───┤   indexing-worker┘
            incident-builder (corrélation)◄┤
            coverage-worker (couverture) ◄─┘
                          │
                     PostgreSQL (référentiel, état des alertes et incidents, audit)
                          │
                    baolsec-api (FastAPI) ◄── frontend (React, nginx HTTPS)
```

Chaque service est indépendant et ne communique qu'à travers le broker (flux persistants,
accusés de réception) ou PostgreSQL. Un message qui ne peut pas être traité part dans la file de
rejet (`DLQ`) au lieu d'être perdu (C11).

## Démarrage

Prérequis : Docker et Docker Compose v2, `make`, `openssl` ; [`uv`](https://docs.astral.sh/uv/)
pour `make rules-load` et les commandes de test.

```bash
cp .env.example .env && chmod 600 .env   # puis remplacer chaque <secret>
make gateway-dev                         # certificats de développement (passerelle, interface)
docker compose --env-file .env -f compose.yaml build   # construction des images
make up                                  # toute la pile : migrations, broker, services, interface
make rules-load                          # règles de détection de rules/ dans la base
make admin-create ADMIN_EMAIL=vous@exemple.sn   # premier administrateur (mot de passe affiché une fois)
```

Ouvrir ensuite `https://localhost` (certificat de développement à accepter), se connecter avec le
compte administrateur, puis **Sources › Ajouter une source** : l'assistant déclare la source, génère
son jeton, affiche la configuration de l'agent à installer et confirme la réception du premier
événement.

## Mise à jour d'une installation existante

Après la récupération d'une nouvelle version du code :

```bash
bash scripts/deployment/nettoyer_fichiers_obsoletes.sh --oui   # si l'archive a été extraite par-dessus l'ancienne version
bash scripts/deployment/complete_env.sh   # ajoute à .env les variables apparues depuis sa création
docker compose --env-file .env -f compose.yaml build   # reconstruit les images modifiées
make up                                   # redémarre les services et applique les nouvelles migrations
```

`make up` ne reconstruit pas les images d'un code modifié : la commande `build` est nécessaire à
chaque mise à jour.

Extraire une archive par-dessus un dossier existant ajoute et remplace des fichiers, mais n'en
supprime aucun. Les fichiers retirés du dépôt restent alors sur le disque et peuvent faire échouer
la construction de l'interface (erreurs `tsc` sur `src/api/resources.ts`, `src/hooks/useAuth.ts`…).
Le premier script supprime uniquement ces fichiers, listés un par un ; sans `--oui`, il affiche la
liste sans rien supprimer.

`complete_env.sh` ne modifie aucune valeur déjà présente dans `.env` et en garde une copie
(`.env.sauvegarde`). Il génère les secrets manquants sans les afficher, sauf `POSTGRES_PASSWORD`,
`BROKER_TOKEN` et `SVC_*_PASSWORD`, qu'il signale seulement. Une base déjà créée garde son mot de
passe d'origine : en mettre un nouveau empêcherait d'y accéder. Même précaution pour
`OPENSEARCH_PASSWORD` si OpenSearch a déjà été démarré : remettre la valeur d'origine.

## Services et ports

| Service | Adresse | Rôle |
|---|---|---|
| Interface (nginx) | `https://<hôte>` (443, 80 redirigé) | Interface analyste et administrateur ; `/api/` relayé vers l'API |
| Passerelle d'ingestion | `<hôte>:8443` (HTTPS), `<hôte>:6514` (Syslog TLS) | Réception des journaux des sources |
| API | `127.0.0.1:8000` | API REST (C5) ; contrat dans `docs/api/openapi.yaml` |
| PostgreSQL | `127.0.0.1:5432` | Référentiel et états (C4) |
| OpenSearch | `127.0.0.1:9200` | Événements, alertes et incidents indexés |
| NATS | `127.0.0.1:4222` | Broker (ADR 0002) |
| Prometheus | `127.0.0.1:9090` | Métriques et règles d'alerte (`docker/prometheus/alerts.yml`) |
| Grafana | `127.0.0.1:3001` | Tableau « BaolSec — Supervision de la plateforme » (admin / `GRAFANA_PASSWORD`) |

Seuls l'interface et la passerelle sont exposés sur le réseau ; les autres ports sont liés à
`127.0.0.1` (accès d'exploitation uniquement).

## Rôles

| Rôle | Écrans |
|---|---|
| Analyste | Tableau de bord, alertes, incidents (prise en charge, attribution, commentaires, clôture), événements, recherche avancée, couverture, supervision ; sources et règles en lecture |
| Administrateur | Vue d'ensemble, sources et identifiants d'ingestion, règles (YAML versionné), utilisateurs, paramètres de corrélation, journal d'audit, file de rejet ; alertes et incidents en lecture |

Les droits sont vérifiés par l'API à chaque requête ; l'interface ne fait que les refléter.

## Configuration (.env)

`.env.example` liste toutes les variables avec leur rôle. Les plus importantes :

| Variable | Rôle |
|---|---|
| `POSTGRES_PASSWORD`, `SVC_*_PASSWORD` | Propriétaire de la base et un compte par service, droits minimaux |
| `BROKER_TOKEN` | Authentification au broker |
| `JWT_SECRET` | Signature des jetons de session (32 caractères au moins) |
| `INCIDENTS_COMMAND_TOKEN` | Commandes de l'API vers le service Incidents |
| `OPENSEARCH_PASSWORD` | Compte `admin` d'OpenSearch |
| `GATEWAY_SOURCE_REGISTRY=postgres` | Les sources déclarées dans l'interface sont reconnues par la passerelle (`file` : tests de C6) |
| `EVENTS_RETENTION_DAYS`, `SNAPSHOT_KEEP`, `BACKUP_RETENTION_DAYS` | Conservation des index, instantanés et sauvegardes (ES-09) |

## Exploitation

```bash
make help                    # toutes les commandes
docker compose ps            # état et santé des services
make journaux                # journaux des services, lisibles (heure, service, niveau en français)
make journaux ARGS="--suivre --service incidents --niveau attention --depuis 2h"
docker compose logs -f incident-builder   # journaux bruts (JSON)
make dlq-list                # file de rejet par service et par motif
make test                    # tests unitaires de chaque service
make test-db test-incidents  # tests d'intégration (PostgreSQL, broker jetable)
```

Sauvegarde et restauration : `docs/deployment/sauvegarde_restauration.md`.
Installation des agents : `agents/README.md`.

## Structure du dépôt

```text
baolsec/
├── compose.yaml                 # pile complète : infrastructure/compose/compose.yaml + supervision
├── agents/                      # configurations Fluent Bit (Linux, Windows, application web, collecteur Syslog)
├── docker/                      # Prometheus (cibles, règles d'alerte) et Grafana (tableau, source)
├── docs/                        # conception, décisions, API (openapi.yaml), déploiement
├── frontend/                    # interface React + TypeScript (Vite), servie par nginx
├── infrastructure/
│   ├── backup/                  # sauvegarde PostgreSQL planifiée
│   ├── broker/                  # topologie JetStream, file de rejet
│   ├── compose/                 # services de la plateforme
│   ├── database/                # migrations Alembic (SQL dans sql/), comptes de service
│   └── opensearch/              # modèles d'index
├── rules/                       # règles de détection (contrat rule/v1)
├── scripts/                     # développement et tests
├── services/                    # un dossier par service (voir docs/architecture/structure-du-depot.md)
├── shared/                      # contrats JSON Schema et bibliothèque Python commune
└── tests/                       # tests d'intégration, de bout en bout et de performance
```
