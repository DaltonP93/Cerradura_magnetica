"""Real-PostgreSQL end-to-end test for backup_db.sh + restore_db.sh.

Unlike test_backup_restore_scripts.py (fakes), this drives the scripts against a
real, disposable PostgreSQL using a CI shim (scripts/ci/pg_compose_shim.sh) in
place of `docker compose`. It proves the two guarantees that matter most:

  1. A dump can be backed up and restored, and the restored data replaces the
     live database (with the previous DB preserved as a *_recovery_* database).
  2. A restore that FAILS VALIDATION leaves the live database completely
     untouched (the non-destructive-swap P0 guarantee) — verified on real PG.

Runs only when ACP_PG_INTEGRATION=1 and psql/pg_dump are available (i.e. in the
dedicated CI job). Skipped locally by default.
"""
import os
import shutil
import stat
import subprocess
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKUP = REPO_ROOT / "scripts" / "backup_db.sh"
RESTORE = REPO_ROOT / "scripts" / "restore_db.sh"
SHIM = REPO_ROOT / "scripts" / "ci" / "pg_compose_shim.sh"

pytestmark = pytest.mark.skipif(
    os.environ.get("ACP_PG_INTEGRATION") != "1"
    or shutil.which("psql") is None
    or shutil.which("pg_dump") is None,
    reason="real-PostgreSQL integration test (set ACP_PG_INTEGRATION=1 with psql/pg_dump)",
)

PGUSER = os.environ.get("PGUSER", "postgres")


def psql(dbname, sql, check=True):
    """Run a scalar SQL statement against dbname via libpq env; return stdout."""
    r = subprocess.run(
        ["psql", "-U", PGUSER, "-d", dbname, "-v", "ON_ERROR_STOP=1", "-tAc", sql],
        capture_output=True, text=True,
    )
    if check:
        assert r.returncode == 0, f"psql failed: {sql}\n{r.stderr}"
    return r.stdout.strip()


@pytest.fixture
def dbname():
    name = f"acp_it_{uuid.uuid4().hex[:12]}"
    psql("postgres", f'DROP DATABASE IF EXISTS "{name}";')
    psql("postgres", f'CREATE DATABASE "{name}";')
    # Minimal schema the restore validation/smoke checks require.
    psql(name, "CREATE TABLE alembic_version (version_num varchar(64) PRIMARY KEY);")
    psql(name, "INSERT INTO alembic_version VALUES ('e0f1a2b3c4d5');")
    psql(name, "CREATE TABLE organizations (id serial PRIMARY KEY, name text);")
    psql(name, "INSERT INTO organizations (name) VALUES ('acme');")
    yield name
    # Cleanup: the live DB, any recovery/failed siblings, and the target itself.
    rows = psql(
        "postgres",
        "SELECT datname FROM pg_database WHERE datname LIKE '" + name + "%';",
    )
    for db in [d for d in rows.splitlines() if d]:
        psql("postgres", f'ALTER DATABASE "{db}" WITH ALLOW_CONNECTIONS true;', check=False)
        psql("postgres", f'DROP DATABASE IF EXISTS "{db}";', check=False)


def _env(dbname):
    env = dict(os.environ)
    env.update({"COMPOSE": str(SHIM), "POSTGRES_USER": PGUSER, "POSTGRES_DB": dbname})
    return env


def run(script, args, dbname):
    SHIM.chmod(SHIM.stat().st_mode | stat.S_IEXEC)
    return subprocess.run(
        ["sh", str(script), *args],
        capture_output=True, text=True, env=_env(dbname), stdin=subprocess.DEVNULL,
    )


