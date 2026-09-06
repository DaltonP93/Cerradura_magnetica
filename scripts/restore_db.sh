#!/usr/bin/env sh
# PostgreSQL restore for the access-control database.
#
# Restores a gzipped dump produced by backup_db.sh into the compose `db`
# service. This is a DESTRUCTIVE operation: it drops and recreates the target
# database. It refuses to run without an explicit --force flag, and it should
# normally be exercised against an ISOLATED verification environment, never
# blindly against production. A backup you have never restored is not a backup.
#
#   scripts/restore_db.sh backups/acp-20260906T020000Z.sql.gz --force
#
# It pipes the dump through psql inside the compose `db` service, so no client
# tools are needed on the host.
set -eu

DUMP="${1:-}"
FORCE="${2:-}"
DB_USER="${POSTGRES_USER:-acp}"
DB_NAME="${POSTGRES_DB:-access_control}"
COMPOSE="${COMPOSE:-docker compose}"

if [ -z "$DUMP" ]; then
  echo "usage: $0 <dump.sql.gz> --force" >&2
  exit 2
fi
if [ ! -f "$DUMP" ]; then
  echo "error: dump not found: $DUMP" >&2
  exit 2
fi
if [ "$FORCE" != "--force" ]; then
  echo "refusing to restore without --force (this DROPS and recreates '$DB_NAME')." >&2
  echo "run against an isolated environment and pass --force to proceed." >&2
  exit 3
fi

echo "Restoring $DB_NAME from $DUMP"
# Terminate other connections, drop and recreate the database, then load.
$COMPOSE exec -T db psql -U "$DB_USER" -d postgres -v ON_ERROR_STOP=1 <<SQL
SELECT pg_terminate_backend(pid) FROM pg_stat_activity
  WHERE datname = '$DB_NAME' AND pid <> pg_backend_pid();
DROP DATABASE IF EXISTS "$DB_NAME";
CREATE DATABASE "$DB_NAME" OWNER "$DB_USER";
SQL

gunzip -c "$DUMP" | $COMPOSE exec -T db psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1

echo "Restore complete. Verify with: SELECT count(*) FROM organizations;"
echo "Then run 'alembic current' to confirm the schema head matches the code."
