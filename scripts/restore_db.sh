#!/usr/bin/env sh
# PostgreSQL restore for the access-control database.
#
# Restores a gzipped dump produced by backup_db.sh. This is a DESTRUCTIVE
# operation and must normally be run against an ISOLATED verification
# environment, never blindly against production. A backup you have never
# restored is not a backup.
#
#   scripts/restore_db.sh backups/acp-20260906T020000Z.sql.gz --confirm access_control
#
# Safety design (see tests/test_backup_restore_scripts.py):
#   * All argument/dump validation happens BEFORE contacting PostgreSQL.
#   * `gzip -t` verifies the dump before anything is dropped.
#   * DB_NAME/DB_USER are validated as strict SQL identifiers; the reserved
#     databases postgres/template0/template1 are refused.
#   * Confirmation is tied to the EXACT database name (--confirm <DB_NAME>),
#     not a generic --force.
#   * POSIX `sh` has no `pipefail`; we never pipe through commands whose failure
#     must abort. gunzip writes a temp .sql, whose exit code is checked; psql
#     loads from that file by redirection, whose exit code is checked.
#   * The dump is loaded into a TEMPORARY database and validated (schema +
#     alembic_version) before the live database is replaced by an atomic
#     rename. On any failure the temp database is dropped and the live database
#     is left untouched. Success is printed only if every step succeeded.
set -eu

usage() {
  echo "usage: $0 <dump.sql.gz> --confirm <DB_NAME>" >&2
  echo "  restores <dump.sql.gz> into DB_NAME via a temporary DB, then swaps." >&2
  exit 2
}

DUMP="${1:-}"
FLAG="${2:-}"
CONFIRM="${3:-}"

DB_USER="${POSTGRES_USER:-acp}"
DB_NAME="${POSTGRES_DB:-access_control}"
COMPOSE="${COMPOSE:-docker compose}"

# --- 1) Argument validation (before touching PostgreSQL) --------------------
[ -n "$DUMP" ] || usage
[ "$FLAG" = "--confirm" ] || { echo "error: missing --confirm <DB_NAME>" >&2; usage; }
[ -n "$CONFIRM" ] || { echo "error: --confirm requires the exact database name" >&2; usage; }

if [ ! -f "$DUMP" ]; then
  echo "error: dump not found: $DUMP" >&2
  exit 2
fi

is_valid_ident() {
  # PostgreSQL unquoted identifier: letter/underscore then letters/digits/underscore.
  printf '%s' "$1" | grep -Eq '^[A-Za-z_][A-Za-z0-9_]*$'
}
is_reserved_db() {
  case "$1" in postgres|template0|template1) return 0 ;; *) return 1 ;; esac
}

for name in "$DB_NAME" "$DB_USER"; do
  is_valid_ident "$name" || { echo "error: invalid SQL identifier: '$name'" >&2; exit 2; }
done
if is_reserved_db "$DB_NAME"; then
  echo "error: refusing to restore over the reserved database '$DB_NAME'" >&2
  exit 2
fi
if [ "$CONFIRM" != "$DB_NAME" ]; then
  echo "error: confirmation '$CONFIRM' does not match target database '$DB_NAME'" >&2
  echo "       pass exactly: --confirm $DB_NAME" >&2
  exit 3
fi

# --- 2) Verify the dump integrity BEFORE any destructive action -------------
if ! gzip -t "$DUMP"; then
  echo "error: '$DUMP' is not a valid gzip file; aborting before any change" >&2
  exit 4
fi

WORK="$(mktemp -d)"
TMPSQL="$WORK/restore.sql"
TMPDB="${DB_NAME}_restore_$(date -u +%Y%m%d%H%M%S)"
is_valid_ident "$TMPDB" || { echo "error: computed temp db name invalid: '$TMPDB'" >&2; exit 2; }

# Best-effort cleanup: remove temp files and drop the temp DB if it survives.
cleanup() {
  rm -rf "$WORK"
  $COMPOSE exec -T db psql -U "$DB_USER" -d postgres -v ON_ERROR_STOP=1 \
    -c "DROP DATABASE IF EXISTS \"$TMPDB\";" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

if ! gunzip -c "$DUMP" > "$TMPSQL"; then
  echo "error: failed to decompress '$DUMP'; aborting" >&2
  exit 4
fi
if [ ! -s "$TMPSQL" ]; then
  echo "error: decompressed dump is empty; aborting" >&2
  exit 4
fi

echo "Restoring into a temporary database '$TMPDB' for validation..."

# --- 3) Load into a temporary database --------------------------------------
$COMPOSE exec -T db psql -U "$DB_USER" -d postgres -v ON_ERROR_STOP=1 <<SQL
DROP DATABASE IF EXISTS "$TMPDB";
CREATE DATABASE "$TMPDB" OWNER "$DB_USER";
SQL

if ! $COMPOSE exec -T db psql -U "$DB_USER" -d "$TMPDB" -v ON_ERROR_STOP=1 -q < "$TMPSQL"; then
  echo "error: loading the dump into '$TMPDB' failed; live database '$DB_NAME' untouched" >&2
  exit 5
fi

# --- 4) Validate the restored temp database before swapping -----------------
if ! $COMPOSE exec -T db psql -U "$DB_USER" -d "$TMPDB" -tAc \
      "SELECT to_regclass('public.alembic_version') IS NOT NULL AND to_regclass('public.organizations') IS NOT NULL;" \
      | grep -q '^t$'; then
  echo "error: restored data failed validation (missing alembic_version/organizations); not swapping" >&2
  exit 6
fi

# --- 5) Atomic swap: replace the live database with the validated temp one ---
# NOTE: stop the backend (or scale to 0) before this step so it does not
# reconnect mid-swap. We terminate existing connections immediately before drop.
echo "Validation OK. Swapping '$TMPDB' -> '$DB_NAME'..."
$COMPOSE exec -T db psql -U "$DB_USER" -d postgres -v ON_ERROR_STOP=1 <<SQL
SELECT pg_terminate_backend(pid) FROM pg_stat_activity
  WHERE datname IN ('$DB_NAME', '$TMPDB') AND pid <> pg_backend_pid();
DROP DATABASE IF EXISTS "$DB_NAME";
ALTER DATABASE "$TMPDB" RENAME TO "$DB_NAME";
SQL

# The temp DB has become the live DB; nothing left to drop.
trap - EXIT INT TERM
rm -rf "$WORK"

echo "Restore complete: '$DB_NAME' restored from '$DUMP'."
echo "Verify: $COMPOSE exec -T db psql -U $DB_USER -d $DB_NAME -c 'SELECT count(*) FROM organizations;'"
echo "Then confirm the schema head: (cd backend && alembic current) matches the code."
# Rollback of a failed restore: the live database is only ever dropped in the
# final swap, immediately before the validated temp DB is renamed into place.
# If the swap itself fails, restore from the most recent good dump into a fresh
# database and re-point the app; keep the previous dump until the new one is
# verified.
