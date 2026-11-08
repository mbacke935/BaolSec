# Broker — NATS JetStream

Décision et comparaison : `docs/decisions/0002-broker.md`.

| Fichier | Rôle |
|---|---|
| `nats-server.conf` | Serveur : JetStream, stockage `/data`, `sync_interval: 1s`, jeton `BROKER_TOKEN` |
| `topology.json` | Flux, rétention et consommateurs durables (source de vérité) |
| `init_broker.py` | Crée ou met à jour la topologie et le bucket KV ; peut être relancé |
| `Dockerfile` | Image du conteneur ponctuel `broker-init` |
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

Consommateurs : pull, acquittement explicite, 5 livraisons au plus, délais 5 s, 15 s, 30 s, 60 s.
Le service qui échoue à la 5e livraison publie un `dlq_message/v1` puis acquitte l'original
(`baolsec_common.messaging.process`).

## Règles

- Modifier `topology.json`, puis relancer `make broker-init`. Le stockage, la rétention et le nom d'un flux ne sont pas modifiables après création : `init_broker.py` le signale. En développement, `make broker-reset` supprime les données du broker et recrée les flux ; en production, un tel changement passe par un nouveau flux et une migration documentée.
- La durée de conservation de `normalized-events` et `alerts` est la première limite atteinte (7 jours ou taille) : voir la décision 0002.
- Le port 4222 n'est publié que sur `127.0.0.1` (développement). Les services joignent le broker par le réseau Docker interne.
- Supervision : `http://broker:8222/healthz` et `/jsz` (réseau interne).
