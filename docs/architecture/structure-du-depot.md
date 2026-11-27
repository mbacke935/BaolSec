# Structure du dépôt BaolSec

Ce document fixe l'organisation du dépôt Git de BaolSec. Il traduit l'architecture décrite dans **C3 (Architecture HLD, LLD et workflows)** et le modèle de données de **C4** en dossiers, et sert de référence pendant toute la réalisation. Toute création, suppression ou renommage de dossier de premier ou deuxième niveau doit être reporté ici.

Le dépôt est un **monorepo** : un seul dépôt, mais chaque service a son propre code, ses dépendances, ses tests et son image Docker. L'architecture est distribuée par ses services, pas par le nombre de dépôts.

BaolSec compte **huit composants applicatifs** : sept services backend dans `services/` et l'interface web dans `frontend/`, qui ne communique qu'avec l'API. La numérotation 1 à 8 du C3 est conservée.

---

## 1. Invariants d'architecture

Ces règles s'appliquent à tout le code. Une revue qui constate leur violation bloque la fusion.

| N° | Règle | Référence |
|---|---|---|
| I-1 | Un service = une responsabilité. Chaque service démarre, s'arrête, se teste et se réplique seul. | C3 2.1 |
| I-2 | Les échanges entre services passent par le broker, avec des contrats de messages versionnés (`shared/contracts`). Deux exceptions seulement : (a) la **lecture seule** des référentiels autorisés des schémas `config` et `acces` ; (b) les **commandes API → Incidents**, par un appel HTTP interne authentifié, validé et idempotent grâce au `command_id` (contrat précis fixé en C5). | C3 2.1, 2.5 |
| I-3 | Chaque service est seul à écrire dans son schéma PostgreSQL. Les autres passent par des messages ou par une interface autorisée, jamais par une écriture directe. | C3 2.5, C4 2.2 |
| I-4 | `indexing-worker` est le seul service qui écrit dans OpenSearch. | C3 2.5, C4 2.1 |
| I-5 | Les incidents ne sont jamais indexés dans OpenSearch. PostgreSQL (schéma `incidents`) est leur source de vérité ; l'API les lit là. | C4 2.1 |
| I-6 | L'API ne reçoit aucun événement de sécurité : elle sert la consultation et la gestion. | C3 2.1 |
| I-7 | Livraison au moins une fois : chaque consommateur est idempotent (event_id, alert_id, command_id). | C3 3.1, C4 7 |
| I-8 | On n'acquitte un message qu'après la persistance de ses effets. | C3 3.1 |
| I-9 | Le broker et le stockage d'état ne sont pas nommés dans le code métier ni dans les noms de dossiers : le code utilise des interfaces (`messaging`, `state`), les adaptateurs concrets sont isolés. Le choix est confirmé en C8 (broker) et C14 (tests du stockage d'état, flux 3). | C3 2.6 |
| I-10 | Aucun secret dans le dépôt. Seul `.env.example` est versionné. | C2 ES-08 |

---

## 2. Arborescence

```text
baolsec/
├── services/
│   ├── ingestion-gateway/        # Service 1 — Passerelle d'ingestion
│   ├── normalization-worker/     # Service 2 — Normalisation
│   ├── detection-worker/         # Service 3 — Détection
│   ├── incident-builder/         # Service 4 — Incidents
│   ├── indexing-worker/          # Service 5 — Indexation
│   ├── coverage-worker/          # Service 6 — Couverture
│   └── api/                      # Service 7 — API REST
├── frontend/                     # Composant 8 — Interface web
├── agents/                       # Configurations de collecte côté sources
├── shared/                       # Contrats, schéma commun, utilitaires techniques
├── infrastructure/               # Broker, bases, supervision, déploiement
├── tests/                        # Tests qui traversent plusieurs services
├── test-data/                    # Jeux de données et scénarios (sans gros fichiers)
├── scripts/                      # Outils de développement et d'exploitation
├── docs/                         # Conception C1–C8, décisions, guides
├── .env.example
├── .gitignore
├── Makefile
├── README.md
└── LICENSE
```

Chaque service Python suit le même gabarit :

```text
services/<service>/
├── src/<paquet>/
│   ├── ...                       # modules décrits en section 3
│   ├── health.py                 # /health et /metrics (C3 4.1)
│   ├── config.py                 # variables d'environnement validées au démarrage
│   └── main.py
├── tests/                        # tests unitaires du service
├── Dockerfile                    # image non root, versions fixées (C2 ES-10)
├── pyproject.toml
└── README.md                     # rôle, entrées, sorties, variables
```

