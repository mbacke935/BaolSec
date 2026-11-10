# detection-worker — moteur de détection (C12, C14)

Consomme `normalized-events` (consommateur durable `detection`, partagé par toutes les instances),
applique les règles YAML actives et publie les alertes `alert/v1` dans `alerts` (Msg-Id = `alert_id`).
Workflow W3 de C3.

## Fonctionnement

1. Les règles actives sont lues dans `config.rules` / `config.rule_versions` (compte `svc_detection`,
   lecture seule) toutes les 30 s ; chaque règle est contrôlée par le contrat `shared/contracts/rule/v1`.
   Une règle refusée est écartée et signalée (`/health`, métrique) ; les autres restent appliquées.
   Tant qu'aucun chargement n'a réussi, les événements attendent dans le broker.
2. Règle **simple** : un événement suffit ; l'alerte est publiée directement.
3. Règle **window** : l'état (événements comptés, fin de la rafale déjà signalée, alerte en attente) est
   lu dans le KV `detection-state`, mis à jour par écriture conditionnelle sur la révision lue, avec un
   délai de vie égal à la fenêtre + 2 minutes. Seuil atteint : l'alerte est enregistrée « en attente »
   dans la même écriture, publiée, puis effacée.
4. L'événement est acquitté après toutes les règles.

| Situation | Comportement |
|---|---|
| Même événement relivré | Déjà dans l'état : pas compté deux fois |
| Deux instances sur la même clé | Écriture conditionnelle : la seconde relit et recommence |
| Arrêt entre l'écriture du KV et la publication | Alerte republiée au démarrage, toutes les minutes, ou au prochain événement de la clé |
| Événement en retard (source directe) | Plus ancien que maintenant − fenêtre − 2 min : non compté, métrique `late_events` |
| Source rejouée (`ingestion_mode = rejeu`) | Évaluée sur les dates des journaux, sans contrôle de retard |
| Rafale qui continue après l'alerte | Une seule alerte par fenêtre ; une nouvelle rafale après la fin de fenêtre en produit une autre |
| Événement illisible | File de rejet dès la 1re tentative |

`alert_id` = SHA-256 de (code de la règle, clé de regroupement, début de fenêtre) : une alerte
republiée garde son identifiant, le broker et le service des incidents l'écartent.

## Configuration (préfixe `DETECTOR_`)

| Variable | Défaut | Rôle |
|---|---|---|
| `DETECTOR_RULES_SOURCE` | `postgres` | `postgres` ou `file` (dossier YAML, tests) |
| `DETECTOR_POSTGRES_DSN` | — | Compte `svc_detection` |
| `DETECTOR_RULES_DIR` | `/opt/baolsec/rules` | Dossier des règles en mode `file` |
| `DETECTOR_RULES_REFRESH_S` | 30 | Relecture des règles |
| `DETECTOR_LATE_TOLERANCE_S` | 120 | Tolérance des événements en retard |
| `DETECTOR_PENDING_INTERVAL_S` | 60 | Contrôle des alertes en attente |
| `DETECTOR_KV_BUCKET` | `detection-state` | Bucket KV de l'état |

Métriques : `baolsec_detector_evaluations_total{rule,outcome}`, `_alerts_total{rule,severity}`,
`_late_events_total`, `_state_conflicts_total`, `_pending_alerts`, `_republished_total`, `_rules_loaded`,
`_rules_rejected`, `_seconds`.

## Commandes

```bash
make detection-up        # pile complète + chargement des règles + détection
make rules-load          # après modification d'un fichier de rules/ (nouvelle version)
make test-detection      # 45 tests unitaires + 6 tests d'intégration
make bench-detection     # débit
docker compose --env-file .env -f infrastructure/compose/compose.yaml up -d --scale detection-worker=2 detection-worker
```
