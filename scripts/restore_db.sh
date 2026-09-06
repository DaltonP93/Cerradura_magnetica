#!/usr/bin/env sh
# PostgreSQL restore for the access-control database — NON-DESTRUCTIVE swap.
#
# The active database is NEVER dropped before a validated replacement is in
# place. The dump is restored into a temporary database and validated; then the
# swap is done by renames with automatic rollback:
#
#   active  -> <db>_recovery_<stamp>     (step 1)
#   temp    -> active                    (step 2)
#   if step 2 fails: <db>_recovery_<stamp> -> active   (rollback)
#
# The previous database is kept as <db>_recovery_<stamp> and is NOT deleted
# until a post-swap smoke test succeeds AND you delete it explicitly:
#
#   scripts/restore_db.sh --drop-recovery <db>_recovery_<stamp> --confirm <db>_recovery_<stamp>
#
# This is still a sensitive operation: run it against an ISOLATED verification
# environment, and stop the backend (or ensure it cannot reconnect) during the
# swap. We set ALLOW_CONNECTIONS=false + terminate connections on the target
# during the rename window as a safeguard.
#
# See tests/test_backup_restore_scripts.py (fakes) and
# tests/test_backup_restore_integration.py (real disposable PostgreSQL in CI).
set -eu

DB_USER="${POSTGRES_USER:-acp}"
DB_NAME="${POSTGRES_DB:-access_control}"
COMPOSE="${COMPOSE:-docker compose}"
LOCKDIR="${RESTORE_LOCKDIR:-${TMPDIR:-/tmp}/acp-restore-${DB_NAME}.lock}"

# --- helpers ----------------------------------------------------------------
is_valid_ident() { printf '%s' "$1" | grep -Eq '^[A-Za-z_][A-Za-z0-9_]*$'; }
is_reserved_db() { case "$1" in postgres|template0|template1) return 0 ;; *) return 1 ;; esac; }

# Run an admin statement against the maintenance DB, propagating its exit code.
admin_c() { $COMPOSE exec -T db psql -U "$DB_USER" -d postgres -v ON_ERROR_STOP=1 -c "$1"; }

# Run a scalar query; capture VALUE and EXIT CODE separately (no `psql | grep`).
# Sets REPLY to the trimmed output. Returns psql's exit code.
scalar() {
  _db="$1"; _sql="$2"
  REPLY="$($COMPOSE exec -T db psql -U "$DB_USER" -d "$_db" -tAc "$_sql")"; _rc=$?
  REPLY="$(printf '%s' "$REPLY" | tr -d '[:space:]')"
  return "$_rc"
}

usage() {
  echo "usage: $0 <dump.sql.gz> --confirm <DB_NAME>" >&2
  echo "       $0 --drop-recovery <recovery_db> --confirm <recovery_db>" >&2
  exit 2
}

# --- explicit, separate deletion of a recovery database ---------------------
if [ "${1:-}" = "--drop-recovery" ]; then
  RECOVERY="${2:-}"; FLAG="${3:-}"; CONFIRM="${4:-}"
  [ -n "$RECOVERY" ] || usage
  [ "$FLAG" = "--confirm" ] && [ "$CONFIRM" = "$RECOVERY" ] || {
    echo "error: --drop-recovery requires --confirm <exact recovery db name>" >&2; exit 3; }
  is_valid_ident "$RECOVERY" || { echo "error: invalid identifier '$RECOVERY'" >&2; exit 2; }
  is_reserved_db "$RECOVERY" && { echo "error: refusing to drop reserved db '$RECOVERY'" >&2; exit 2; }
  case "$RECOVERY" in
    *_recovery_*) ;;
    *) echo "error: '$RECOVERY' is not a recovery database (expected *_recovery_*)" >&2; exit 2 ;;
  esac
  echo "Dropping recovery database '$RECOVERY'..."
  admin_c "DROP DATABASE IF EXISTS \"$RECOVERY\";"
  echo "Recovery database '$RECOVERY' dropped."
  exit 0
