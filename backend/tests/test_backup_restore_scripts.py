"""Behavioral tests for scripts/backup_db.sh and scripts/restore_db.sh.

These exercise the shell scripts with a FAKE `docker compose` command so no real
PostgreSQL is involved. They lock in the correctness guarantees that motivated
the hardening: failures must not be reported as success, the live database must
not be touched before the dump is validated, and temp artifacts are cleaned up.
"""
import gzip
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKUP = REPO_ROOT / "scripts" / "backup_db.sh"
RESTORE = REPO_ROOT / "scripts" / "restore_db.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("sh") is None or shutil.which("gzip") is None,
    reason="requires POSIX sh and gzip",
)

# A fake `docker compose` that emulates pg_dump/psql behavior driven by env vars.
FAKE_COMPOSE = r"""#!/usr/bin/env sh
echo "ARGS: $*" >> "$FAKE_LOG"
sub=""
for a in "$@"; do
  case "$a" in pg_dump) sub=pg_dump; break;; psql) sub=psql; break;; esac
done
if [ "$sub" = pg_dump ]; then
  [ "${FAKE_MODE:-}" = pg_dump_fail ] && exit 1
  echo "-- fake pg_dump output"
  echo "CREATE TABLE t(id int);"
  exit 0
fi
if [ "$sub" = psql ]; then
  input="$(cat)"
  case "$input" in *"RENAME TO"*) echo SWAP >> "$FAKE_SWAP" ;; esac
  for a in "$@"; do
    case "$a" in *to_regclass*)
      [ "${FAKE_MODE:-}" = validate_fail ] && { echo f; exit 0; }
      echo t; exit 0 ;;
    esac
  done
  is_load=no
  for a in "$@"; do [ "$a" = "-q" ] && is_load=yes; done
  if [ "$is_load" = yes ]; then
    [ "${FAKE_MODE:-}" = psql_load_fail ] && exit 1
    exit 0
  fi
  exit 0
fi
cat >/dev/null 2>&1 || true
exit 0
"""


@pytest.fixture
def fake(tmp_path):
    compose = tmp_path / "fake_compose.sh"
    compose.write_text(FAKE_COMPOSE)
    compose.chmod(compose.stat().st_mode | stat.S_IEXEC)
    log = tmp_path / "compose.log"
    swap = tmp_path / "swap.marker"
    workdir = tmp_path / "work"  # TMPDIR for restore's mktemp -d
    workdir.mkdir()
    return {"compose": compose, "log": log, "swap": swap, "workdir": workdir, "tmp": tmp_path}


def run(script, args, fake, mode=None, extra_env=None):
    env = dict(os.environ)
    env.update(
        {
            "COMPOSE": str(fake["compose"]),
            "FAKE_LOG": str(fake["log"]),
            "FAKE_SWAP": str(fake["swap"]),
            "POSTGRES_USER": "acp",
            "POSTGRES_DB": "access_control",
            "TMPDIR": str(fake["workdir"]),
        }
    )
    if mode:
        env["FAKE_MODE"] = mode
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["sh", str(script), *args],
        capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL,
    )


def make_gzip(path: Path, content: bytes = b"-- dump\nCREATE TABLE t(id int);\n"):
    with gzip.open(path, "wb") as fh:
        fh.write(content)


# --- backup -----------------------------------------------------------------
def test_backup_fails_when_pg_dump_fails(fake, tmp_path):
    """1. pg_dump failure must make the script fail (not a false success)."""
    backup_dir = tmp_path / "backups"
    r = run(BACKUP, [], fake, mode="pg_dump_fail", extra_env={"BACKUP_DIR": str(backup_dir)})
    assert r.returncode != 0, r.stdout + r.stderr
    assert "Backup complete" not in r.stdout


def test_backup_leaves_no_dump_on_failure(fake, tmp_path):
    """2. A failed backup must not leave a final dump or temp file behind."""
    backup_dir = tmp_path / "backups"
    run(BACKUP, [], fake, mode="pg_dump_fail", extra_env={"BACKUP_DIR": str(backup_dir)})
    leftovers = list(backup_dir.glob("acp-*.sql.gz")) + list(backup_dir.glob(".acp-*"))
    assert leftovers == [], leftovers


