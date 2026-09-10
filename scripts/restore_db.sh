#!/usr/bin/env sh
# PostgreSQL restore for the access-control database — explicit state machine,
# NON-DESTRUCTIVE swap with signal-safe reconciliation.
#
# The active database is NEVER dropped before a validated replacement is in
# place. States:
#
#   PREPARING             lock held; args/dump validated; temp not loaded yet
#   TEMP_READY            dump restored into temp DB and validated
#   ACTIVE_RENAMED        active renamed to <db>_recovery_<stamp>
#   PROMOTED              temp renamed to the active name
#   SMOKE_OK              post-swap smoke test passed (success)
#   ROLLED_BACK           a failure/interrupt was recovered; active is intact
#   FATAL_MANUAL_RECOVERY automatic recovery impossible; nothing deleted
#
# On EXIT/TERM/INT/HUP the handler reconciles from SERVER TRUTH (which databases
# actually exist), not just the in-memory state, because a signal can arrive
# mid-statement:
#   * active exists, recovery absent  -> pre-swap: drop only the temp DB.
#   * active absent, recovery exists  -> mid-swap: restore recovery -> active.
#   * active exists, recovery exists  -> post-swap: keep both (new active + old).
#   * neither exists                  -> ambiguous: delete NOTHING, keep lock.
# It never deletes temp or recovery when the state is ambiguous or a rollback
# failed, and prints instructions that match exactly the objects it kept.
#
# The lock is a directory holding a journal (PID/UTC/target/phase/temp/recovery).
# An existing lock is NEVER auto-removed; a new run fails closed and points to
# the explicit `--release-lock` recovery procedure.
#
# See tests/test_backup_restore_scripts.py (fakes) and
# tests/test_backup_restore_integration.py (real disposable PostgreSQL in CI).
set -eu

DB_USER="${POSTGRES_USER:-acp}"
DB_NAME="${POSTGRES_DB:-access_control}"
COMPOSE="${COMPOSE:-docker compose}"
LOCKDIR="${RESTORE_LOCKDIR:-${TMPDIR:-/tmp}/acp-restore-${DB_NAME}.lock}"
JOURNAL="$LOCKDIR/journal"
# Post-swap smoke query (boolean). Overridable so an operator/test can inject a
# controlled, isolated smoke failure to exercise the post-swap rollback.
SMOKE_SQL="${RESTORE_SMOKE_SQL:-SELECT count(*) >= 0 FROM organizations;}"

STATE=INIT
I_OWN_LOCK=0
KEEP_LOCK=0
WORK=""
TMPDB=""
RECOVERY=""

# --- helpers ----------------------------------------------------------------
is_valid_ident() { printf '%s' "$1" | grep -Eq '^[A-Za-z_][A-Za-z0-9_]*$'; }
is_reserved_db() { case "$1" in postgres|template0|template1) return 0 ;; *) return 1 ;; esac; }

admin_c() { $COMPOSE exec -T db psql -U "$DB_USER" -d postgres -v ON_ERROR_STOP=1 -c "$1"; }

# Run a scalar query; capture VALUE (REPLY) and EXIT CODE separately.
scalar() {
  _db="$1"; _sql="$2"
  REPLY="$($COMPOSE exec -T db psql -U "$DB_USER" -d "$_db" -tAc "$_sql")"; _rc=$?
  REPLY="$(printf '%s' "$REPLY" | tr -d '[:space:]')"
  return "$_rc"
}

db_exists() { scalar postgres "SELECT 1 FROM pg_database WHERE datname='$1';" && [ "$REPLY" = "1" ]; }

journal_write() {
  [ "$I_OWN_LOCK" = 1 ] || return 0
  {
    echo "pid=$$"
    echo "utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "target=$DB_NAME"
    echo "phase=$STATE"
    echo "temp=$TMPDB"
    echo "recovery=$RECOVERY"
  } > "$JOURNAL" 2>/dev/null || true
}
set_state() { STATE="$1"; journal_write; }

usage() {
  echo "usage: $0 <dump.sql.gz> --confirm <DB_NAME>" >&2
  echo "       $0 --drop-recovery <recovery_db> --confirm <recovery_db>" >&2
  echo "       $0 --release-lock --confirm <DB_NAME>   (explicit, safe lock recovery)" >&2
  exit 2
}

