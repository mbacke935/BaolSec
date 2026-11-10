# Broker — NATS JetStream

Décision et comparaison : `docs/decisions/0002-broker.md`.

| Fichier | Rôle |
|---|---|
| `nats-server.conf` | Serveur : JetStream, stockage `/data`, `sync_interval: 1s`, jeton `BROKER_TOKEN` |
| `topology.json` | Flux, rétention et consommateurs durables (source de vérité) |
| `init_broker.py` | Crée ou met à jour la topologie et le bucket KV ; peut être relancé |
| `dlq_admin.py` | Exploitation de la file de rejet : liste, détail, reprise, purge, métriques (C11) |
| `Dockerfile` | Image des outils : conteneur ponctuel `broker-init`, service `dlq-monitor` |
| `../state-store/detection-state.json` | Bucket KV de l'état des règles |

## Démarrer

```bash
cp .env.example .env          # puis renseigner BROKER_TOKEN (ex. : openssl rand -hex 32)
make broker-up                # broker + application de la topologie
make test-broker              # tests d'intégration (persistance, relecture, partage, déduplication, dlq)
```

## Flux

| Flux | Sujet | Rétention | Consommateurs durables |
|---|---|---|---|
| `RAW_EVENTS` | `raw-events` | jusqu'à l'acquittement par ses consommateurs (7 jours au plus) ; 20 Gio, refus des nouveaux messages si plein | `normalization`, `coverage-raw` |
| `NORMALIZED_EVENTS` | `normalized-events` | 7 jours ou 20 Gio | `detection`, `indexing-events`, `coverage-normalized` |
| `ALERTS` | `alerts` | 7 jours ou 2 Gio | `incident-builder`, `indexing-alerts` |
| `DLQ` | `dlq.<service>` | 30 jours ou 2 Gio (refus des nouveaux messages si plein) | — (lecture par l'API, `GET /dlq`) |

Consommateurs : pull, acquittement explicite, délais de relivraison 5 s, 15 s, 30 s, 60 s.
Le broker relivre sans limite (`max_deliver` = -1) ; les 5 tentatives sont comptées par
`baolsec_common.messaging.process`. Le service qui échoue à la 5e tentative publie un `dlq_message/v1`
puis acquitte l'original. Un contenu illisible ou non conforme part en file de rejet dès la 1re tentative.
Un message dont la 5e tentative n'a pas abouti (service arrêté, file de rejet injoignable) revient
et part en file de rejet à la livraison suivante.

## File de rejet (C11)

```bash
make dlq-list                                     # nombre de messages par service et par motif
make dlq-list ARGS="-v --service normalization-worker --since 2026-11-08T00:00:00Z"
make dlq-show SEQ=42                              # motif, tentatives, contenu d'origine
make dlq-replay ARGS="--reason parse_error --dry-run"   # ce qui serait repris
make dlq-replay ARGS="--reason parse_error"             # reprise, puis retrait de la file
make dlq-purge ARGS="--service normalization-worker --reason validation_error --yes"
make dlq-monitor-up                               # métriques Prometheus sur dlq-monitor:9102
```

Procédure :

1. `make dlq-list` : repérer le service et le motif qui augmentent (alerte sur `baolsec_dlq_messages`).
2. `make dlq-show SEQ=…` sur quelques messages : contenu d'origine et motif.
3. Corriger la cause : parseur ou correspondance ECS (`parse_error`, `mapping_error`), contrat (`validation_error`),
   service ou broker indisponible (`processing_error`, rien à corriger dans le code).
4. Déployer la correction, puis `make dlq-replay ARGS="--reason … --dry-run"`, puis sans `--dry-run`.
5. Les messages qui échouent encore retournent en file de rejet avec leur identifiant d'origine.
6. Un message sans intérêt (format non pris en charge, test) est supprimé avec `make dlq-purge … --yes`.

Reprise : le contenu d'origine est republié dans son flux avec le Msg-Id `replay:<séquence>:<identifiant>` ;
l'`event_id` (ou l'`alert_id`) ne change pas, donc les services en aval restent idempotents. La republication
est confirmée avant la suppression dans la file : un arrêt entre les deux laisse le message dans la file, sans perte.
Un événement refusé par la passerelle (`original_stream` = `ingest`) n'est pas repris : la source le renvoie.
Une reprise vers `normalized-events` ou `alerts` est reçue par tous les consommateurs du flux ; ils écartent
ce qu'ils ont déjà traité (`_id` = `event_id` dans OpenSearch, `alert_id` déterministe).

La file conserve les messages 30 jours (2 Gio au plus). Pleine, elle refuse les nouveaux rejets : le service
n'acquitte pas le message en échec, qui reste dans son flux d'origine. Rien n'est supprimé sans action de l'exploitant.

## Règles

- Modifier `topology.json`, puis relancer `make broker-init`. Le stockage, la rétention et le nom d'un flux ne sont pas modifiables après création : `init_broker.py` le signale. En développement, `make broker-reset` supprime les données du broker et recrée les flux ; en production, un tel changement passe par un nouveau flux et une migration documentée.
- La durée de conservation de `normalized-events` et `alerts` est la première limite atteinte (7 jours ou taille) : voir la décision 0002.
- Le port 4222 n'est publié que sur `127.0.0.1` (développement). Les services joignent le broker par le réseau Docker interne.
- Supervision : `http://broker:8222/healthz` et `/jsz` (réseau interne).
