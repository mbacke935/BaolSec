# C26-FIX — corrections et validation locale

## A. Résumé exécutif

**C26-FIX PARTIELLEMENT VALIDÉE.** L'intégration reste bloquée : 2,1 Gio de RAM
disponibles, sous le seuil de sécurité de 8 Gio. Aucun Docker C26 n'a été lancé.

## B. État Git

Branche `c25-lab-datasets`, commit `75a201f`. L'état Git préexistant est préservé,
y compris `services/coverage-worker/src/coverage/repositories/__init__.py`, absent du
disque et marqué `D`. `.env` et les Compose actifs n'ont pas été modifiés.

## C. Défauts identifiés

L'incident-builder ne publie jamais le sujet `incidents` : la recherche des appels
`publish` confirme qu'il écrit seulement PostgreSQL. L'indexing-worker exige pourtant
`INCIDENTS/indexing-incidents`. Le défaut est réel et bloque l'indexation d'incidents.

## D. Corrections réalisées

Dans les seuls artefacts C26, `topology.c26.json` crée `INCIDENTS` et aligne les
durables sur les valeurs du code. `db-bootstrap` charge idempotemment sources/règles ;
le générateur TLS produit exclusivement des identifiants de test C26.

## E. Incident Builder / NATS

Une publication directe après transaction SQL créerait une fenêtre de perte ou de
fantôme. La solution sûre est une outbox transactionnelle, un contrat `incident/v1` et
un relai idempotent. Ces éléments n'existent pas : ils ne sont pas inventés sans test
PostgreSQL/NATS réel.

## F. Idempotence et cohérence

`alert_id` déduplique les alertes et `incident_alerts.alert_id` est UNIQUE : une alerte
ne peut appartenir qu'à un incident. L'idempotence de l'outbox est non vérifiée.

## G. Timeout incident-builder

`test_alert.py + test_consumer.py` : 25 réussis en 0,81 s.
`test_correlation.py + test_lifecycle.py` : 51 réussis en 0,21 s.
`test_http.py` dépasse 20 s : le problème est localisé à FastAPI TestClient, mais sa
cause exacte n'est pas démontrée ; aucune correction spéculative n'est conservée.

## H. Contrats interservices

Gateway, normalisation et détection disposent de tests locaux. Le contrat incidents →
indexation est divergent par absence de producteur. Aucun échange NATS réel n'est
déclaré vérifié.

## I. Tests

Gateway 34 réussis ; normalisation 96 ; détection 60 ; indexation 6. Incident-builder
76 réussis par groupes, HTTP timeout. Coverage/API : 27/35 collectés, non exécutés.
Compose C26, JSON topologie et syntaxe TLS : réussis statiquement.

## J. Tests non exécutés

Build, NATS, PostgreSQL, OpenSearch, API réelle, supervision, E2E, DLQ et résilience
sont bloqués par le garde-fou matériel et l'interdiction Docker.

## K. Limites

Résultats unitaires ou statiques uniquement ; aucune preuve de durabilité ou intégration.

## L. Décision finale

**C26-FIX PARTIELLEMENT VALIDÉE.** La divergence INCIDENTS est prouvée ; sa correction
sûre exige une outbox transactionnelle conçue et testée avant C26 réelle.
