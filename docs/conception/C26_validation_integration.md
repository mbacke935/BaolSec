# C26 — Validation d'intégration : état de campagne

## Objectif

Valider une pile BaolSec isolée de bout en bout : ingestion, JetStream, normalisation,
détection, incidents PostgreSQL, indexation OpenSearch, API, couverture et supervision.

## Audit exécuté le 16 novembre 2026

La branche était `c25-lab-datasets`, au commit `75a201f`. Les modifications locales
préexistantes ont été constatées et préservées : tests API, tests/verrous des workers
coverage et indexing, suppression locale de `coverage/repositories/__init__.py`, et les
deux fichiers `.python-version` non suivis. Aucun de ces fichiers n'a été modifié par C26.

### Ressources observées

| Mesure | Résultat observé |
|---|---|
| RAM disponible | environ 2,0 Gio sur 6,5 Gio |
| Swap utilisé | environ 3,7 Gio sur 4,0 Gio |
| Espace disponible du dépôt | 106 Gio |
| Pile BaolSec existante | broker, PostgreSQL, gateway, normalizer, detection-worker et incident-builder déjà actifs |
| Composants absents de la pile active | OpenSearch, indexer, coverage-worker, API, Prometheus, Grafana |

Les ports normaux sont déjà occupés par la pile existante : NATS `127.0.0.1:4222`,
PostgreSQL `127.0.0.1:5432`, gateway `8443` et `6514`. Cette pile et ses volumes n'ont
pas été modifiés ni interrogés fonctionnellement, car elle n'est pas l'environnement
isolé C26 demandé.

## Blocages constatés

1. Le démarrage d'une seconde pile complète serait risqué sur la capacité mémoire
   observée : OpenSearch est configuré avec un tas Java de 512 Mio, auquel s'ajoutent
   PostgreSQL, NATS, les workers, l'API et la supervision. Le swap est déjà presque plein.
   La consigne C26 interdit explicitement de provoquer une saturation ou de perturber les
   services existants.
2. Le `compose.yaml` racine ne décrit pas les chemins des services réels : il référence
   notamment `services/gateway/Dockerfile`, `services/normalizer/Dockerfile`,
   `services/enricher/Dockerfile` et `services/rule-engine/Dockerfile`, alors que le dépôt
   contient `services/ingestion-gateway`, `services/normalization-worker` et
   `services/detection-worker`. Une construction isolée depuis ce fichier échouerait.
3. Les Compose complémentaires `infrastructure/compose/compose.dev.yaml` et
   `compose.test.yaml` sont vides (`services: {}`). Ils ne fournissent pas de topologie
   C26 isolée exploitable.

## Architecture vérifiée par lecture

Le code configure le parcours attendu : `RAW_EVENTS` → normalisation →
`NORMALIZED_EVENTS` → détection → `alerts`/`ALERTS` → incident-builder ; les indexeurs
consomment `NORMALIZED_EVENTS`, `ALERTS` et `INCIDENTS`. Les workers s'appuient sur des
consommateurs pull JetStream et `RetryPolicy` pour DLQ et redélivrance. Cette constatation
ne constitue pas une preuve d'intégration réelle.

## Scénarios C26

| ID | Composant | Scénario | Résultat attendu | Résultat obtenu | Statut |
|---|---|---|---|---|---|
| C26-ENV | Compose isolé | Démarrage d'une pile dédiée | Réseaux/volumes/ports dédiés | Non exécuté : blocages ci-dessus | Bloqué |
| C26-NATS | JetStream | Streams, consumers, ack, DLQ | Flux réel vérifié | Non exécuté | Bloqué |
| C26-ING | Gateway | HTTPS et Syslog TLS | Publication RAW_EVENTS | Non exécuté | Bloqué |
| C26-NORM | Normalizer | RAW_EVENTS → NORMALIZED_EVENTS | ECS et ack réels | Non exécuté | Bloqué |
| C26-DET | Detection | 8 règles et négatifs | Alertes ALERTS | Non exécuté | Bloqué |
| C26-INC | Incident builder | ALERTS → PostgreSQL | Idempotence et corrélation | Non exécuté | Bloqué |
| C26-OS | Indexing | Événements/alertes indexés | Recherche OpenSearch | Non exécuté | Bloqué |
| C26-API | API/RBAC | Consultation et autorisations | Routes réelles | Non exécuté | Bloqué |
| C26-COV | Coverage | RAW/NORMALIZED → PostgreSQL | Mesures réelles | Non exécuté | Bloqué |
| C26-RES | Résilience | Pannes/reprises contrôlées | Redélivrance/DLQ | Non exécuté | Bloqué |
| C26-OBS | Supervision | Prometheus/Grafana | Métriques collectées | Non exécuté | Bloqué |

