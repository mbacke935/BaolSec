# Contrats de messages BaolSec

Contrats versionnés échangés entre les services (C5). Une modification incompatible crée une nouvelle version (`v2`) ; `v1` n'est jamais modifiée de façon incompatible.

| Contrat | Flux / canal | Producteur | Consommateurs | Rapport à ECS |
|---|---|---|---|---|
| `raw_event/v1` | raw-events | ingestion-gateway | normalization-worker, coverage-worker | Enveloppe interne |
| `normalized_event/v1` | normalized-events | normalization-worker | detection-worker, indexing-worker, coverage-worker | Conforme à ECS 9.5.0 |
| `alert/v1` | alerts | detection-worker | incident-builder, indexing-worker | Champs ECS pertinents |
| `dlq_message/v1` | dlq | service qui abandonne un message ; passerelle pour un événement reçu invalide | inspection par l'Administrateur (`GET /dlq`) | Enveloppe technique |
| `incident_command/v1` (+ `result.schema.json`) | HTTP interne | api | incident-builder | Commande métier |
| `rule/v1` | `config.rule_versions.definition_yaml` (YAML) | api ; `make rules-load` en attendant l'API | detection-worker, coverage-worker (via `config.rule_requirements`) | Champs ECS des événements |

Références : `docs/decisions/0001-schema-commun-ecs.md` (choix d'ECS) et `docs/conception/C5-correspondance-ecs.md` (correspondance champ par champ).

## Organisation

```text
<contrat>/v1/
├── schema.json      # JSON Schema (draft 2020-12)
├── examples/        # messages valides (Linux, Windows, pare-feu, application web…)
└── invalid/         # messages qui doivent être rejetés, avec README des raisons
```

## Vérification

Depuis la racine du dépôt :

```bash
uv run --with jsonschema --with rfc3339-validator scripts/testing/validate_contracts.py
```

Chaque exemple de `examples/` doit être accepté, chaque fichier de `invalid/` rejeté.
Chaque exemple brut de `raw_event/v1/examples/` a un exemple normalisé du même nom : le service de
normalisation doit produire exactement celui-ci (`services/normalization-worker/tests/test_contrats.py`).
L'exemple Windows reproduit la forme envoyée par l'agent (entrée winevtlog de Fluent Bit, `EventData` nommé).

## Règles communes

- **Identifiants** : `event_id` (identifiant natif fiable ou SHA-256 hexadécimal) et `alert_id` (SHA-256) servent de Msg-Id dans le broker. `command_id` (UUID, valeur de l'en-tête Idempotency-Key) est une clé d'idempotence HTTP et PostgreSQL : il ne passe jamais par le broker.
- **Règles** (C12) : `rule.id` d'une alerte est le code de la règle (`AUTH-001`) ; l'identifiant `config.rules.id` en est dérivé (UUID v5 sur un espace de noms fixe), ce qui permet au service des incidents de retrouver la règle sans requête supplémentaire.
- **Dates** : RFC 3339, en UTC.
- **Champs inconnus refusés** : aucun champ hors contrat, en particulier à la racine d'un événement ECS.
- **`event.ingested`** n'apparaît dans aucun message : il est posé par le pipeline d'ingestion OpenSearch.