# --- explicit, safe lock recovery (never automatic) -------------------------
if [ "${1:-}" = "--release-lock" ]; then
  FLAG="${2:-}"; CONFIRM="${3:-}"
  if ! { [ "$FLAG" = "--confirm" ] && [ "$CONFIRM" = "$DB_NAME" ]; }; then
    echo "error: --release-lock requires --confirm $DB_NAME" >&2; exit 3
  fi
  if [ ! -d "$LOCKDIR" ]; then
    echo "no lock present at $LOCKDIR; nothing to release." >&2
    exit 0
  fi
  echo "Lock journal ($LOCKDIR):" >&2
  if [ -f "$JOURNAL" ]; then cat "$JOURNAL" >&2; else echo "(no journal file)" >&2; fi
  _pid="$(sed -n 's/^pid=//p' "$JOURNAL" 2>/dev/null || true)"
  if [ -n "$_pid" ] && kill -0 "$_pid" 2>/dev/null; then
    echo "error: process $_pid still alive — a restore may be running. Refusing to release." >&2
    exit 4
  fi
  echo "No live owner detected. Review the journal above: if a restore was" >&2
  echo "interrupted, run it again to reconcile BEFORE releasing. Releasing now." >&2
  rm -f "$JOURNAL" 2>/dev/null || true
  rmdir "$LOCKDIR" 2>/dev/null || true
  echo "Lock released." >&2
  exit 0
fi

# --- explicit, separate deletion of a recovery database ---------------------
if [ "${1:-}" = "--drop-recovery" ]; then
  RECOVERY_ARG="${2:-}"; FLAG="${3:-}"; CONFIRM="${4:-}"
  [ -n "$RECOVERY_ARG" ] || usage
  if ! { [ "$FLAG" = "--confirm" ] && [ "$CONFIRM" = "$RECOVERY_ARG" ]; }; then
    echo "error: --drop-recovery requires --confirm <exact recovery db name>" >&2; exit 3
  fi
  is_valid_ident "$RECOVERY_ARG" || { echo "error: invalid identifier '$RECOVERY_ARG'" >&2; exit 2; }
  is_reserved_db "$RECOVERY_ARG" && { echo "error: refusing to drop reserved db '$RECOVERY_ARG'" >&2; exit 2; }
  [ "$RECOVERY_ARG" = "$DB_NAME" ] && { echo "error: '$RECOVERY_ARG' is the ACTIVE database; refusing" >&2; exit 2; }
  case "$RECOVERY_ARG" in
    "${DB_NAME}_recovery_"*) ;;
    *) echo "error: '$RECOVERY_ARG' is not a \${POSTGRES_DB}_recovery_* database" >&2; exit 2 ;;
  esac
  # Same mutex as restore: refuse while a restore is active.
  if ! mkdir "$LOCKDIR" 2>/dev/null; then
    echo "error: a restore is in progress (lock $LOCKDIR); refusing --drop-recovery" >&2
    exit 75
  fi
  I_OWN_LOCK=1
  trap 'rmdir "$LOCKDIR" 2>/dev/null || true' EXIT INT TERM HUP
  echo "AUDIT: dropping recovery database '$RECOVERY_ARG' (target=$DB_NAME, by pid $$, $(date -u +%Y-%m-%dT%H:%M:%SZ))" >&2
  admin_c "DROP DATABASE IF EXISTS \"$RECOVERY_ARG\";"
  echo "Recovery database '$RECOVERY_ARG' dropped."
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

# 3) Mutual exclusion. An existing lock is NEVER auto-removed (fail closed).
if ! mkdir "$LOCKDIR" 2>/dev/null; then
  echo "error: a restore lock already exists at $LOCKDIR — refusing (fail closed)." >&2
  echo "Journal:" >&2
  if [ -f "$JOURNAL" ]; then cat "$JOURNAL" >&2; else echo "(no journal file)" >&2; fi
  echo "If no restore is running, recover explicitly with:" >&2
  echo "  $0 --release-lock --confirm $DB_NAME" >&2
  exit 75
fi
I_OWN_LOCK=1

STAMP="$(date -u +%Y%m%d%H%M%S)"
TMPDB="${DB_NAME}_restore_$STAMP"
RECOVERY="${DB_NAME}_recovery_$STAMP"
is_valid_ident "$TMPDB" || { echo "error: computed temp db invalid: '$TMPDB'" >&2; exit 2; }
is_valid_ident "$RECOVERY" || { echo "error: computed recovery db invalid: '$RECOVERY'" >&2; exit 2; }
WORK="$(mktemp -d)"
set_state PREPARING

