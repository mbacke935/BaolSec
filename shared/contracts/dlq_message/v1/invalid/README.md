# Exemples invalides

Chaque fichier doit être **rejeté** par le schéma ; le test échoue s'il est accepté.

| Fichier | Raison du rejet attendu |
|---|---|
| `rejet_ingestion_sans_source.json` | un événement refusé à l'ingestion indique sa source (source_id) |
