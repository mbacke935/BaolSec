# ADR 0001 — Choix du schéma commun de normalisation

- **Statut** : accepté
- **Date** : 5 novembre 2026
- **Décideurs** : Mohamed Mbacke, Pape Makhtar Aidara
- **Documents liés** : C3 (sections 3.3 et 4.2), C4 (section 6), C5 (contrats), `docs/conception/C5-correspondance-ecs.md`

## Contexte

BaolSec normalise des événements issus de sources hétérogènes : systèmes Linux, postes Windows, pare-feu et applications web (dont le backend des applications mobiles). L'encadreur demande de s'appuyer sur un schéma reconnu plutôt que d'en inventer un. Deux schémas ont été étudiés : **Elastic Common Schema (ECS)** et **Open Cybersecurity Schema Framework (OCSF)**.

## Décision

**ECS 9.5.0** est le schéma de référence des événements normalisés de BaolSec. Le champ `ecs.version` vaut `9.5.0` dans chaque événement normalisé et chaque alerte.

## Justification

- Correspondance directe avec les champs du modèle de données C4 (`src_ip` → `source.ip`, `user_name` → `user.name`, etc.).
- Conventions de nommage utilisées par OpenSearch, en particulier par les correspondances par défaut de Security Analytics.
- Règles de détection simples à écrire sur des champs génériques (`event.category`, `event.outcome`, `user.name`, `source.ip`).
- Charge de mise en œuvre adaptée à une équipe de deux personnes.
- Possibilité d'ajouter des champs propres au projet dans un espace de noms dédié lorsque les champs standards ne suffisent pas.

## Périmètre

| Contrat | Rapport à ECS |
|---|---|
| `raw_event/v1` | Enveloppe interne de collecte, indépendante d'ECS |
| `normalized_event/v1` | Conforme à ECS 9.5.0 |
| `alert/v1` | S'appuie sur les champs ECS pertinents (`event.kind: alert`, `rule.*`, entités) |
| `dlq_message/v1` | Enveloppe technique de rejet, indépendante d'ECS |
| `incident_command/v1` | Commande métier interne, indépendante d'ECS |

ECS est la convention des **événements de sécurité**, pas le format de tous les messages échangés entre les services.

## Règles d'application

1. **Champs standards d'abord.** Un champ ECS existant est toujours préféré. Aucun champ n'est créé à la racine du document.
2. **Espace de noms `baolsec.*`** pour les données propres au projet (identifiant et type de la source, heure de réception, sévérité normalisée, classification d'adresse IP…). Chaque champ `baolsec.*` est décrit dans la table de correspondance.
3. **Trois horodatages distincts** :

   | Champ | Signification | Renseigné par |
   |---|---|---|
   | `@timestamp` | Heure d'origine de l'événement | normalization-worker, à partir de la source |
   | `baolsec.received_at` | Heure de réception par la passerelle | ingestion-gateway |
   | `event.ingested` | Heure d'écriture dans OpenSearch | pipeline d'ingestion OpenSearch, au moment de l'écriture |

   `event.ingested` est posé par un pipeline d'ingestion OpenSearch (processeur `set` avec l'horodatage d'ingestion), appliqué aux index `events-*` et `alerts-*`. Il reflète donc toujours l'écriture réussie : en cas d'échec temporaire puis de nouvelle tentative, la valeur stockée est celle de la tentative qui a abouti. Le pipeline est déclaré dans `infrastructure/opensearch/` et ne change pas la règle selon laquelle seul `indexing-worker` écrit dans OpenSearch.

   `event.created` (première lecture par un agent) n'est renseigné que lorsque l'agent le fournit. Si la source ne donne pas d'heure d'origine fiable, `@timestamp` prend l'heure de réception et `baolsec.timestamp_source` vaut `received`.
4. **Trois niveaux de sévérité séparés** :
   - sévérité **native** : `event.severity` (si la source fournit une échelle numérique), `log.syslog.severity.code` pour Syslog, `log.level` pour les journaux applicatifs ;
   - sévérité **normalisée** BaolSec : `baolsec.severity.label` (`info`, `faible`, `moyenne`, `elevee`, `critique`) ;
   - **score normalisé** : `baolsec.severity.score` (0 à 4).

   La conversion est définie **source par source** dans la table de correspondance ; une valeur native n'est jamais interprétée sans connaître l'échelle de la source.
5. **Règles de détection** : elles n'utilisent que des champs normalisés (ECS ou `baolsec.*`), jamais un nom de champ propre à une source.
6. **Information absente** : lorsqu'une source ne fournit pas une information, le champ est omis. Aucune valeur n'est inventée ; les valeurs génériques (`-`, `anonymous`, `N/A`) sont omises.
7. **Validation** : chaque contrat a un JSON Schema dans `shared/contracts/`, et des exemples pour Linux, Windows, pare-feu et application web sont validés par ces schémas.

## Alternative étudiée

**OCSF** (piloté par la Linux Foundation, version 1.9.0 disponible) est spécialisé en cybersécurité et structuré en catégories, classes et objets. OpenSearch Security Analytics sait aussi traiter des données OCSF. Il a été écarté pour cette première version, car son modèle par classes demande davantage de travail de normalisation et d'écriture des règles. Une exportation vers OCSF reste possible plus tard au moyen d'une table de correspondance dédiée.

## Conséquences

- `normalization-worker` convertit chaque source vers ECS 9.5.0 (`services/normalization-worker/src/normalizer/mapping/`).
- Les consommateurs (détection, indexation, couverture, API) utilisent uniquement les champs normalisés.
- Le modèle C4 et les modèles d'index OpenSearch (C4 section 6) sont alignés sur les noms ECS de la table de correspondance.
- La convergence d'ECS avec les conventions sémantiques d'OpenTelemetry est suivie ; un changement de version d'ECS fera l'objet d'une nouvelle décision.
