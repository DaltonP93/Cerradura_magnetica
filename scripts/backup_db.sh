#!/usr/bin/env sh
# PostgreSQL backup for the access-control database.
#
# Produces a compressed, timestamped dump under BACKUP_DIR and prunes dumps
# older than RETENTION_DAYS. Intended to be run from cron on the host, e.g.:
#
#   0 2 * * *  /path/to/scripts/backup_db.sh >> /var/log/acp-backup.log 2>&1
#
# It runs pg_dump inside the compose `db` service, so no client tools are needed
# on the host. Store BACKUP_DIR on separate, access-controlled storage: dumps
# contain personal data, credentials metadata and audit trails.
set -eu

BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
DB_USER="${POSTGRES_USER:-acp}"
DB_NAME="${POSTGRES_DB:-access_control}"
COMPOSE="${COMPOSE:-docker compose}"

mkdir -p "$BACKUP_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$BACKUP_DIR/acp-$STAMP.sql.gz"

echo "Backing up $DB_NAME -> $OUT"
$COMPOSE exec -T db pg_dump -U "$DB_USER" -d "$DB_NAME" --no-owner | gzip > "$OUT"

# Prune old dumps.
find "$BACKUP_DIR" -name 'acp-*.sql.gz' -type f -mtime "+$RETENTION_DAYS" -delete || true
echo "Backup complete. Retained last $RETENTION_DAYS days in $BACKUP_DIR."
