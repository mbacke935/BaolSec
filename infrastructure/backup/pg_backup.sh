#!/bin/sh
# Sauvegarde quotidienne de PostgreSQL (ES-09, C4 section 8).
#
# Format personnalisé de pg_dump (-Fc) : restauration sélective possible avec pg_restore.
# Rotation : les sauvegardes plus anciennes que BACKUP_RETENTION_DAYS jours sont supprimées.
# Lancé en boucle par le service « backup » de compose.yaml (une sauvegarde toutes les
# BACKUP_INTERVAL_S secondes, 24 h par défaut), ou ponctuellement : BACKUP_ONCE=1.
#
# Variables : PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE (variables standard de libpq),
#             BACKUP_DIR (défaut /backups), BACKUP_RETENTION_DAYS (défaut 14), BACKUP_INTERVAL_S (86400).
#
# Restauration (voir docs/deployment/sauvegarde_restauration.md) :
#   pg_restore --clean --if-exists -d baolsec /backups/baolsec-AAAAMMJJ-HHMMSS.dump
set -eu
BACKUP_DIR="${BACKUP_DIR:-/backups}"
RETENTION="${BACKUP_RETENTION_DAYS:-14}"
INTERVAL="${BACKUP_INTERVAL_S:-86400}"
mkdir -p "$BACKUP_DIR"

backup_once() {
  stamp=$(date -u +%Y%m%d-%H%M%S)
  tmp="$BACKUP_DIR/.baolsec-$stamp.dump.part"
  out="$BACKUP_DIR/baolsec-$stamp.dump"
  if pg_dump -Fc -f "$tmp" "${PGDATABASE:-baolsec}"; then
    mv "$tmp" "$out"
    echo "$(date -u +%FT%TZ) sauvegarde ok : $out ($(du -h "$out" | cut -f1))"
  else
    rm -f "$tmp"
    echo "$(date -u +%FT%TZ) ÉCHEC de la sauvegarde" >&2
    return 1
  fi
  find "$BACKUP_DIR" -name 'baolsec-*.dump' -type f -mtime "+$RETENTION" -print -delete \
    | sed 's/^/supprimée (rétention) : /'
}

if [ "${BACKUP_ONCE:-0}" = "1" ]; then
  backup_once
  exit $?
fi
while true; do
  backup_once || true
  sleep "$INTERVAL"
done
