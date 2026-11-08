# Passerelle d'ingestion (service 1)

Référence : C3, fiche 4.3 et workflow W1 ; contrat `raw_event/v1` (C5) ; broker : ADR 0002.

Reçoit les événements des sources, vérifie leur origine et leur validité, puis les publie
durablement dans le flux `raw-events`. Elle ne parse pas le contenu : c'est la normalisation qui le fait.

## Entrées

| Canal | Port | Authentification | Format |
|---|---|---|---|
| HTTPS `POST /ingest` | 8443 | `Authorization: Bearer <jeton de la source>` | tableau JSON d'enregistrements (sortie `http` de Fluent Bit, `format json`) |
| Syslog TCP/TLS | 6514 | certificat client signé par l'AC des sources, empreinte enregistrée | RFC 5425 (comptage d'octets) ; fin de ligne aussi acceptée |

Pour chaque enregistrement HTTPS :
- `date` → `agent.read_at` (ISO 8601 ou secondes epoch ; omis s'il est illisible) ;
- `log` (texte) → `payload_format: text` ;
- sinon l'enregistrement entier (journald, journal Windows…) → `payload_format: json`.

`event_id` : `win:<Computer>:<Channel>:<EventRecordID>` pour Windows, sinon SHA-256 de (source, format, contenu).

## Réponses HTTPS

| Code | Cas | Effet chez Fluent Bit |
|---|---|---|
| 202 | Chaque événement a un résultat durable : publié dans `raw-events`, ou conservé dans la file de rejet (`dlq`) s'il est invalide ; `rejected` liste ces derniers | retire le lot du tampon |
| 400 | Corps qui n'est pas un tableau JSON lisible | abandonne le lot |
| 401 | Jeton absent, inconnu, expiré, révoqué, ou source désactivée | abandonne le lot |
| 413 | Corps > 8 Mio ou plus de 50 000 événements | abandonne le lot. Un morceau Fluent Bit fait au plus ~2 Mo : ces limites ne sont pas atteintes par un agent normal |
| 429 | Limite de débit de la source dépassée (`Retry-After`) | garde le lot et réessaie |
| 503 | Broker ou référentiel des sources indisponible (`Retry-After`) | garde le lot et réessaie |

Le comportement de Fluent Bit (abandon sur 4xx sauf 408 et 429, nouvel essai sinon) vient de son code
source (`plugins/out_http/http.c`). Les erreurs sont au format RFC 9457 (`application/problem+json`).

Il n'y a pas d'accusé événement par événement : c'est tout le lot qui est accepté (202) ou renvoyé (503), avec les mêmes identifiants, et le broker écarte ce qui était déjà stocké.

Syslog n'a pas d'accusé applicatif : si le broker ne répond pas, la passerelle cesse de lire la
connexion et réessaie ; TCP ralentit alors l'émetteur. Cette entrée sert aux équipements qui émettent directement en Syslog TLS ; pfSense passe par le collecteur Fluent Bit (C7).

## Référentiel des sources

Lecture seule des tables `config.sources` et `config.source_credentials` (C4), rafraîchie toutes
les 30 s. Si la lecture échoue, le cache précédent reste utilisé 5 min au plus, puis tout est refusé
(503) : une révocation ne peut pas être ignorée indéfiniment.

`GATEWAY_SOURCE_REGISTRY=file` lit les mêmes informations dans un fichier JSON : réservé aux tests et
au développement avant le déploiement de PostgreSQL.

Nouveau jeton (en attendant l'écran d'administration) : `python -m gateway.auth`.

## Variables d'environnement

| Variable | Défaut | Rôle |
|---|---|---|
| `BROKER_URL`, `BROKER_TOKEN` | `nats://broker:4222`, — | broker |
| `GATEWAY_SOURCE_REGISTRY` | `postgres` | `postgres` ou `file` |
| `GATEWAY_POSTGRES_DSN` | — | compte en lecture seule sur le schéma `config` |
| `GATEWAY_SOURCES_FILE` | — | fichier de sources (mode `file`) |
| `GATEWAY_SOURCES_REFRESH_S` / `GATEWAY_SOURCES_MAX_STALE_S` | 30 / 300 | cache des sources |
| `GATEWAY_TLS_CERT`, `GATEWAY_TLS_KEY` | `/run/secrets/gateway.*` | certificat serveur (HTTPS et Syslog) |
| `GATEWAY_SYSLOG_CLIENT_CA` | `/run/secrets/sources-ca.crt` | AC des certificats clients Syslog |
| `GATEWAY_MAX_BODY_BYTES` / `GATEWAY_MAX_EVENTS_PER_BATCH` | 8 Mio / 50 000 | taille des lots |
| `GATEWAY_MAX_EVENT_CHARS` | 65 536 | taille d'un événement (limite du contrat) |
| `GATEWAY_RATE_LIMIT_EVENTS_PER_S` / `GATEWAY_RATE_LIMIT_BURST` | 500 / 5 000 | limite par source et par instance ; un lot plus grand que la rafale est accepté s'il reste des jetons, puis la source attend (429) que la dette soit remboursée |

## Supervision

Port interne 9000 : `/health` (broker connecté, cache des sources utilisable) et `/metrics`
(`baolsec_gateway_events_total`, `_rejections_total`, `_publish_seconds`, `_broker_errors_total`,
`_sources_cache_age_seconds`, `_syslog_connections`).

## Tests

```bash
make test-gateway       # unitaires (34) + intégration (12, pile démarrée par make gateway-up)
```
Le test du référentiel PostgreSQL s'exécute si `TEST_POSTGRES_DSN` est défini.
