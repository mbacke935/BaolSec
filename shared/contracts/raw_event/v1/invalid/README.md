# Exemples invalides

Chaque fichier doit être **rejeté** par le schéma ; le test échoue s'il est accepté.

| Fichier | Raison du rejet attendu |
|---|---|
| `type_de_source_inconnu.json` | type de source hors du périmètre (le mobile passe par son backend : http) |
