# ADR 0002 — Choix du broker de messages persistant

- **Statut** : accepté
- **Date** : 5 novembre 2026
- **Décideurs** : Mohamed Mbacke, Pape Makhtar Aidara
- **Documents liés** : C2 (ENF-02, ENF-05, ENF-08, CT-06), C3 (sections 2.6, 3.1 et 4.1), C5 (contrats), carte Trello C8

## Contexte

Les services de BaolSec échangent les événements et les alertes par un broker persistant (C3 2.1). L'encadreur a fixé deux conditions : le broker doit être **persistant**, et il ne doit pas être choisi « uniquement parce qu'on le connaît ». NATS JetStream figurait dans C3 comme choix **provisoire** ; cette décision le confirme ou le remplace.

Le broker doit satisfaire les exigences déjà fixées :

| Besoin | Origine |
|---|---|
| Messages conservés après un redémarrage, accusé de publication avant de répondre à l'agent | C3 3.1, W1 |
| Acquittement individuel, reprise des messages non acquittés, 5 tentatives puis dlq | C3 3.1 |
| Relecture d'un flux depuis une position (reconstruction, rejeu de tests) | Carte C8, C4 8 |
| Plusieurs instances d'un même service se partagent un flux sans traiter deux fois le même message | ENF-08 |
| Déduplication à la publication par identifiant stable (`event_id`, `alert_id`) | C3 3.1, I-7 |
| Stockage clé-valeur pour l'état des règles de détection, sans technologie supplémentaire si possible | C3 2.6, carte C12 |
| ≥ 500 événements/s soutenus sur la machine de démonstration (8 Go de RAM, 6,5 Go utilisables), partagée avec PostgreSQL, OpenSearch et les services | ENF-02, CT-06 |

## Options étudiées

1. **NATS JetStream** (nats-server 2.15.2, version stable la plus récente au 5 novembre 2026)
2. **Redis Streams** (Redis 8.x)
3. **Apache Kafka 4.2** ou **Redpanda** (compatible avec le protocole Kafka)

## Comparaison

| Critère | NATS JetStream | Redis Streams | Kafka 4.2 / Redpanda |
|---|---|---|---|
| **Persistance** | Flux stockés sur disque (stockage `file` par défaut). L'écriture sur disque (fsync) est réglée par `sync_interval` : 2 min par défaut, `always` pour un fsync avant chaque accusé. | Toutes les données sont **en mémoire** ; le disque sert à la reprise (RDB, AOF). Avec la politique par défaut (`appendfsync everysec`), jusqu'à 1 s d'écritures perdues en cas de panne. | Journal sur disque, conçu pour de très gros volumes. |
| **Accusé de publication** | PubAck après stockage dans le flux. | Réponse à `XADD`. | Accusé du broker selon `acks`. |
| **Acquittement par message** | Oui (`AckExplicit`, valeur par défaut). | Oui (`XACK`, liste des messages en attente). | Consumer groups classiques : validation d'une **position** (offset), pas d'un message. Acquittement par message avec les *share groups*, déclarés prêts pour la production dans Kafka 4.2 (février 2026). |
| **Redélivrance et limite de tentatives** | Automatique après `AckWait` (30 s par défaut) ou `nak` ; `MaxDeliver` limite le nombre de livraisons ; délais croissants avec `BackOff` ; compteur de livraisons fourni avec chaque message. | Non automatique : un consommateur doit reprendre les messages en attente (`XCLAIM` / `XAUTOCLAIM`) ; la limite de tentatives est à coder. | Classique : à coder (topics de reprise). Share groups : limite de livraisons gérée par le broker. |
| **File de rejet (dlq)** | Pas d'alimentation automatique ; une alerte (*advisory*) est émise quand `MaxDeliver` est atteint. | À coder. | Pas de dlq native pour les consommateurs ; à coder. |
| **Relecture** | Par numéro de séquence ou par date (`DeliverByStartSequence`, `DeliverByStartTime`). | Par identifiant (`XRANGE`, `XREAD`). | Par offset ou par date. |
| **Partage d'un flux entre instances** | Consommateur durable en mode pull partagé par plusieurs instances. | Consumer groups. | Consumer groups (une partition par instance active) ou share groups. |
| **Déduplication à la publication** | Native, **sur tout le flux**, par l'en-tête `Nats-Msg-Id`, dans une fenêtre réglable (2 min par défaut). Indépendante de l'instance qui publie. | Depuis Redis 8.6 (`XADD … IDMP`) : déduplication **par producteur** (`pid`), au plus 10 000 identifiants par producteur. Deux instances de la passerelle ont des `pid` différents : un lot renvoyé par un agent vers l'autre instance ne serait pas reconnu comme doublon. | Producteur idempotent : déduplication limitée à une session de producteur ; un producteur redémarré ou une autre instance n'est pas couvert, sauf transactions. |
| **Stockage clé-valeur pour l'état des règles** | Intégré (bucket KV construit sur un flux, révisions, écriture conditionnelle). | Intégré (Redis est un stockage clé-valeur). | Absent : il faudrait ajouter Redis ou une base. |
| **Ressources** | Un binaire unique ; **17 Mo de RAM** mesurés à vide avec JetStream activé (nats-server 2.15.2). | Faible à vide, mais la mémoire croît avec le volume conservé, puisque tout le flux est en RAM. | JVM pour Kafka (Java 17 pour les brokers) ; Redpanda demande en production au moins 2 cœurs et **2 Go de RAM par cœur**. |
| **Exploitation** | Configuration courte, image officielle `nats`. | Simple ; réglage de la persistance et de la mémoire maximale à surveiller. | La plus lourde des trois (KRaft, partitions, réglage de la JVM). |