---

## 3. Services

### 3.1 `services/ingestion-gateway/` — Passerelle d'ingestion
Référence : C3 4.3 (fiche), W1 (3.2), C4 config.sources et source_credentials.

```text
src/gateway/
├── http/             # POST /ingest (HTTPS, lots JSON)
├── syslog/           # Syslog TCP/TLS :6514 (RFC 5424 / 5425)
├── auth/             # jetons hachés, certificats clients, révocation
├── sources_cache/    # cache des sources actives, rafraîchi depuis PostgreSQL (lecture seule)
├── rate_limit/       # limitation de débit par source
├── validation/       # format, taille, nombre d'événements par lot
├── event_id/         # identifiant natif ou empreinte SHA-256
└── publisher/        # publication raw-events (Msg-Id = event_id), attente de PubAck
```
Écrit : flux `raw-events`. Ne lit que `config` dans PostgreSQL.

### 3.2 `services/normalization-worker/` — Normalisation
Référence : C3 4.4, W2 (3.3), C3 4.2 (enveloppes).

```text
src/normalizer/
├── consumer/         # consommateur durable raw-events
├── parsers/          # linux/, windows/, firewall/, http/
├── mapping/          # conversion vers le schéma commun retenu en C5
├── enrichment/       # métadonnées de source, classification IP
├── publisher/        # normalized-events (même event_id)
└── dlq/              # publication en file de rejet après 5 tentatives
```
Écrit : flux `normalized-events`, `dlq`. N'écrit dans aucune base.

### 3.3 `services/detection-worker/` — Détection
Référence : C3 4.5, W3 (3.4), C4 6 (état de détection).

```text
src/detection/
├── consumer/         # consommateur durable normalized-events
├── rules/            # chargement des règles YAML (lecture config.rules / rule_versions)
├── engine/           # règles simples et règles à fenêtre
├── state/            # interface StateStore + adaptateur (KV ou Redis, cf. I-9)
├── pending/          # relais des alertes en attente (démarrage + chaque minute)
└── publisher/        # alerts (Msg-Id = alert_id)
```
Écrit : flux `alerts`, état de détection. Fenêtres sur l'horodatage d'origine, tolérance de retard de 2 min.

### 3.4 `services/incident-builder/` — Incidents
Référence : C3 4.6, W4 (3.5), règles de corrélation (3.8), C4 schéma `incidents`.

```text
src/incidents/
├── consumer/         # consommateur durable alerts
├── alert_state/      # création et mise à jour de l'état de traitement des alertes
├── correlation/      # règles R1–R4 et exclusions E1–E5 (code), choix du candidat, verrous par entité
├── timeline/         # chronologie et justification enregistrée
├── commands/         # point d'entrée interne pour les commandes de l'API + traitement idempotent
└── repositories/     # accès au schéma incidents (seul écrivain)
```
Écrit : schéma PostgreSQL `incidents`. Lit : `config.rules`, `config.settings`, `acces.users`. Exécute les commandes ; l'API ne touche jamais ces tables en écriture.