fi

# --- restore ----------------------------------------------------------------
DUMP="${1:-}"; FLAG="${2:-}"; CONFIRM="${3:-}"

# 1) Argument validation BEFORE contacting PostgreSQL.
[ -n "$DUMP" ] || usage
[ "$FLAG" = "--confirm" ] || { echo "error: missing --confirm <DB_NAME>" >&2; usage; }
[ -n "$CONFIRM" ] || { echo "error: --confirm requires the exact database name" >&2; usage; }
[ -f "$DUMP" ] || { echo "error: dump not found: $DUMP" >&2; exit 2; }
for name in "$DB_NAME" "$DB_USER"; do
  is_valid_ident "$name" || { echo "error: invalid SQL identifier: '$name'" >&2; exit 2; }
done
is_reserved_db "$DB_NAME" && { echo "error: refusing to restore over reserved db '$DB_NAME'" >&2; exit 2; }
[ "$CONFIRM" = "$DB_NAME" ] || {
  echo "error: confirmation '$CONFIRM' does not match target '$DB_NAME' (pass --confirm $DB_NAME)" >&2; exit 3; }

# 2) Verify dump integrity BEFORE any destructive action.
gzip -t "$DUMP" || { echo "error: '$DUMP' is not a valid gzip file; aborting" >&2; exit 4; }

# 3) Mutual exclusion: only one restore at a time.
if ! mkdir "$LOCKDIR" 2>/dev/null; then
  echo "error: another restore is in progress (lock: $LOCKDIR)" >&2
  exit 75
fi

STAMP="$(date -u +%Y%m%d%H%M%S)"
TMPDB="${DB_NAME}_restore_$STAMP"
RECOVERY="${DB_NAME}_recovery_$STAMP"
WORK="$(mktemp -d)"
TMPSQL="$WORK/restore.sql"
SWAPPED=0   # 1 once TMPDB has become the live DB