### Mesures réalisées

Mesures faites le 5 novembre 2026 sur l'environnement de développement (nats-server 2.15.2, messages de 600 octets, client nats-py 2.16.0). Elles servent à comparer des réglages, **pas** à valider ENF-02 : la mesure de référence sera refaite sur la machine de démonstration (CT-06) avec `scripts/testing/bench_broker.py`.

| `sync_interval` | Publication séquentielle (attente de chaque PubAck) | 50 publications en parallèle |
|---|---|---|
| 2 min (défaut) | 6 834 msg/s | 26 721 msg/s |
| 1 s | 6 437 msg/s | 29 211 msg/s |
| `always` | 2 412 msg/s | 5 047 msg/s |

Première mesure sur la machine de démonstration (HP 255 G10, broker en conteneur, `sync_interval: 1s`, messages de 1 000 octets, 5 novembre 2026) : **1 293 msg/s** en publication séquentielle et **13 006 msg/s** avec 50 publications en vol. La passerelle publie les événements d'un lot en parallèle ; le besoin d'ENF-02 est d'au moins 1 000 écritures/s (raw-events puis normalized-events). La mesure avec la pile complète sera faite en C27.

Valeurs par défaut vérifiées sur le serveur : fenêtre de déduplication 120 s, stockage `file`, rétention `limits`, `AckWait` 30 s, `MaxDeliver` illimité, `MaxAckPending` 1 000. Un second envoi avec le même `Nats-Msg-Id` est signalé comme doublon et n'est pas stocké.

## Décision

**NATS JetStream (nats-server 2.15.2)** est le broker de BaolSec, et son **bucket KV** stocke l'état des règles de détection.

## Justification

1. **Déduplication adaptée à notre architecture.** La passerelle est réplicable (ENF-08) et un agent peut renvoyer un lot vers une autre instance. JetStream déduplique sur tout le flux par `event_id`, quelle que soit l'instance qui publie. Redis 8.6 déduplique par producteur et Kafka par session de producteur : ni l'un ni l'autre ne couvre ce cas.
2. **Reprises gérées par le broker.** Acquittement individuel, redélivrance automatique, compteur de livraisons et `MaxDeliver` correspondent directement à la règle « 5 tentatives puis dlq » de C3. Avec Redis Streams, cette mécanique serait à écrire et à tester.
3. **Mémoire.** Sur une machine de 8 Go partagée avec OpenSearch et PostgreSQL, un broker qui garde ses flux sur disque est préférable à Redis, qui garde tout le flux en RAM, et à Kafka/Redpanda, dont les besoins minimaux (JVM, 2 Go par cœur) dépassent ce qui reste disponible.
4. **Une technologie de moins.** Le bucket KV intégré évite d'ajouter Redis pour l'état des règles. Redis reste le repli documenté si les tests de C14 montrent une limite du KV.
5. **Ce qui a été écarté et pourquoi.** Kafka/Redpanda sont faits pour des volumes très supérieurs à ceux d'une PME, au prix d'une exploitation plus lourde. Redis Streams est simple, mais sa persistance n'est pas sa fonction première et les reprises seraient à coder.

## Limites acceptées

