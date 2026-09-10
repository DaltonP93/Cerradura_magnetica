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
#
# Correctness guarantees (see tests/test_backup_restore_scripts.py):
#   * A failing pg_dump makes the whole script fail (no false "success").
#     POSIX `sh` has no `pipefail`, so we do NOT pipe pg_dump into gzip; we dump
#     to a temp file, check pg_dump's exit code, then gzip the temp file.
#   * The final dump is only ever a fully written, gzip-verified file, published
#     via an atomic rename. A partial/interrupted run leaves no *.sql.gz behind.
#   * Retention prune runs only after a successful backup.
set -eu
umask 077  # dumps are sensitive: owner-only

BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
DB_USER="${POSTGRES_USER:-acp}"
DB_NAME="${POSTGRES_DB:-access_control}"
COMPOSE="${COMPOSE:-docker compose}"

# Validate RETENTION_DAYS is a non-negative integer before using it with find.
case "$RETENTION_DAYS" in
  ''|*[!0-9]*) echo "error: RETENTION_DAYS must be a non-negative integer, got '$RETENTION_DAYS'" >&2; exit 2 ;;
esac

mkdir -p "$BACKUP_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$BACKUP_DIR/acp-$STAMP.sql.gz"

# Work in a temp file; clean it up on any exit unless we succeed and clear trap.
TMP="$(mktemp "$BACKUP_DIR/.acp-$STAMP.XXXXXX")"
TMPGZ="$TMP.gz"
trap 'rm -f "$TMP" "$TMPGZ"' EXIT INT TERM

echo "Backing up $DB_NAME -> $OUT"

# 1) Dump to a plain temp file and check pg_dump's own exit code (no pipe).
if ! $COMPOSE exec -T db pg_dump -U "$DB_USER" -d "$DB_NAME" --no-owner > "$TMP"; then
  echo "error: pg_dump failed; no backup written" >&2
  exit 1
fi

# 2) A valid dump is never empty (pg_dump always emits a header).
if [ ! -s "$TMP" ]; then
  echo "error: pg_dump produced an empty dump; refusing to publish it" >&2
  exit 1
fi

# 3) Compress, then verify the gzip integrity before publishing.
gzip -n "$TMP"          # creates "$TMPGZ", removes "$TMP"
if ! gzip -t "$TMPGZ"; then
  echo "error: produced gzip failed integrity check; not publishing" >&2
  exit 1
fi

# 4) Publish atomically. Only now is a *.sql.gz visible under BACKUP_DIR.
mv "$TMPGZ" "$OUT"
trap - EXIT INT TERM

# 5) Prune old dumps only after a successful backup.
find "$BACKUP_DIR" -name 'acp-*.sql.gz' -type f -mtime "+$RETENTION_DAYS" -delete || true
echo "Backup complete: $OUT (retained last $RETENTION_DAYS days in $BACKUP_DIR)."
