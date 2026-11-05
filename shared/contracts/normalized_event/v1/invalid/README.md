# Exemples invalides

Chaque fichier doit être **rejeté** par le schéma ; le test échoue s'il est accepté.

| Fichier | Raison du rejet attendu |
|---|---|
| `event_ingested_pose_par_le_worker.json` | event.ingested est posé par OpenSearch, pas par le worker |
| `champ_invente_a_la_racine.json` | aucun champ inventé à la racine (ADR 0001, règle 1) |
| `pare_feu_avec_host.json` | le pare-feu est décrit par observer.*, pas host.* |
| `categorie_non_ecs.json` | event.category doit être une valeur autorisée par ECS |
| `authentification_sans_utilisateur.json` | un événement d'authentification doit porter user.name |
| `severite_incoherente.json` | libellé et score de sévérité doivent correspondre |