# Reconcile from server truth and recover as far as safely possible.
reconcile_and_recover() {
  _active=no; _recovery=no; _temp=no
  if db_exists "$DB_NAME"; then _active=yes; fi
  if db_exists "$RECOVERY"; then _recovery=yes; fi
  if db_exists "$TMPDB"; then _temp=yes; fi

  if [ "$_active" = yes ] && [ "$_recovery" = no ]; then
    # Pre-swap (or already fully rolled back): active intact.
    if [ "$_temp" = yes ]; then admin_c "DROP DATABASE IF EXISTS \"$TMPDB\";" >/dev/null 2>&1 || true; fi
    set_state ROLLED_BACK
    echo "reconciliado: base activa '$DB_NAME' intacta; temporal eliminada si existía." >&2
    return 0
  fi
  if [ "$_active" = no ] && [ "$_recovery" = yes ]; then
    # Mid-swap: active was renamed away and not yet promoted -> restore it.
    if admin_c "ALTER DATABASE \"$RECOVERY\" RENAME TO \"$DB_NAME\";"; then
      admin_c "ALTER DATABASE \"$DB_NAME\" WITH ALLOW_CONNECTIONS true;" >/dev/null 2>&1 || true
      set_state ROLLED_BACK
      echo "reconciliado: rollback OK, '$DB_NAME' restaurada desde '$RECOVERY'." >&2
      [ "$_temp" = yes ] && echo "  (temporal '$TMPDB' conservada para inspección)" >&2
      return 0
    fi
    set_state FATAL_MANUAL_RECOVERY; KEEP_LOCK=1
    echo "FATAL: no se pudo restaurar '$DB_NAME'. La base original está como '$RECOVERY'." >&2
    echo "  Recuperá manualmente: ALTER DATABASE \"$RECOVERY\" RENAME TO \"$DB_NAME\";" >&2
    return 1
  fi
  if [ "$_active" = yes ] && [ "$_recovery" = yes ]; then
    # Post-swap: new active in place, old preserved.
    set_state PROMOTED
    echo "reconciliado: base activa '$DB_NAME' es la nueva; anterior conservada como '$RECOVERY'." >&2
    return 0
  fi
  # Neither exists -> ambiguous. Delete nothing.
  set_state FATAL_MANUAL_RECOVERY; KEEP_LOCK=1
  echo "FATAL: estado ambiguo — ni '$DB_NAME' ni '$RECOVERY' existen. NO se elimina nada." >&2
  echo "  Objetos posibles a inspeccionar: temporal='$TMPDB', recovery='$RECOVERY'." >&2
  return 1
}

on_signal() {
  trap '' EXIT TERM INT HUP  # prevent re-entry
  echo "señal recibida en estado $STATE; reconciliando desde el servidor..." >&2
  reconcile_and_recover || true
  finish
  exit 130
}

finish() {
  if [ -n "$WORK" ]; then rm -rf "$WORK" 2>/dev/null || true; fi
  if [ "$I_OWN_LOCK" = 1 ]; then
    if [ "$KEEP_LOCK" = 1 ]; then
      echo "lock CONSERVADO en $LOCKDIR (estado $STATE) — recuperación manual requerida." >&2
      echo "  Revisá el journal y usá: $0 --release-lock --confirm $DB_NAME (tras reconciliar)." >&2
    else
      rm -f "$JOURNAL" 2>/dev/null || true
      rmdir "$LOCKDIR" 2>/dev/null || true
    fi
  fi
}

on_exit() { code=$?; finish; exit "$code"; }
trap on_signal TERM INT HUP
trap on_exit EXIT

# 4) Decompress (exit checked) and ensure non-empty.
gunzip -c "$DUMP" > "$WORK/restore.sql" || { echo "error: failed to decompress '$DUMP'" >&2; exit 4; }
[ -s "$WORK/restore.sql" ] || { echo "error: decompressed dump is empty" >&2; exit 4; }

# 5) Load into a temporary database and validate it.
echo "Restoring into temporary database '$TMPDB' for validation..."
admin_c "DROP DATABASE IF EXISTS \"$TMPDB\";"
admin_c "CREATE DATABASE \"$TMPDB\" OWNER \"$DB_USER\";"
if ! $COMPOSE exec -T db psql -U "$DB_USER" -d "$TMPDB" -v ON_ERROR_STOP=1 -q < "$WORK/restore.sql"; then
  echo "error: loading the dump into '$TMPDB' failed; live database '$DB_NAME' untouched" >&2
  admin_c "DROP DATABASE IF EXISTS \"$TMPDB\";" >/dev/null 2>&1 || true
  exit 5
fi
if ! scalar "$TMPDB" "SELECT (to_regclass('public.alembic_version') IS NOT NULL AND to_regclass('public.organizations') IS NOT NULL);"; then
  echo "error: validation query failed to run on '$TMPDB'; not swapping" >&2
  admin_c "DROP DATABASE IF EXISTS \"$TMPDB\";" >/dev/null 2>&1 || true
  exit 6
