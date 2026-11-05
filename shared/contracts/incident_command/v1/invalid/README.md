# Exemples invalides

Chaque fichier doit être **rejeté** par le schéma ; le test échoue s'il est accepté.

| Fichier | Raison du rejet attendu |
|---|---|
| `statut_alerte_sur_incident.json` | statut_alerte cible une alerte (alert_id) |
| `statut_incident_inconnu.json` | statut d'incident hors de ouvert / en_cours / clos |
