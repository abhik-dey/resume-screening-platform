#!/usr/bin/env bash
# Postgres backup and restore.
#
# Flagged as missing since Phase 21. A deployment with no backup story has
# a single failure away from losing every candidate record, and the vector
# index can be rebuilt only by re-embedding everything — which costs real
# money in API calls.
#
#   ./scripts/backup.sh backup            take a backup
#   ./scripts/backup.sh restore FILE      restore one
#   ./scripts/backup.sh list              list what exists
#   ./scripts/backup.sh verify FILE       check a backup is readable
#
# A BACKUP YOU HAVE NEVER RESTORED IS NOT A BACKUP. `verify` exists so
# that claim can be checked without waiting for an incident.
set -euo pipefail
cd "$(dirname "$0")/.."

COMPOSE="docker compose -f infra/docker-compose.prod.yml"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"

read_env() {
  local key="$1"
  if [ -f backend/.env.prod ]; then
    grep "^${key}=" backend/.env.prod | cut -d'=' -f2- || true
  fi
}

PG_USER="$(read_env POSTGRES_USER)"
PG_DB="$(read_env POSTGRES_DB)"
PG_USER="${PG_USER:-resume_user}"
PG_DB="${PG_DB:-resume_screening}"

cmd_backup() {
  mkdir -p "$BACKUP_DIR"
  local stamp file
  stamp="$(date +%Y%m%d-%H%M%S)"
  file="${BACKUP_DIR}/${PG_DB}-${stamp}.sql.gz"

  echo "Backing up ${PG_DB}..."
  # Custom format would be smaller, but plain SQL can be inspected and
  # partially recovered by hand — which matters when a restore is going
  # badly and you need to see what's actually in the file.
  $COMPOSE exec -T postgres pg_dump -U "$PG_USER" -d "$PG_DB" --clean --if-exists \
    | gzip > "$file"

  # A zero-byte or truncated backup is worse than none, because it looks
  # like protection. Verify before reporting success.
  if [ ! -s "$file" ]; then
    echo "FAILED: backup file is empty"
    rm -f "$file"
    exit 1
  fi
  if ! gzip -t "$file" 2>/dev/null; then
    echo "FAILED: backup is not a valid gzip archive"
    rm -f "$file"
    exit 1
  fi

  echo "Wrote $file ($(du -h "$file" | cut -f1))"
  cmd_prune
}

cmd_verify() {
  local file="${1:?usage: verify FILE}"
  [ -f "$file" ] || { echo "No such file: $file"; exit 1; }

  echo "Verifying $file"
  gzip -t "$file" || { echo "FAILED: corrupt archive"; exit 1; }

  # Look for structure a real dump must contain. A gzip that decompresses
  # to nothing useful still passes `gzip -t`.
  local tables
  tables=$(gzip -dc "$file" | grep -c "^CREATE TABLE" || true)
  echo "  archive intact"
  echo "  CREATE TABLE statements: $tables"
  if [ "$tables" -lt 5 ]; then
    echo "FAILED: expected at least 5 tables — this dump looks incomplete"
    exit 1
  fi
  echo "Backup looks restorable."
}

cmd_restore() {
  local file="${1:?usage: restore FILE}"
  [ -f "$file" ] || { echo "No such file: $file"; exit 1; }

  cmd_verify "$file"

  echo
  echo "This REPLACES the contents of ${PG_DB}."
  echo "Every candidate, score, and report currently stored will be overwritten."
  read -rp "Type the database name to confirm: " confirm
  [ "$confirm" = "$PG_DB" ] || { echo "Aborted."; exit 1; }

  echo "Restoring..."
  gzip -dc "$file" | $COMPOSE exec -T postgres psql -U "$PG_USER" -d "$PG_DB"
  echo "Restored. Run 'make prod-migrate' in case the dump predates the current schema."
}

cmd_list() {
  mkdir -p "$BACKUP_DIR"
  if ! ls "$BACKUP_DIR"/*.sql.gz > /dev/null 2>&1; then
    echo "No backups in $BACKUP_DIR"
    return
  fi
  ls -lh "$BACKUP_DIR"/*.sql.gz | awk '{print $9, "\t", $5, "\t", $6, $7, $8}'
}

cmd_prune() {
  local removed
  removed=$(find "$BACKUP_DIR" -name "*.sql.gz" -mtime "+${RETENTION_DAYS}" -print -delete 2>/dev/null | wc -l)
  [ "$removed" -gt 0 ] && echo "Pruned $removed backup(s) older than ${RETENTION_DAYS} days"
  return 0
}

case "${1:-}" in
  backup)  cmd_backup ;;
  restore) cmd_restore "${2:-}" ;;
  verify)  cmd_verify "${2:-}" ;;
  list)    cmd_list ;;
  prune)   cmd_prune ;;
  *)
    cat <<USAGE
Usage: $0 {backup|restore FILE|verify FILE|list|prune}

  backup         dump the database, gzip it, verify it, prune old ones
  verify FILE    check a backup is intact and contains real schema
  restore FILE   restore (destructive, requires confirmation)
  list           show existing backups
  prune          delete backups older than \${RETENTION_DAYS:-14} days

Schedule with cron:
  0 2 * * * cd /path/to/project && ./scripts/backup.sh backup >> /var/log/rsp-backup.log 2>&1

Note this backs up Postgres only. The Qdrant vector index is rebuildable
by re-indexing resumes, but that costs embedding API calls — back up its
volume too if that matters to you.
USAGE
    exit 1
    ;;
esac
