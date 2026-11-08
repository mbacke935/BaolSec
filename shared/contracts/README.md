# Contrats de messages BaolSec

Contrats versionnés échangés entre les services (C5). Une modification incompatible crée une nouvelle version (`v2`) ; `v1` n'est jamais modifiée de façon incompatible.

| Contrat | Flux / canal | Producteur | Consommateurs | Rapport à ECS |
|---|---|---|---|---|
| `raw_event/v1` | raw-events | ingestion-gateway | normalization-worker, coverage-worker | Enveloppe interne |
| `normalized_event/v1` | normalized-events | normalization-worker | detection-worker, indexing-worker, coverage-worker | Conforme à ECS 9.5.0 |
| `alert/v1` | alerts | detection-worker | incident-builder, indexing-worker | Champs ECS pertinents |
| `dlq_message/v1` | dlq | service qui abandonne un message ; passerelle pour un événement reçu invalide | inspection par l'Administrateur (`GET /dlq`) | Enveloppe technique |
| `incident_command/v1` (+ `result.schema.json`) | HTTP interne | api | incident-builder | Commande métier |

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

## Règles communes

- **Identifiants** : `event_id` (identifiant natif fiable ou SHA-256 hexadécimal) et `alert_id` (SHA-256) servent de Msg-Id dans le broker. `command_id` (UUID, valeur de l'en-tête Idempotency-Key) est une clé d'idempotence HTTP et PostgreSQL : il ne passe jamais par le broker.
- **Dates** : RFC 3339, en UTC.
- **Champs inconnus refusés** : aucun champ hors contrat, en particulier à la racine d'un événement ECS.
- **`event.ingested`** n'apparaît dans aucun message : il est posé par le pipeline d'ingestion OpenSearch.
