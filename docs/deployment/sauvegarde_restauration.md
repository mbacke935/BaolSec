# Sauvegarde et restauration (ES-09)

Trois ensembles de données ont une valeur durable. Chacun a son mécanisme.

| Données | Mécanisme | Fréquence et conservation | Emplacement |
|---|---|---|---|
| PostgreSQL : sources, règles, comptes, alertes, incidents, couverture, audit | service `backup` (`infrastructure/backup/pg_backup.sh`, `pg_dump -Fc`) | toutes les 24 h, `BACKUP_RETENTION_DAYS` jours (14) | volume `postgres-backups` |
| OpenSearch : événements, alertes et incidents indexés | service `opensearch-maintenance` (`indexing_worker.maintenance`) : instantané puis purge | toutes les 24 h ; index de plus de `EVENTS_RETENTION_DAYS` jours (90) supprimés ; `SNAPSHOT_KEEP` instantanés (14) | volume `opensearch-snapshots`, dépôt `baolsec` |
| Broker : messages en transit | flux JetStream sur disque (`sync_interval: 1s`) | 7 jours ; file de rejet 30 jours | volume `broker-data` |

Les volumes Docker restent sur la machine : copiez régulièrement `postgres-backups` et
`opensearch-snapshots` vers un stockage externe (autre disque, autre site).

## PostgreSQL

Sauvegarde immédiate (en plus de la sauvegarde quotidienne) :

```bash
docker compose run --rm -e BACKUP_ONCE=1 backup
docker compose run --rm --entrypoint ls backup -lh /backups
```

Restauration (arrêter d'abord les services qui écrivent, pour un état cohérent) :

```bash
docker compose stop baolsec-api incident-builder coverage-worker detection-worker ingestion-gateway normalization-worker
docker compose run --rm --entrypoint sh backup -c \
  'pg_restore --clean --if-exists -d baolsec /backups/baolsec-AAAAMMJJ-HHMMSS.dump'
docker compose up -d
```

`pg_restore --clean` remplace les objets existants. Les rôles des comptes de service ne font pas
partie de la sauvegarde de la base : ils sont recréés par `db-migrate` (mots de passe lus dans `.env`).

## OpenSearch

Liste des instantanés et restauration d'un index (exemple : les événements du 26/11/2026) :

```bash
curl -sk -u admin:$OPENSEARCH_PASSWORD https://127.0.0.1:9200/_snapshot/baolsec/_all | jq '.snapshots[].snapshot'
curl -sk -u admin:$OPENSEARCH_PASSWORD -X POST \
  "https://127.0.0.1:9200/_snapshot/baolsec/<instantané>/_restore" \
  -H 'Content-Type: application/json' \
  -d '{"indices": "baolsec-events-2026.11.26", "include_global_state": false}'
```

Un index restauré doit d'abord être supprimé s'il existe encore. Si OpenSearch est indisponible,
l'indexation n'acquitte pas les messages : ils restent dans le broker (7 jours) et sont indexés au
retour d'OpenSearch.

## Vérification

Une sauvegarde n'est fiable qu'une fois restaurée. Une fois par mois : restaurer la dernière
sauvegarde PostgreSQL dans une base temporaire et comparer quelques comptages.

```bash
docker compose run --rm --entrypoint sh backup -c '
  createdb baolsec_verif &&
  pg_restore -d baolsec_verif $(ls -t /backups/baolsec-*.dump | head -1) &&
  psql -d baolsec_verif -Atc "SELECT count(*) FROM config.sources; SELECT count(*) FROM incidents.incidents;" &&
  dropdb baolsec_verif'
```