fi
if [ "$REPLY" != "t" ]; then
  echo "error: restored data failed validation (missing alembic_version/organizations); not swapping" >&2
  admin_c "DROP DATABASE IF EXISTS \"$TMPDB\";" >/dev/null 2>&1 || true
  exit 6
fi
set_state TEMP_READY

# 6) Non-destructive swap.
echo "Validation OK. Swapping ('$DB_NAME' -> '$RECOVERY', '$TMPDB' -> '$DB_NAME')..."
admin_c "ALTER DATABASE \"$DB_NAME\" WITH ALLOW_CONNECTIONS false;" >/dev/null 2>&1 || true
admin_c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname IN ('$DB_NAME','$TMPDB') AND pid <> pg_backend_pid();" >/dev/null 2>&1 || true

if ! admin_c "ALTER DATABASE \"$DB_NAME\" RENAME TO \"$RECOVERY\";"; then
  echo "error: could not rename live '$DB_NAME' to '$RECOVERY'; live DB intact, aborting" >&2
  admin_c "ALTER DATABASE \"$DB_NAME\" WITH ALLOW_CONNECTIONS true;" >/dev/null 2>&1 || true
  admin_c "DROP DATABASE IF EXISTS \"$TMPDB\";" >/dev/null 2>&1 || true
  exit 7
fi
set_state ACTIVE_RENAMED

if ! admin_c "ALTER DATABASE \"$TMPDB\" RENAME TO \"$DB_NAME\";"; then
  echo "error: could not promote '$TMPDB' to '$DB_NAME'; rolling back..." >&2
  if admin_c "ALTER DATABASE \"$RECOVERY\" RENAME TO \"$DB_NAME\";"; then
    admin_c "ALTER DATABASE \"$DB_NAME\" WITH ALLOW_CONNECTIONS true;" >/dev/null 2>&1 || true
    set_state ROLLED_BACK
    echo "rollback OK: '$DB_NAME' restaurada desde '$RECOVERY'. Temporal '$TMPDB' conservada." >&2
    exit 8
  fi
  set_state FATAL_MANUAL_RECOVERY; KEEP_LOCK=1
  echo "FATAL: rollback falló. La base original está como '$RECOVERY' y la candidata como '$TMPDB'." >&2
  echo "  Recuperá manualmente: ALTER DATABASE \"$RECOVERY\" RENAME TO \"$DB_NAME\";" >&2
  exit 9
fi
set_state PROMOTED
admin_c "ALTER DATABASE \"$DB_NAME\" WITH ALLOW_CONNECTIONS true;" >/dev/null 2>&1 || true

# 7) Post-swap smoke test. On failure, roll back to the recovery DB.
if ! scalar "$DB_NAME" "$SMOKE_SQL" || [ "$REPLY" != "t" ]; then
  echo "error: post-swap smoke test failed; rolling back to '$RECOVERY'..." >&2
  FAILED="${DB_NAME}_failed_$STAMP"
  admin_c "ALTER DATABASE \"$DB_NAME\" WITH ALLOW_CONNECTIONS false;" >/dev/null 2>&1 || true
  admin_c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$DB_NAME' AND pid <> pg_backend_pid();" >/dev/null 2>&1 || true
  if admin_c "ALTER DATABASE \"$DB_NAME\" RENAME TO \"$FAILED\";" && \
     admin_c "ALTER DATABASE \"$RECOVERY\" RENAME TO \"$DB_NAME\";"; then
    admin_c "ALTER DATABASE \"$DB_NAME\" WITH ALLOW_CONNECTIONS true;" >/dev/null 2>&1 || true
    set_state ROLLED_BACK
    echo "rolled back to previous database. Suspect restore kept as '$FAILED' for inspection." >&2
    exit 10
  fi
  set_state FATAL_MANUAL_RECOVERY; KEEP_LOCK=1
  echo "FATAL: smoke-test rollback falló. Previa='$RECOVERY'; sospechosa='$DB_NAME'." >&2
  exit 11
fi
set_state SMOKE_OK

# 8) Success. The previous database is preserved (NOT deleted) as $RECOVERY.
echo "Restore complete: '$DB_NAME' restored from '$DUMP'."
echo "Previous database preserved as '$RECOVERY' (NOT deleted)."
echo "After verifying the app, delete it explicitly with:"
echo "  $0 --drop-recovery $RECOVERY --confirm $RECOVERY"