- **Durabilité sur un seul nœud.** Avec un seul serveur, la valeur par défaut `sync_interval: 2m` peut faire perdre jusqu'à 2 min de messages déjà acquittés en cas de coupure de courant ou de plantage du système (pas en cas d'arrêt du seul processus). BaolSec fixe **`sync_interval: 1s`** : perte maximale d'une seconde dans ce cas, avec un débit mesuré équivalent au défaut. `always` (fsync avant chaque accusé) sera adopté si la mesure sur la machine de démonstration montre qu'il tient ENF-02 avec la pile complète ; le résultat sera reporté dans C27.
- **Pas de grappe.** Un seul serveur NATS en démonstration ; la réplication des flux (jusqu'à 5 copies en grappe) est une évolution possible, pas un livrable.
- **La dlq reste applicative**, comme prévu dans C3 : le service qui abandonne un message publie un `dlq_message/v1`, attend la confirmation, puis acquitte l'original.
- **La fenêtre de déduplication est limitée** (fixée à 10 min) : chaque consommateur garde son idempotence applicative (C3 3.1).
- **Une publication sans réponse peut quand même être stockée.** Observé en test : pendant un arrêt du broker, une publication expire côté client (la passerelle répond 503), puis le client la transmet à la reconnexion. L'agent renvoie alors le même événement, et la déduplication par `event_id` empêche le doublon. C'est pourquoi la fenêtre de déduplication (10 min) doit rester supérieure au délai de reprise des agents.

## Configuration retenue

Détail et valeurs dans `infrastructure/broker/` (flux et consommateurs) et `infrastructure/state-store/` (bucket KV).

| Flux | Sujet | Rétention | Producteur | Consommateurs durables |
|---|---|---|---|---|
| `RAW_EVENTS` | `raw-events` | 72 h ou 20 Gio | ingestion-gateway | `normalization`, `coverage-raw` |
| `NORMALIZED_EVENTS` | `normalized-events` | 72 h ou 20 Gio | normalization-worker | `detection`, `indexing-events`, `coverage-normalized` |
| `ALERTS` | `alerts` | 30 jours ou 2 Gio | detection-worker | `incident-builder`, `indexing-alerts` |
| `DLQ` | `dlq.<service>` | 30 jours ou 2 Gio, nouveaux messages refusés si plein | service qui abandonne un message | aucun (inspection par l'Administrateur) |

Commun à tous les consommateurs : mode pull, `AckExplicit`, `MaxDeliver` 5, `BackOff` 5 s, 15 s, 30 s, 60 s, `MaxAckPending` 1 000. Commun aux flux : stockage `file`, fenêtre de déduplication 10 min, taille maximale d'un message 1 Mio.

## Conséquences

- Le code métier n'utilise que l'interface `baolsec_common.messaging` (I-9) ; l'adaptateur NATS est isolé dans `nats_adapter.py`.
- `infrastructure/broker/init_broker.py` crée ou met à jour les flux, les consommateurs et le bucket KV ; il peut être relancé sans risque.
- Les tests `tests/integration/broker/` vérifient la persistance après redémarrage, la relecture, le partage entre instances, la déduplication et la redélivrance jusqu'à la dlq.
- Un changement de broker passerait par un nouvel adaptateur et une nouvelle décision, sans toucher au code métier.

## Sources

- NATS, consommateurs JetStream : https://docs.nats.io/nats-concepts/jetstream/consumers
- NATS, flux JetStream : https://docs.nats.io/nats-concepts/jetstream/streams
- NATS, fonctionnement du KV : https://docs.nats.io/learn/key-value/under-the-hood
- NATS, documentation de `sync_interval` : https://github.com/nats-io/nats.docs/pull/896
- Synadia, résultats Jepsen sur NATS 2.12.1 et `sync_interval` : https://synadia.com/blog/jepsen-nats-2-12-1
- Versions de nats-server : https://releasealert.dev/github/nats-io/nats-server
- Redis, persistance : https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/
- Redis, XADD idempotent (8.6) : https://redis.io/docs/latest/develop/data-types/streams/idempotency/
- Apache Kafka 4.2.0 : https://kafka.apache.org/blog/2026/02/17/apache-kafka-4.2.0-release-announcement/
- Kafka 4.x et KRaft : https://andrewbaker.ninja/2026/02/17/apache-kafka-4-x-what-kraft-and-zookeeper-removal-mean/
- Producteur idempotent Kafka : https://docs.axonops.com/data-platforms/kafka/application-development/producers/idempotence
- Redpanda, exigences de production : https://docs.redpanda.com/current/deploy/redpanda/manual/production/requirements/
