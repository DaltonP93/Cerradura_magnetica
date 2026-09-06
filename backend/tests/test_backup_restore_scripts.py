"""Behavioral tests for scripts/backup_db.sh and scripts/restore_db.sh.

These exercise the shell scripts with a FAKE `docker compose` command so no real
PostgreSQL is involved. They lock in the correctness guarantees that motivated
the hardening: failures are never reported as success, and — critically — the
live database is NEVER destroyed before a validated replacement is in place
(non-destructive swap with automatic rollback). A real-PostgreSQL end-to-end
test lives in test_backup_restore_integration.py (CI only).
"""
import gzip
import os
import shutil
import signal
import stat
import subprocess
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKUP = REPO_ROOT / "scripts" / "backup_db.sh"
RESTORE = REPO_ROOT / "scripts" / "restore_db.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("sh") is None or shutil.which("gzip") is None,
    reason="requires POSIX sh and gzip",
)

# Fake `docker compose`. Behavior is driven by FAKE_MODE. It logs every psql -c
# statement and every -tAc scalar query to FAKE_LOG so tests can assert exactly
# which renames/drops were (not) issued.
FAKE_COMPOSE = r"""#!/usr/bin/env sh
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
  # Classify the psql invocation.
  mode=admin; sql=""; want_next=0
  for a in "$@"; do
    if [ "$want_next" = 1 ]; then sql="$a"; want_next=0; continue; fi
    case "$a" in
      -tAc) mode=scalar; want_next=1 ;;
      -c) mode=exec; want_next=1 ;;
      -q) mode=load ;;
    esac
  done

  if [ "$mode" = load ]; then
    cat >/dev/null 2>&1 || true
    [ "${FAKE_MODE:-}" = block ] && sleep 30
    [ "${FAKE_MODE:-}" = load_fail ] && exit 1
    exit 0
  fi

  if [ "$mode" = scalar ]; then
    echo "SCALAR: $sql" >> "$FAKE_LOG"
    case "$sql" in
      *to_regclass*)
        [ "${FAKE_MODE:-}" = validate_exit_fail ] && { echo t; exit 1; }
        [ "${FAKE_MODE:-}" = validate_fail ] && { echo f; exit 0; }
        echo t; exit 0 ;;
      *organizations*)   # post-swap smoke test
        [ "${FAKE_MODE:-}" = smoke_fail ] && { echo f; exit 0; }
        echo t; exit 0 ;;
      *) echo t; exit 0 ;;
    esac
  fi

  if [ "$mode" = exec ]; then
    echo "EXEC: $sql" >> "$FAKE_LOG"
    case "$sql" in
      *'RENAME TO "access_control_recovery_'*)   # step 1: active -> recovery
        [ "${FAKE_MODE:-}" = rename_active_fail ] && exit 1 ;;
      *'"access_control_restore_'*'RENAME TO "access_control"'*)  # step 2: temp -> active
        case "${FAKE_MODE:-}" in rename_temp_fail|rollback_fail|smoke_fail_promote) exit 1 ;; esac ;;
      *'"access_control_recovery_'*'RENAME TO "access_control"'*)  # rollback: recovery -> active
        [ "${FAKE_MODE:-}" = rollback_fail ] && exit 1 ;;
    esac
    # smoke_fail promotes normally; only the smoke scalar fails.
    exit 0
  fi

  # bare admin psql (heredoc etc.)
  cat >/dev/null 2>&1 || true
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
    workdir = tmp_path / "work"
    workdir.mkdir()
    return {
        "compose": compose,
        "log": tmp_path / "compose.log",
        "lock": tmp_path / "restore.lock",
        "workdir": workdir,
        "tmp": tmp_path,
    }


def _env(fake, mode=None, extra=None):
    env = dict(os.environ)
    env.update(
        {
            "COMPOSE": str(fake["compose"]),
            "FAKE_LOG": str(fake["log"]),
            "POSTGRES_USER": "acp",
            "POSTGRES_DB": "access_control",
            "TMPDIR": str(fake["workdir"]),
            "RESTORE_LOCKDIR": str(fake["lock"]),
        }
    )
    if mode:
        env["FAKE_MODE"] = mode
    if extra:
        env.update(extra)
    return env


def run(script, args, fake, mode=None, extra=None):
    return subprocess.run(
        ["sh", str(script), *args],
        capture_output=True, text=True, env=_env(fake, mode, extra),
        stdin=subprocess.DEVNULL,
    )


def make_gzip(path: Path, content: bytes = b"-- dump\nCREATE TABLE t(id int);\n"):
    with gzip.open(path, "wb") as fh:
        fh.write(content)


def log_text(fake):
    return fake["log"].read_text() if fake["log"].exists() else ""


# --- backup -----------------------------------------------------------------
def test_backup_fails_when_pg_dump_fails(fake, tmp_path):
    r = run(BACKUP, [], fake, mode="pg_dump_fail", extra={"BACKUP_DIR": str(tmp_path / "b")})
    assert r.returncode != 0
    assert "Backup complete" not in r.stdout


def test_backup_leaves_no_dump_on_failure(fake, tmp_path):
    bdir = tmp_path / "b"
    run(BACKUP, [], fake, mode="pg_dump_fail", extra={"BACKUP_DIR": str(bdir)})
    assert list(bdir.glob("acp-*.sql.gz")) + list(bdir.glob(".acp-*")) == []


def test_backup_happy_path_publishes_valid_gzip(fake, tmp_path):
    bdir = tmp_path / "b"
    r = run(BACKUP, [], fake, mode="happy", extra={"BACKUP_DIR": str(bdir)})
    assert r.returncode == 0, r.stdout + r.stderr
    dumps = list(bdir.glob("acp-*.sql.gz"))
    assert len(dumps) == 1
    with gzip.open(dumps[0], "rb") as fh:
        assert b"fake pg_dump output" in fh.read()
    assert list(bdir.glob(".acp-*")) == []


def test_backup_rejects_bad_retention(fake, tmp_path):
    r = run(BACKUP, [], fake, mode="happy",
            extra={"BACKUP_DIR": str(tmp_path / "b"), "RETENTION_DAYS": "; rm -rf /"})
    assert r.returncode == 2


# --- restore: pre-flight validation ----------------------------------------
def test_restore_rejects_corrupt_gzip_before_touching_db(fake, tmp_path):
    bad = tmp_path / "bad.sql.gz"
    bad.write_bytes(b"not gzip")
    r = run(RESTORE, [str(bad), "--confirm", "access_control"], fake)
    assert r.returncode == 4
    assert log_text(fake) == ""  # DB never contacted


def test_restore_rejects_invalid_db_name(fake, tmp_path):
    dump = tmp_path / "d.sql.gz"
    make_gzip(dump)
    r = run(RESTORE, [str(dump), "--confirm", "bad;name"], fake, extra={"POSTGRES_DB": "bad;name"})
    assert r.returncode == 2
    assert log_text(fake) == ""


def test_restore_rejects_reserved_db(fake, tmp_path):
    dump = tmp_path / "d.sql.gz"
    make_gzip(dump)
    r = run(RESTORE, [str(dump), "--confirm", "postgres"], fake, extra={"POSTGRES_DB": "postgres"})
    assert r.returncode == 2


def test_restore_requires_exact_confirmation(fake, tmp_path):
    dump = tmp_path / "d.sql.gz"
    make_gzip(dump)
    r = run(RESTORE, [str(dump), "--confirm", "wrong"], fake)
    assert r.returncode == 3
    assert log_text(fake) == ""


def test_restore_without_confirm_flag_is_usage_error(fake, tmp_path):
    dump = tmp_path / "d.sql.gz"
    make_gzip(dump)
    assert run(RESTORE, [str(dump)], fake).returncode == 2


# --- restore: load / validation failures never swap ------------------------
def test_restore_load_failure_does_not_swap(fake, tmp_path):
    dump = tmp_path / "d.sql.gz"
    make_gzip(dump)
    r = run(RESTORE, [str(dump), "--confirm", "access_control"], fake, mode="load_fail")
    assert r.returncode == 5
    assert "Restore complete" not in r.stdout
    assert "RENAME TO" not in log_text(fake)  # live DB untouched


def test_restore_validation_failure_does_not_swap(fake, tmp_path):
    dump = tmp_path / "d.sql.gz"
    make_gzip(dump)
    r = run(RESTORE, [str(dump), "--confirm", "access_control"], fake, mode="validate_fail")
    assert r.returncode == 6
    assert "RENAME TO" not in log_text(fake)


def test_restore_validation_nonzero_exit_after_printing_t_does_not_swap(fake, tmp_path):
    """The validation prints 't' but psql exits non-zero: exit code is checked
    separately from the value (no `psql | grep`), so this must NOT swap."""
    dump = tmp_path / "d.sql.gz"
    make_gzip(dump)
    r = run(RESTORE, [str(dump), "--confirm", "access_control"], fake, mode="validate_exit_fail")
    assert r.returncode == 6
    assert "RENAME TO" not in log_text(fake)


# --- restore: the non-destructive swap and its rollbacks -------------------
def test_restore_rename_active_failure_keeps_live_db(fake, tmp_path):
    """If renaming the live DB to a recovery name fails, the live DB is intact."""
    dump = tmp_path / "d.sql.gz"
    make_gzip(dump)
    r = run(RESTORE, [str(dump), "--confirm", "access_control"], fake, mode="rename_active_fail")
    assert r.returncode == 7
    assert "live DB intact" in (r.stdout + r.stderr)
    # No promotion of the temp DB happened.
    assert 'RENAME TO "access_control"' not in log_text(fake)


def test_restore_promote_failure_rolls_back(fake, tmp_path):
    """If promoting the temp DB fails, the recovery DB is renamed back to live."""
    dump = tmp_path / "d.sql.gz"
    make_gzip(dump)
    r = run(RESTORE, [str(dump), "--confirm", "access_control"], fake, mode="rename_temp_fail")
    assert r.returncode == 8
    assert "rollback OK" in (r.stdout + r.stderr)
    # The rollback rename (recovery -> live) was issued.
    assert '"access_control_recovery_' in log_text(fake)


def test_restore_failed_rollback_is_reported_fatal(fake, tmp_path):
    dump = tmp_path / "d.sql.gz"
    make_gzip(dump)
    r = run(RESTORE, [str(dump), "--confirm", "access_control"], fake, mode="rollback_fail")
    assert r.returncode == 9
    assert "FATAL" in (r.stdout + r.stderr)


def test_restore_smoke_failure_rolls_back_and_keeps_previous(fake, tmp_path):
    dump = tmp_path / "d.sql.gz"
    make_gzip(dump)
    r = run(RESTORE, [str(dump), "--confirm", "access_control"], fake, mode="smoke_fail")
    assert r.returncode == 10
    assert "rolled back to previous" in (r.stdout + r.stderr)
    assert 'RENAME TO "access_control_failed_' in log_text(fake)


def test_restore_happy_path_preserves_previous_db(fake, tmp_path):
    dump = tmp_path / "d.sql.gz"
    make_gzip(dump)
    r = run(RESTORE, [str(dump), "--confirm", "access_control"], fake, mode="happy")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "Restore complete" in r.stdout
    assert "Previous database preserved" in r.stdout
    # The previous DB is preserved: NO drop of a *_recovery_* database happened.
    assert 'DROP DATABASE IF EXISTS "access_control_recovery_' not in log_text(fake)
    # temp files cleaned up.
    assert list(fake["workdir"].iterdir()) == []
    # lock released.
    assert not fake["lock"].exists()


def test_restore_refuses_when_another_restore_holds_the_lock(fake, tmp_path):
    dump = tmp_path / "d.sql.gz"
    make_gzip(dump)
    fake["lock"].mkdir()  # simulate a concurrent restore holding the mutex
    r = run(RESTORE, [str(dump), "--confirm", "access_control"], fake, mode="happy")
    assert r.returncode == 75
    assert log_text(fake) == ""  # never touched the DB


def test_restore_interrupted_by_sigterm_cleans_up_without_swapping(fake, tmp_path):
    """SIGTERM during the load must release the lock and not have swapped."""
    dump = tmp_path / "d.sql.gz"
    make_gzip(dump)
    proc = subprocess.Popen(
        ["sh", str(RESTORE), str(dump), "--confirm", "access_control"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=_env(fake, "block"),
        stdin=subprocess.DEVNULL, start_new_session=True,
    )
    # Wait until the lock is taken and the (blocking) load has started.
    deadline = time.time() + 10
    while time.time() < deadline and not fake["lock"].exists():
        time.sleep(0.1)
    time.sleep(0.5)
    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    proc.wait(timeout=10)
    assert proc.returncode != 0
    assert not fake["lock"].exists()  # cleanup released the mutex
    assert 'RENAME TO "access_control"' not in log_text(fake)  # no swap happened


# --- explicit recovery-drop action -----------------------------------------
def test_drop_recovery_requires_matching_confirm(fake):
    r = run(RESTORE, ["--drop-recovery", "access_control_recovery_20260101", "--confirm", "nope"], fake)
    assert r.returncode == 3
    assert log_text(fake) == ""


def test_drop_recovery_refuses_non_recovery_name(fake):
    r = run(RESTORE, ["--drop-recovery", "access_control", "--confirm", "access_control"], fake)
    assert r.returncode == 2


def test_drop_recovery_happy_path(fake):
    name = "access_control_recovery_20260101000000"
    r = run(RESTORE, ["--drop-recovery", name, "--confirm", name], fake)
    assert r.returncode == 0
    assert f'DROP DATABASE IF EXISTS "{name}"' in log_text(fake)
