# incident-builder — état et suivi des alertes (C15)

Consomme `alerts` (consommateur durable `incident-builder`), crée l'**état de traitement** de chaque alerte dans
`incidents.alert_state` et applique les **commandes de l'API** sur les alertes. Workflow W4 de C3 (étape 1) ;
la corrélation en incidents (C16) et la chronologie (C17) viendront dans le même service.
Document : `docs/conception/C15_Gestion_des_alertes_BaolSec.docx`.

## Fonctionnement

1. Chaque alerte est vérifiée par le contrat `shared/contracts/alert/v1`, puis insérée avec le statut `nouvelle`
   (clé primaire `alert_id`, `ON CONFLICT DO NOTHING`). Une alerte déjà connue est ignorée : l'état de traitement
   n'est jamais écrasé. Le message est acquitté après la validation de la transaction PostgreSQL.
2. Le document complet de l'alerte (règle, événements justificatifs, message) reste dans le flux puis dans
   OpenSearch (C19) et ne change plus ; `alert_state` ne garde que règle, sévérité, date et état de traitement.
3. Les commandes `statut_alerte` et `assigner_alerte` arrivent par `POST /commands` (secret partagé avec l'API),
   dans une transaction : verrou de la ligne, rejeu par `command_id`, décision, écriture de l'état et de la commande.

| Situation | Comportement |
|---|---|
| Même alerte livrée deux fois | Une seule ligne ; métrique `alert_duplicates_total` |
| Message illisible, non conforme à `alert/v1`, sévérité `info` | File de rejet dès la 1re tentative |
| Règle absente de `config.rules` (mode `file` de la détection, ou `make rules-load` oublié) | File de rejet sans nouvelle tentative ; `make rules-load` puis `make dlq-replay` |
| PostgreSQL injoignable | La lecture du flux est suspendue, les alertes attendent dans le broker (7 jours) ; reprise automatique |
| Panne pendant une transaction | Message non acquitté, nouvelle livraison (5 tentatives, puis file de rejet) |
| Service arrêté un moment | Le consommateur durable conserve les alertes ; elles sont enregistrées au redémarrage |
| Commande rejouée (même `command_id`) | Résultat enregistré renvoyé, `replayed = true`, rien n'est réappliqué |
| Deux analystes agissent en même temps | Passage l'un après l'autre : la seconde commande est jugée sur le nouvel état |

### Cycle de vie

`nouvelle` → `en_cours` → `cloturee`. Une alerte `nouvelle` n'a pas d'analyste ; une alerte `en_cours` en a toujours un.

| Commande | De | Vers | Assigné |
|---|---|---|---|
| `statut_alerte` `en_cours` | nouvelle, cloturee | en_cours | l'auteur de la commande |
| `statut_alerte` `nouvelle` | en_cours | nouvelle | retiré |
| `statut_alerte` `cloturee` | nouvelle, en_cours | cloturee | conservé |
| `assigner_alerte` (analyste) | nouvelle, en_cours | en_cours | l'analyste désigné (actif) |
| `assigner_alerte` (`null`) | en_cours | nouvelle | retiré |

Tout le reste est refusé (`transition_interdite`), y compris redemander l'état actuel et assigner une alerte clôturée.
Les refus sont enregistrés dans `incident_commands` comme les acceptations. Ne sont pas enregistrés, faute de ligne
à laquelle les rattacher : alerte inconnue (`cible_introuvable`), auteur inconnu ou désactivé (`donnees_invalides`).

## Interface HTTP interne (port 9000, jamais publié)

| Route | Rôle |
|---|---|
| `GET /health` | 200 si broker et PostgreSQL répondent, sinon 503 |
| `GET /metrics` | Prometheus |
| `POST /commands` | Commande `incident_command/v1` ; en-tête `Authorization: Bearer <INCIDENTS_COMMAND_TOKEN>` |

Réponses de `POST /commands` : **200** avec un `incident_command_result/v1` (`acceptee` ou `refusee`) ; **400** contrat
non respecté ; **401** secret absent ou faux ; **501** commande d'incident (C16) ; **503** PostgreSQL indisponible ;
**500** erreur interne. Pour 500 et 503 rien n'est enregistré : l'API renvoie la même commande avec le même `command_id`.

## Configuration (préfixe `INCIDENTS_`)

| Variable | Défaut | Rôle |
|---|---|---|
| `INCIDENTS_POSTGRES_DSN` | — (obligatoire) | Compte `svc_incidents` |
| `INCIDENTS_COMMAND_TOKEN` | — (obligatoire, 32 caractères au moins) | Secret partagé avec l'API : `openssl rand -hex 32` |
| `INCIDENTS_STREAM`, `INCIDENTS_DURABLE` | `ALERTS`, `incident-builder` | Flux et consommateur |
| `INCIDENTS_FETCH_BATCH` | 50 | Alertes lues par lot |
| `INCIDENTS_DB_POOL_SIZE`, `INCIDENTS_DB_TIMEOUT_S` | 5, 5 | Pool de connexions |
| `INCIDENTS_CONTRACTS_DIR` | `/opt/baolsec/contracts` | Contrats JSON Schema |

Métriques : `baolsec_incidents_alerts_received_total{severity}`, `_alert_duplicates_total`, `_messages_total{outcome}`,
`_alert_seconds`, `_commands_total{command_type,result}`, `_command_replays_total`.

## Commandes

```bash
make incidents-up        # pile complète + détection + service Incidents (INCIDENTS_COMMAND_TOKEN dans .env)
make alerts-list         # alertes récentes ; ARGS="--status nouvelle --severity critique --rule AUTH-001 --page 2"
make alerts-count        # compteurs par statut et par sévérité
make test-incidents      # 63 tests unitaires + 38 tests d'intégration (PostgreSQL de la pile, broker jetable)
```

Les tests d'intégration vident les flux du broker : ils tournent sur un broker jetable (`make test-incidents`),
jamais sur celui de la pile.
