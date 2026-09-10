#!/usr/bin/env sh
# CI-only shim that lets backup_db.sh / restore_db.sh talk to a plain PostgreSQL
# service (no docker compose). It translates
#
#     <shim> exec -T db <cmd> [args...]   ->   <cmd> [args...]
#
# and relies on the standard libpq environment (PGHOST, PGPORT, PGUSER,
# PGPASSWORD) for the connection, so the client tools connect to the CI service.
# It is NOT used in production — production uses `docker compose exec -T db`.
set -eu
[ "${1:-}" = exec ] || { echo "pg_compose_shim: expected 'exec', got: $*" >&2; exit 2; }
shift
[ "${1:-}" = "-T" ] && shift
[ "${1:-}" = "db" ] && shift
exec "$@"