Ne pas confondre deux sortes de règles :
- les **règles de détection** sont des données (`config.rules`, `config.rule_versions`), gérées par l'Administrateur et appliquées par `detection-worker` ;
- les **règles de corrélation** R1–R4 et E1–E5 sont du code, dans `correlation/` ; seuls leurs paramètres (fenêtre de 30 min, durée maximale de 24 h, valeurs génériques ignorées, enchaînements d'activités) sont des données, dans `config.settings`.

### 3.5 `services/indexing-worker/` — Indexation
Référence : C3 4.7, W5 (3.6), C4 6.

```text
src/indexer/
├── consumers/        # normalized-events et alerts (deux consommateurs)
├── batching/         # lots (taille ou délai)
├── bulk/             # _bulk avec _id stable, analyse du résultat élément par élément
└── errors/           # classement des échecs : temporaire → nouvelle livraison ; permanent → dlq
```
Écrit : index `events-AAAA.MM.JJ` et `alerts-AAAA.MM`. Seul écrivain OpenSearch (I-4). Erreurs : OpenSearch indisponible → aucun acquittement, nouvelle livraison avec délai croissant ; document invalide → file de rejet ; un lot n'est jamais acquitté en bloc (C3 W5).

### 3.6 `services/coverage-worker/` — Couverture
Référence : C3 4.8, W6 (3.7), C4 schéma `couverture` et section 7.

```text
src/coverage/
├── consumers/        # raw-events et normalized-events (deux consommateurs)
├── counters/         # comptage par lots de 10 s, coverage_batches (déduplication par séquence)
├── evaluation/       # calcul des états chaque minute (ACTIVE, SILENCIEUSE, FLUX_INCOMPLET…)
├── affected_rules/   # règles privées de données, à partir de config.rule_requirements
└── repositories/     # accès au schéma couverture (seul écrivain)
```
Écrit : schéma PostgreSQL `couverture`. Le service compare réception et traitement ; il n'évalue aucune règle de détection.

- **Déduplication** : la clé est le couple (consommateur, numéro de séquence du message dans le broker), enregistré par lot dans `coverage_batches` (C4 section 7).
- **Événements en retard** : la couverture compte selon l'heure de réception (`received_at`), pas l'heure d'origine ; un retard ne fausse donc pas l'état d'une source.

### 3.7 `services/baolsec-api/` — API REST
Référence : C3 4.9, matrice des rôles (C2 3), C4 schémas `acces` et `config`, contrat C5 (`docs/api/openapi.yaml`).

```text
src/baolsec_api/
├── main.py           # application FastAPI, middlewares (sécurité, audit, CORS), /health, /metrics
├── config.py         # variables d'environnement (Pydantic Settings)
├── auth.py           # JWT d'accès et de renouvellement, Argon2, verrouillage après échecs (ES-01)
├── dependencies.py   # contrôle du rôle sur chaque route (ES-03), pagination
├── middleware/       # security.py (débit, taille, en-têtes, ES-05) ; audit.py (mutations, ES-07)
├── commandclient.py  # commandes incident_command/v1 vers le service Incidents
├── broker.py         # lecture de la file de rejet et des flux JetStream
├── rulecheck.py      # validation des règles YAML (contrat rule/v1)
└── routers/          # auth, users, sources, rules, admin (settings, roles, audit, dlq), alerts,
                      # incidents, coverage, search et events, system (supervision)
seed_admin.py         # création du premier compte administrateur (make admin-create)
```

### 3.8 `frontend/` — Interface web
Référence : C3 4.10, maquette interactive v3 (design Nexus).

```text
frontend/
├── src/
│   ├── app/                  # routage, garde par rôle
│   ├── features/
│   │   ├── auth/  dashboard/  alerts/  incidents/  events/
│   │   ├── sources/          # sources et couverture
│   │   ├── rules/  monitoring/
│   │   └── users/  audit/  settings/   # Administrateur uniquement
│   ├── components/  services/  stores/  types/
│   └── main.tsx
├── tests/
├── package.json
└── vite.config.ts
```
Ne parle qu'à l'API.

---

## 4. Dossiers transversaux

### 4.1 `agents/` — Collecte côté sources
Référence : C3 W1, C1 section 4 ; validé source par source en C7.

```text
agents/
├── fluent-bit/
│   ├── linux/        # auth.log, journald, journaux iptables du noyau ; tampon disque ; HTTPS vers la passerelle
│   ├── windows/      # journal Sécurité (winevtlog) ; tampon disque
│   └── webapp/       # journaux HTTP et applicatifs écrits par le serveur (application web, backend mobile)
└── syslog-relay/     # relais à file persistante pour pfSense, puis Syslog TLS vers la passerelle
```
Uniquement des configurations et leur documentation : pas d'agent développé par l'équipe.

- **Backend mobile** : Fluent Bit lit les journaux que le serveur de l'application écrit ; il ne collecte jamais rien sur le téléphone.
- **iptables** : les journaux passent par le système Linux (cible LOG du noyau, journald ou kern.log) ; l'agent Fluent Bit Linux les collecte avec son tampon disque.
- **pfSense** : aucun agent n'est installé sur l'équipement ; il envoie ses journaux en Syslog au relais, qui les conserve sur disque puis les transmet en TLS à la passerelle. `syslog-relay/README.md` décrit la configuration.

### 4.2 `shared/`
```text
shared/
├── contracts/            # contrats versionnés (JSON Schema + modèles Pydantic)
│   ├── raw_event/v1/
│   ├── normalized_event/v1/
│   ├── alert/v1/
│   ├── dlq_message/v1/
│   └── incident_command/v1/
├── schema/               # le schéma commun retenu en C5 (ECS ou OCSF) et nos correspondances
└── python-common/
    ├── logging/          # journaux JSON
    ├── metrics/          # Prometheus
    ├── messaging/        # interface publication / consommation (cf. I-9)
    └── config/
```
`shared/` ne contient aucune logique métier : chaque service garde la maîtrise de son domaine. Le dossier `schema/` ne contiendra qu'un seul schéma, celui choisi en C5.

### 4.3 `infrastructure/`
```text
infrastructure/
├── compose/              # compose.yaml, compose.dev.yaml, compose.test.yaml
├── broker/               # définition des flux, consommateurs durables, rétention, dlq
├── state-store/          # configuration de l'état de détection (bucket KV, ou Redis en repli)
├── postgresql/
│   ├── roles/            # comptes svc_* et droits par schéma (C4 2.2)
│   └── migrations/
│       ├── acces/  config/  incidents/  couverture/
├── opensearch/           # modèles d'index, politique de rétention, dépôt de snapshots
├── prometheus/           # prometheus.yml, règles d'alerte techniques
├── grafana/              # tableaux de bord et provisionnement
├── tls/                  # scripts de génération des certificats de développement (pas de clés)
└── backup/               # pg_dump quotidien, snapshots OpenSearch, restauration (C4 8)
```

### 4.4 `tests/` et `test-data/`
Référence : C2 section 8.

```text
tests/
├── integration/          # échanges entre deux services via le broker
├── end_to_end/           # source → alerte → incident → API
├── resilience/           # scénarios S1 à S5
├── detection/            # scénarios D1 à D6 (corrélation R1–R4, E1–E5)
├── performance/          # débit, latences p95, ressources (ENF-02)
└── security/             # authentification, RBAC, TLS, injections (ES-01 à ES-10)

test-data/
├── manifest.yaml         # jeux publics : source, version ou commit, empreinte
├── download/             # scripts de téléchargement (OTRF, EVTX-ATTACK-SAMPLES, Loghub)
├── samples/              # petits extraits versionnés pour les tests unitaires
└── scenarios/            # procédures Hydra et Atomic Red Team, en laboratoire isolé
```
Les **tests unitaires** restent dans chaque service (`services/<service>/tests/`, `frontend/tests/`) ; `tests/` ne contient que les tests qui traversent plusieurs services. Les jeux publics volumineux ne sont pas versionnés dans Git ; `manifest.yaml` garantit la reproductibilité.

### 4.5 `docs/` et `scripts/`
```text
docs/
├── conception/           # C1 à C15
├── architecture/         # ce document, sources des diagrammes (.puml, .dot)
├── decisions/            # fiches de décision : broker, état, schéma commun…
├── api/                  # contrat OpenAPI
├── deployment/           # installation et exploitation
└── guides/               # guide utilisateur par rôle

scripts/
├── development/  database/  testing/  deployment/
```

---

## 5. Correspondance avec C3 et C4

| Dossier | Service (C3) | Fiche LLD | Workflow | Écrit dans | Lit |
|---|---|---|---|---|---|
| `services/ingestion-gateway` | 1 · Passerelle | 4.3 | W1 | raw-events | config |
| `services/normalization-worker` | 2 · Normalisation | 4.4 | W2 | normalized-events, dlq | config |
| `services/detection-worker` | 3 · Détection | 4.5 | W3 | alerts, état de détection | config.rules |
| `services/incident-builder` | 4 · Incidents | 4.6 | W4, 3.8 | schéma `incidents` | config.rules, config.settings, acces.users |
| `services/indexing-worker` | 5 · Indexation | 4.7 | W5 | OpenSearch | — |
| `services/coverage-worker` | 6 · Couverture | 4.8 | W6 | schéma `couverture` | config.sources, config.rules |
| `services/baolsec-api` | 7 · API REST | 4.9 | — | schémas `acces` (dont `audit_log`), `config` | OpenSearch, schémas `incidents` et `couverture`, référentiels autorisés |
| `frontend` | 8 · Interface web | 4.10 | — | — | API uniquement |
| `agents` | Agents de collecte | 2.3 | W1 | — (envoi à la passerelle) | journaux locaux |

---

## 6. Ordre de mise en place

1. **C5** : choisir ECS ou OCSF, écrire les contrats `shared/contracts/*/v1`.
2. Créer la racine, le gabarit des services et `infrastructure/compose`.
3. PostgreSQL : rôles et migrations des quatre schémas.
4. Broker : flux, consommateurs, file de rejet ; interfaces `messaging` et `state`.
5. Agents Fluent Bit et passerelle (W1), puis normalisation (W2).
6. Détection avec état et alertes en attente (W3).
7. Incidents et règles de corrélation (W4, 3.8), indexation (W5), couverture (W6).
8. API, puis interface web.
9. Supervision, sauvegardes, tests globaux (S1–S5, D1–D6).

Le plan de migration depuis le code existant (dossiers conservés, déplacés ou créés) sera établi après examen du dépôt GitHub actuel.