## Préconditions pour rejouer C26

1. Libérer suffisamment de mémoire et de swap, ou utiliser une machine disposant d'au
   moins 8 Gio réellement libres pour la pile isolée.
2. Créer et faire relire un Compose C26 cohérent avec les chemins et noms de services
   actuels, des réseaux/volumes portant le préfixe `baolsec-c26`, et des ports localhost
   non conflictuels.
3. Fournir un jeu de variables C26 isolé, sans modifier ni exposer `.env`.
4. Après démarrage, consigner les identifiants de conteneurs, streams, consumers, index et
   résultats des huit scénarios avec preuves réelles.

## Conclusion

La campagne d'intégration n'a pas été exécutée. Aucun succès d'intégration, de résilience,
de DLQ réel, de persistance PostgreSQL, d'OpenSearch, d'API ou de supervision ne peut être
déclaré sur la base de cet audit.

## Mise à jour C26-PRE2 — 16 novembre 2026

### A. Résumé exécutif

**C26 BLOQUÉE.** Le garde-fou de 8 Gio réellement libres n'est pas satisfait : 2,1 Gio
étaient disponibles et le swap était à 3,8/4 Gio. Aucun conteneur C26 n'a été construit
ou démarré.

### B. Environnement

La configuration isolée est `infrastructure/compose/c26-pre/compose.prepared.yaml`.
Elle résout statiquement 15 services et 5 volumes dédiés, avec projet, réseau et
conteneurs `baolsec-c26`. La pile normale a été seulement observée.

### C. Architecture

Les flux gateway → RAW_EVENTS → normalisation → NORMALIZED_EVENTS →
détection/couverture/indexation et ALERTS → incidents PostgreSQL/indexation restent
statiques. L'indexing-worker est le seul écrivain OpenSearch localisé. Aucun flux réel
n'a été vérifié.

### D. Tests

| ID | Objectif | Résultat | Statut |
|---|---|---|---|
| PRE2-COMPOSE | validation Compose | 15 services / 5 volumes | RÉUSSI |
| PRE2-NATS | topologie/durables | JSON valide et noms alignés | RÉUSSI |
| PRE2-TLS | générateur TLS test | syntaxe shell valide | RÉUSSI |
| Q-GW | unitaires gateway | 34 passed | RÉUSSI |
| Q-NORM | unitaires normalisation | 96 passed | RÉUSSI |
| Q-DET | unitaires détection | 60 passed | RÉUSSI |
| Q-INDEX | unitaires indexation | 6 passed | RÉUSSI |
| Q-INC/COV/API | collect-only | 94/27/35 tests collectés ; suite incidents non terminée après 120 s | PARTIELLEMENT VALIDÉ |
| C26-ENV à C26-OBS | intégration réelle | pile non démarrée, garde-fou mémoire | BLOQUÉ |

### E. Résultats par composant

NATS, ingestion, incidents, PostgreSQL, OpenSearch, coverage, API, Prometheus et
Grafana sont BLOQUÉS en intégration. Les succès unitaires ne prouvent aucune
communication inter-service.

### F. Résultats de bout en bout

Scénarios C25 positifs, négatifs, malformés et doublons : **NON EXÉCUTÉ**.

### G. Résilience

**NON EXÉCUTÉ.** Aucun service C26 n'existant, aucun redémarrage ou test DLQ réel n'a
été provoqué.

### H. Qualité et régressions

Aucun code applicatif n'a été modifié. Les suites locales réussies sont listées dans
le tableau ; les autres n'ont pas de résultat complet.

### I. Limites

Limite matérielle : mémoire/swap. Limite logicielle : l'indexer attend un stream
`INCIDENTS`, mais aucun producteur `incidents` n'a été trouvé. Limite expérimentale :
aucun build ni service C26 exécuté.

### J. Conclusion

**C26 BLOQUÉE.** La prochaine étape est une machine disposant d'au moins 8 Gio de RAM
réellement libres, puis une autorisation explicite de démarrer la pile C26 isolée.