def test_backup_then_restore_round_trip(tmp_path, dbname):
    bdir = tmp_path / "backups"
    env = _env(dbname)
    env["BACKUP_DIR"] = str(bdir)
    b = subprocess.run(["sh", str(BACKUP)], capture_output=True, text=True, env=env,
                       stdin=subprocess.DEVNULL)
    assert b.returncode == 0, b.stdout + b.stderr
    dumps = list(bdir.glob("acp-*.sql.gz"))
    assert len(dumps) == 1

    # Mutate the live DB after the backup; the restore must revert this.
    psql(dbname, "INSERT INTO organizations (name) VALUES ('sentinel_after_backup');")
    assert psql(dbname, "SELECT count(*) FROM organizations;") == "2"

    r = run(RESTORE, [str(dumps[0]), "--confirm", dbname], dbname)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "Restore complete" in r.stdout
    # Restored to the backed-up state (only 'acme'); sentinel is gone.
    assert psql(dbname, "SELECT count(*) FROM organizations;") == "1"
    assert psql(dbname, "SELECT name FROM organizations;") == "acme"
    # The previous DB is preserved as a recovery database.
    recovery = psql("postgres",
                    "SELECT datname FROM pg_database WHERE datname LIKE '" + dbname + "_recovery_%';")
    assert recovery.startswith(f"{dbname}_recovery_")
    # Explicit, separate deletion of the recovery database works on real PG.
    d = run(RESTORE, ["--drop-recovery", recovery, "--confirm", recovery], dbname)
    assert d.returncode == 0, d.stdout + d.stderr
    assert psql("postgres",
                "SELECT count(*) FROM pg_database WHERE datname='" + recovery + "';") == "0"


def test_post_swap_rollback_restores_previous_on_real_pg(tmp_path, dbname):
    """Real-PG post-swap rollback: an injected smoke failure after promotion
    rolls back to the previous database; the active DB is never lost."""
    bdir = tmp_path / "backups"
    env = _env(dbname)
    env["BACKUP_DIR"] = str(bdir)
    b = subprocess.run(["sh", str(BACKUP)], capture_output=True, text=True, env=env,
                       stdin=subprocess.DEVNULL)
    assert b.returncode == 0, b.stdout + b.stderr
    dump = next(iter(bdir.glob("acp-*.sql.gz")))

    # Mark the live DB so we can prove it survived the failed restore.
    psql(dbname, "INSERT INTO organizations (name) VALUES ('live_before_restore');")
    before = psql(dbname, "SELECT count(*) FROM organizations;")

    # Force the post-swap smoke test to fail (isolated, safe injection).
    env2 = _env(dbname)
    env2["RESTORE_SMOKE_SQL"] = "SELECT false;"
    r = subprocess.run(["sh", str(RESTORE), str(dump), "--confirm", dbname],
                       capture_output=True, text=True, env=env2, stdin=subprocess.DEVNULL)
    assert r.returncode == 10, r.stdout + r.stderr
    # Rolled back: the live DB is intact (still has the marker row).
    assert psql(dbname, "SELECT count(*) FROM organizations;") == before
    assert psql(dbname, "SELECT count(*) FROM organizations WHERE name='live_before_restore';") == "1"
    # The suspect restore is preserved as a *_failed_* database for inspection.
    failed = psql("postgres",
                  "SELECT count(*) FROM pg_database WHERE datname LIKE '" + dbname + "_failed_%';")
    assert failed == "1"


def test_failed_validation_leaves_live_db_untouched(tmp_path, dbname):
    """A dump that loads but fails validation must NOT touch the live DB."""
    # Build a dump of a DB WITHOUT an organizations table -> validation fails.
    other = f"{dbname}_src"
    psql("postgres", f'DROP DATABASE IF EXISTS "{other}";')
    psql("postgres", f'CREATE DATABASE "{other}";')
    psql(other, "CREATE TABLE alembic_version (version_num varchar(64) PRIMARY KEY);")
    dump = tmp_path / "bad.sql.gz"
    with open(dump, "wb") as fh:
        d = subprocess.run(["pg_dump", "-U", PGUSER, "-d", other, "--no-owner"],
                           stdout=subprocess.PIPE, check=True)
        subprocess.run(["gzip"], input=d.stdout, stdout=fh, check=True)
    psql("postgres", f'DROP DATABASE IF EXISTS "{other}";')

    before = psql(dbname, "SELECT count(*) FROM organizations;")
    r = run(RESTORE, [str(dump), "--confirm", dbname], dbname)
    assert r.returncode == 6  # validation failure
    # Live DB is completely untouched.
    assert psql(dbname, "SELECT count(*) FROM organizations;") == before
    # No recovery DB was created (we never entered the swap).
    recoveries = psql("postgres",
                      "SELECT count(*) FROM pg_database WHERE datname LIKE '" + dbname + "_recovery_%';")
    assert recoveries == "0"