cleanup() {
  rm -rf "$WORK"
  # If we never completed the swap, drop the half-built temp DB (best effort).
  if [ "$SWAPPED" -eq 0 ]; then
    admin_c "DROP DATABASE IF EXISTS \"$TMPDB\";" >/dev/null 2>&1 || true
  fi
  rmdir "$LOCKDIR" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

is_valid_ident "$TMPDB" || { echo "error: computed temp db invalid: '$TMPDB'" >&2; exit 2; }
is_valid_ident "$RECOVERY" || { echo "error: computed recovery db invalid: '$RECOVERY'" >&2; exit 2; }

# 4) Decompress (exit code checked) and ensure non-empty.
gunzip -c "$DUMP" > "$TMPSQL" || { echo "error: failed to decompress '$DUMP'" >&2; exit 4; }
[ -s "$TMPSQL" ] || { echo "error: decompressed dump is empty" >&2; exit 4; }

# 5) Load into a temporary database.
echo "Restoring into temporary database '$TMPDB' for validation..."
admin_c "DROP DATABASE IF EXISTS \"$TMPDB\";"
admin_c "CREATE DATABASE \"$TMPDB\" OWNER \"$DB_USER\";"
if ! $COMPOSE exec -T db psql -U "$DB_USER" -d "$TMPDB" -v ON_ERROR_STOP=1 -q < "$TMPSQL"; then
  echo "error: loading the dump into '$TMPDB' failed; live database '$DB_NAME' untouched" >&2
  exit 5
fi

# 6) Validate the temp DB (exit code AND value checked separately).
if ! scalar "$TMPDB" "SELECT (to_regclass('public.alembic_version') IS NOT NULL AND to_regclass('public.organizations') IS NOT NULL);"; then
  echo "error: validation query failed to run on '$TMPDB'; not swapping" >&2
  exit 6
fi
if [ "$REPLY" != "t" ]; then
  echo "error: restored data failed validation (missing alembic_version/organizations); not swapping" >&2
  exit 6
fi

# 7) Non-destructive swap with rollback.
# Block new connections to the current live DB during the rename window.
echo "Validation OK. Swapping via recovery rename ('$DB_NAME' -> '$RECOVERY', '$TMPDB' -> '$DB_NAME')..."
admin_c "ALTER DATABASE \"$DB_NAME\" WITH ALLOW_CONNECTIONS false;" || true
admin_c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname IN ('$DB_NAME','$TMPDB') AND pid <> pg_backend_pid();" >/dev/null 2>&1 || true

# Step 1: rename the live DB to a recovery name. If this fails, the live DB is
# still intact — re-enable connections and abort.
if ! admin_c "ALTER DATABASE \"$DB_NAME\" RENAME TO \"$RECOVERY\";"; then
  echo "error: could not rename live '$DB_NAME' to '$RECOVERY'; live DB intact, aborting" >&2
  admin_c "ALTER DATABASE \"$DB_NAME\" WITH ALLOW_CONNECTIONS true;" >/dev/null 2>&1 || true
  exit 7
fi

# Step 2: promote the temp DB to the live name. On failure, roll back.
if ! admin_c "ALTER DATABASE \"$TMPDB\" RENAME TO \"$DB_NAME\";"; then
  echo "error: could not promote '$TMPDB' to '$DB_NAME'; rolling back..." >&2
  if admin_c "ALTER DATABASE \"$RECOVERY\" RENAME TO \"$DB_NAME\";"; then
    admin_c "ALTER DATABASE \"$DB_NAME\" WITH ALLOW_CONNECTIONS true;" >/dev/null 2>&1 || true
    echo "rollback OK: '$DB_NAME' restored to its original database; no data lost" >&2
    exit 8
  fi
  echo "FATAL: rollback failed. The original database is named '$RECOVERY' and the" >&2
  echo "       candidate is '$TMPDB'. Recover manually: ALTER DATABASE \"$RECOVERY\" RENAME TO \"$DB_NAME\";" >&2
  exit 9
fi
SWAPPED=1
admin_c "ALTER DATABASE \"$DB_NAME\" WITH ALLOW_CONNECTIONS true;" >/dev/null 2>&1 || true

# 8) Post-swap smoke test. On failure, roll back to the recovery DB (the new,
#    suspect DB is kept as <db>_failed_<stamp> for inspection).
if ! scalar "$DB_NAME" "SELECT count(*) >= 0 FROM organizations;" || [ "$REPLY" != "t" ]; then
  echo "error: post-swap smoke test failed; rolling back to '$RECOVERY'..." >&2
  FAILED="${DB_NAME}_failed_$STAMP"
  admin_c "ALTER DATABASE \"$DB_NAME\" WITH ALLOW_CONNECTIONS false;" >/dev/null 2>&1 || true
  admin_c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$DB_NAME' AND pid <> pg_backend_pid();" >/dev/null 2>&1 || true
  if admin_c "ALTER DATABASE \"$DB_NAME\" RENAME TO \"$FAILED\";" && \
     admin_c "ALTER DATABASE \"$RECOVERY\" RENAME TO \"$DB_NAME\";"; then
    admin_c "ALTER DATABASE \"$DB_NAME\" WITH ALLOW_CONNECTIONS true;" >/dev/null 2>&1 || true
    echo "rolled back to previous database. Suspect restore kept as '$FAILED' for inspection." >&2
    exit 10
  fi
  echo "FATAL: smoke-test rollback failed. Previous DB is '$RECOVERY'; suspect is '$DB_NAME'." >&2
  exit 11
fi

# 9) Success. The previous database is preserved (NOT deleted) as $RECOVERY.
echo "Restore complete: '$DB_NAME' restored from '$DUMP'."
echo "Previous database preserved as '$RECOVERY' (NOT deleted)."
echo "After you have verified the app, delete it explicitly with:"
echo "  scripts/restore_db.sh --drop-recovery $RECOVERY --confirm $RECOVERY"