def test_backup_happy_path_publishes_valid_gzip(fake, tmp_path):
    """10a. Simulated happy path produces exactly one valid gzip and succeeds."""
    backup_dir = tmp_path / "backups"
    r = run(BACKUP, [], fake, mode="happy", extra_env={"BACKUP_DIR": str(backup_dir)})
    assert r.returncode == 0, r.stdout + r.stderr
    assert "Backup complete" in r.stdout
    dumps = list(backup_dir.glob("acp-*.sql.gz"))
    assert len(dumps) == 1
    with gzip.open(dumps[0], "rb") as fh:
        assert b"fake pg_dump output" in fh.read()
    assert list(backup_dir.glob(".acp-*")) == []  # no temp left


def test_backup_rejects_bad_retention(fake, tmp_path):
    backup_dir = tmp_path / "backups"
    r = run(BACKUP, [], fake, mode="happy",
            extra_env={"BACKUP_DIR": str(backup_dir), "RETENTION_DAYS": "; rm -rf /"})
    assert r.returncode == 2


# --- restore: validation before any destructive action ---------------------
def test_restore_rejects_corrupt_gzip_before_touching_db(fake, tmp_path):
    """3. Corrupt gzip must abort BEFORE any DB call (no DROP happens)."""
    bad = tmp_path / "bad.sql.gz"
    bad.write_bytes(b"this is not gzip")
    r = run(RESTORE, [str(bad), "--confirm", "access_control"], fake)
    assert r.returncode != 0
    assert "Restore complete" not in r.stdout
    assert not fake["log"].exists() or fake["log"].read_text() == ""  # DB never contacted


def test_restore_fails_when_psql_load_fails(fake, tmp_path):
    """4. A psql load failure fails the script and never swaps the live DB."""
    dump = tmp_path / "d.sql.gz"
    make_gzip(dump)
    r = run(RESTORE, [str(dump), "--confirm", "access_control"], fake, mode="psql_load_fail")
    assert r.returncode != 0
    assert "Restore complete" not in r.stdout
    assert not fake["swap"].exists()  # the live DB was never renamed/replaced


def test_restore_rejects_invalid_db_name(fake, tmp_path):
    """5. An invalid SQL identifier for the DB name is rejected up front."""
    dump = tmp_path / "d.sql.gz"
    make_gzip(dump)
    r = run(RESTORE, [str(dump), "--confirm", "bad;name"], fake,
            extra_env={"POSTGRES_DB": "bad;name"})
    assert r.returncode == 2
    assert not fake["log"].exists() or fake["log"].read_text() == ""


def test_restore_rejects_reserved_db(fake, tmp_path):
    """6. Reserved databases (postgres/template0/template1) are refused."""
    dump = tmp_path / "d.sql.gz"
    make_gzip(dump)
    r = run(RESTORE, [str(dump), "--confirm", "postgres"], fake,
            extra_env={"POSTGRES_DB": "postgres"})
    assert r.returncode == 2


def test_restore_requires_exact_confirmation(fake, tmp_path):
    """7. Confirmation must match the exact DB name; a generic flag is not enough."""
    dump = tmp_path / "d.sql.gz"
    make_gzip(dump)
    r = run(RESTORE, [str(dump), "--confirm", "wrong_name"], fake)
    assert r.returncode == 3
    assert not fake["log"].exists() or fake["log"].read_text() == ""


def test_restore_without_confirm_flag_is_usage_error(fake, tmp_path):
    dump = tmp_path / "d.sql.gz"
    make_gzip(dump)
    r = run(RESTORE, [str(dump)], fake)
    assert r.returncode == 2


def test_restore_fails_validation_does_not_swap(fake, tmp_path):
    """8. If the restored temp DB fails validation, the live DB is not swapped."""
    dump = tmp_path / "d.sql.gz"
    make_gzip(dump)
    r = run(RESTORE, [str(dump), "--confirm", "access_control"], fake, mode="validate_fail")
    assert r.returncode != 0
    assert "Restore complete" not in r.stdout
    assert not fake["swap"].exists()


def test_restore_happy_path_swaps_and_cleans_up(fake, tmp_path):
    """9 + 10b. Happy path succeeds, performs the swap, and cleans temp files."""
    dump = tmp_path / "d.sql.gz"
    make_gzip(dump)
    r = run(RESTORE, [str(dump), "--confirm", "access_control"], fake, mode="happy")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "Restore complete" in r.stdout
    assert fake["swap"].exists()  # the swap (RENAME TO) was issued
    # mktemp -d dir under TMPDIR must be cleaned up.
    assert list(fake["workdir"].iterdir()) == []
