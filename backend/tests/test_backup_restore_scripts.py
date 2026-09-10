"""Behavioral tests for scripts/backup_db.sh and scripts/restore_db.sh.

These exercise the shell scripts with a FAKE, STATEFUL `docker compose` that
tracks which databases exist (in $FAKE_DBSTATE) so the restore's signal-driven
reconciliation — which reads server truth — can be tested deterministically.
No real PostgreSQL is involved here; a real end-to-end test lives in
test_backup_restore_integration.py (CI only).

Core guarantees locked in:
  * failures are never reported as success;
  * the live database is NEVER destroyed before a validated replacement exists;
  * signals mid-swap reconcile safely (rollback), never delete on ambiguity;
  * an abandoned lock fails closed with an explicit recovery path.
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

# Stateful fake `docker compose`. Tracks DB existence in $FAKE_DBSTATE and logs
# every psql -c / -tAc statement to $FAKE_LOG. FAKE_MODE injects failures.
FAKE_COMPOSE = r"""#!/usr/bin/env sh
DBSTATE="$FAKE_DBSTATE"
first_id() { printf '%s' "$1" | grep -oE '"[A-Za-z0-9_]+"' | sed -n '1p' | tr -d '"'; }
second_id() { printf '%s' "$1" | grep -oE '"[A-Za-z0-9_]+"' | sed -n '2p' | tr -d '"'; }
has() { grep -qxF "$1" "$DBSTATE" 2>/dev/null; }
add() { has "$1" || echo "$1" >> "$DBSTATE"; }
del() { grep -vxF "$1" "$DBSTATE" > "$DBSTATE.t" 2>/dev/null || true; mv "$DBSTATE.t" "$DBSTATE" 2>/dev/null || true; }

sub=""
for a in "$@"; do case "$a" in pg_dump) sub=pg_dump; break;; psql) sub=psql; break;; esac; done

if [ "$sub" = pg_dump ]; then
  [ "${FAKE_MODE:-}" = pg_dump_fail ] && exit 1
  echo "-- fake pg_dump output"; echo "CREATE TABLE t(id int);"; exit 0
fi

if [ "$sub" = psql ]; then
  mode=admin; sql=""; want=0
  for a in "$@"; do
    if [ "$want" = 1 ]; then sql="$a"; want=0; continue; fi
    case "$a" in -tAc) mode=scalar; want=1 ;; -c) mode=exec; want=1 ;; -q) mode=load ;; esac
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
      *pg_database*)
        name=$(printf '%s' "$sql" | sed -n "s/.*datname='\([^']*\)'.*/\1/p")
        if has "$name"; then echo 1; else echo ""; fi; exit 0 ;;
      *to_regclass*)
        [ "${FAKE_MODE:-}" = validate_exit_fail ] && { echo t; exit 1; }
        [ "${FAKE_MODE:-}" = validate_fail ] && { echo f; exit 0; }
        echo t; exit 0 ;;
      *organizations*|*count*)
        [ "${FAKE_MODE:-}" = smoke_fail ] && { echo f; exit 0; }
        echo t; exit 0 ;;
      *) echo t; exit 0 ;;
    esac
  fi

  if [ "$mode" = exec ]; then
    echo "EXEC: $sql" >> "$FAKE_LOG"
    # Failure injection BEFORE applying state.
    case "$sql" in
      *'RENAME TO "access_control_recovery_'*)
        [ "${FAKE_MODE:-}" = rename_active_fail ] && exit 1 ;;
      *'"access_control_restore_'*'RENAME TO "access_control"'*)
        [ "${FAKE_MODE:-}" = block_promote ] && sleep 30
        case "${FAKE_MODE:-}" in rename_temp_fail|rollback_fail) exit 1 ;; esac ;;
      *'"access_control_recovery_'*'RENAME TO "access_control"'*)
        [ "${FAKE_MODE:-}" = rollback_fail ] && exit 1 ;;
    esac
    # Apply state transition.
    case "$sql" in
      CREATE\ DATABASE*) add "$(first_id "$sql")" ;;
      DROP\ DATABASE*) del "$(first_id "$sql")" ;;
      *RENAME\ TO*)
        s=$(first_id "$sql"); d=$(second_id "$sql")
        if has "$s"; then del "$s"; add "$d"; fi ;;
    esac
    exit 0
  fi

  cat >/dev/null 2>&1 || true; exit 0
fi
cat >/dev/null 2>&1 || true; exit 0
"""


@pytest.fixture
def fake(tmp_path):
    compose = tmp_path / "fake_compose.sh"
    compose.write_text(FAKE_COMPOSE)
    compose.chmod(compose.stat().st_mode | stat.S_IEXEC)
    dbstate = tmp_path / "dbstate"
    dbstate.write_text("access_control\n")  # the live DB exists at start
    workdir = tmp_path / "work"
    workdir.mkdir()
    return {
        "compose": compose,
        "log": tmp_path / "compose.log",
        "dbstate": dbstate,
        "lock": tmp_path / "restore.lock",
        "workdir": workdir,
        "tmp": tmp_path,
    }


def _env(fake, mode=None, extra=None):
    env = dict(os.environ)
    env.update({
        "COMPOSE": str(fake["compose"]),
        "FAKE_LOG": str(fake["log"]),
        "FAKE_DBSTATE": str(fake["dbstate"]),
        "POSTGRES_USER": "acp",
        "POSTGRES_DB": "access_control",
        "TMPDIR": str(fake["workdir"]),
        "RESTORE_LOCKDIR": str(fake["lock"]),
    })
    if mode:
        env["FAKE_MODE"] = mode
    if extra:
        env.update(extra)
    return env


def run(script, args, fake, mode=None, extra=None):
    return subprocess.run(["sh", str(script), *args], capture_output=True, text=True,
                          env=_env(fake, mode, extra), stdin=subprocess.DEVNULL)


def make_gzip(path, content=b"-- dump\nCREATE TABLE t(id int);\n"):
    with gzip.open(path, "wb") as fh:
        fh.write(content)


def log_text(fake):
    return fake["log"].read_text() if fake["log"].exists() else ""


def dbs(fake):
    return [d for d in fake["dbstate"].read_text().splitlines() if d]


# --- backup -----------------------------------------------------------------
def test_backup_fails_when_pg_dump_fails(fake, tmp_path):
    r = run(BACKUP, [], fake, mode="pg_dump_fail", extra={"BACKUP_DIR": str(tmp_path / "b")})
    assert r.returncode != 0 and "Backup complete" not in r.stdout


def test_backup_leaves_no_dump_on_failure(fake, tmp_path):
    bdir = tmp_path / "b"
    run(BACKUP, [], fake, mode="pg_dump_fail", extra={"BACKUP_DIR": str(bdir)})
    assert list(bdir.glob("acp-*.sql.gz")) + list(bdir.glob(".acp-*")) == []


def test_backup_happy_path_publishes_valid_gzip(fake, tmp_path):
    bdir = tmp_path / "b"
    r = run(BACKUP, [], fake, mode="happy", extra={"BACKUP_DIR": str(bdir)})
    assert r.returncode == 0
    dumps = list(bdir.glob("acp-*.sql.gz"))
    assert len(dumps) == 1
    with gzip.open(dumps[0], "rb") as fh:
        assert b"fake pg_dump output" in fh.read()


def test_backup_rejects_bad_retention(fake, tmp_path):
    r = run(BACKUP, [], fake, mode="happy",
            extra={"BACKUP_DIR": str(tmp_path / "b"), "RETENTION_DAYS": "; rm -rf /"})
    assert r.returncode == 2


# --- restore: pre-flight validation ----------------------------------------
def test_restore_rejects_corrupt_gzip_before_touching_db(fake, tmp_path):
    bad = tmp_path / "bad.sql.gz"
    bad.write_bytes(b"not gzip")
    r = run(RESTORE, [str(bad), "--confirm", "access_control"], fake)
    assert r.returncode == 4 and log_text(fake) == ""


def test_restore_rejects_invalid_db_name(fake, tmp_path):
    dump = tmp_path / "d.sql.gz"
    make_gzip(dump)
    r = run(RESTORE, [str(dump), "--confirm", "bad;name"], fake, extra={"POSTGRES_DB": "bad;name"})
    assert r.returncode == 2 and log_text(fake) == ""


def test_restore_rejects_reserved_db(fake, tmp_path):
    dump = tmp_path / "d.sql.gz"
    make_gzip(dump)
    r = run(RESTORE, [str(dump), "--confirm", "postgres"], fake, extra={"POSTGRES_DB": "postgres"})
    assert r.returncode == 2


def test_restore_requires_exact_confirmation(fake, tmp_path):
    dump = tmp_path / "d.sql.gz"
    make_gzip(dump)
    r = run(RESTORE, [str(dump), "--confirm", "wrong"], fake)
    assert r.returncode == 3 and log_text(fake) == ""


# --- restore: failures never swap ------------------------------------------
def test_restore_load_failure_does_not_swap(fake, tmp_path):
    dump = tmp_path / "d.sql.gz"
    make_gzip(dump)
    r = run(RESTORE, [str(dump), "--confirm", "access_control"], fake, mode="load_fail")
    assert r.returncode == 5
    assert 'RENAME TO' not in log_text(fake)
    assert dbs(fake) == ["access_control"]  # active intact, temp cleaned


def test_restore_validation_failure_does_not_swap(fake, tmp_path):
    dump = tmp_path / "d.sql.gz"
    make_gzip(dump)
    r = run(RESTORE, [str(dump), "--confirm", "access_control"], fake, mode="validate_fail")
    assert r.returncode == 6
    assert 'RENAME TO' not in log_text(fake)
    assert dbs(fake) == ["access_control"]


def test_restore_validation_nonzero_exit_after_printing_t_does_not_swap(fake, tmp_path):
    dump = tmp_path / "d.sql.gz"
    make_gzip(dump)
    r = run(RESTORE, [str(dump), "--confirm", "access_control"], fake, mode="validate_exit_fail")
    assert r.returncode == 6
    assert 'RENAME TO' not in log_text(fake)


def test_restore_rename_active_failure_keeps_live_db(fake, tmp_path):
    dump = tmp_path / "d.sql.gz"
    make_gzip(dump)
    r = run(RESTORE, [str(dump), "--confirm", "access_control"], fake, mode="rename_active_fail")
    assert r.returncode == 7
    assert "live DB intact" in (r.stdout + r.stderr)
    assert "access_control" in dbs(fake)
    assert not any(d.startswith("access_control_recovery_") for d in dbs(fake))


def test_restore_promote_failure_rolls_back(fake, tmp_path):
    dump = tmp_path / "d.sql.gz"
    make_gzip(dump)
    r = run(RESTORE, [str(dump), "--confirm", "access_control"], fake, mode="rename_temp_fail")
    assert r.returncode == 8
    assert "rollback OK" in (r.stdout + r.stderr)
    assert "access_control" in dbs(fake)  # active restored


def test_restore_fatal_rollback_preserves_temp_and_recovery(fake, tmp_path):
    """Requirement: a fatal rollback really keeps BOTH temp and recovery, and
    the message names exactly what is preserved; the lock is kept."""
    dump = tmp_path / "d.sql.gz"
    make_gzip(dump)
    r = run(RESTORE, [str(dump), "--confirm", "access_control"], fake, mode="rollback_fail")
    assert r.returncode == 9
    assert "FATAL" in (r.stdout + r.stderr)
    current = dbs(fake)
    assert any(d.startswith("access_control_recovery_") for d in current), current
    assert any(d.startswith("access_control_restore_") for d in current), current
    # Message names exactly the preserved objects.
    rec = next(d for d in current if d.startswith("access_control_recovery_"))
    assert rec in (r.stdout + r.stderr)
    # Lock is kept for manual recovery (fail closed).
    assert fake["lock"].exists()


def test_restore_smoke_failure_rolls_back_and_keeps_previous(fake, tmp_path):
    dump = tmp_path / "d.sql.gz"
    make_gzip(dump)
    r = run(RESTORE, [str(dump), "--confirm", "access_control"], fake, mode="smoke_fail")
    assert r.returncode == 10
    assert "rolled back to previous" in (r.stdout + r.stderr)
    assert "access_control" in dbs(fake)
    assert any(d.startswith("access_control_failed_") for d in dbs(fake))


def test_restore_happy_path_preserves_previous_db(fake, tmp_path):
    dump = tmp_path / "d.sql.gz"
    make_gzip(dump)
    r = run(RESTORE, [str(dump), "--confirm", "access_control"], fake, mode="happy")
    assert r.returncode == 0
    assert "Restore complete" in r.stdout and "Previous database preserved" in r.stdout
    assert 'DROP DATABASE IF EXISTS "access_control_recovery_' not in log_text(fake)
    assert "access_control" in dbs(fake)
    assert any(d.startswith("access_control_recovery_") for d in dbs(fake))
    assert list(fake["workdir"].glob("tmp*")) == []  # mktemp -d cleaned
    assert not fake["lock"].exists()  # lock released


# --- mutex / lock recovery -------------------------------------------------
def test_restore_refuses_when_lock_held(fake, tmp_path):
    dump = tmp_path / "d.sql.gz"
    make_gzip(dump)
    fake["lock"].mkdir()
    r = run(RESTORE, [str(dump), "--confirm", "access_control"], fake, mode="happy")
    assert r.returncode == 75 and log_text(fake) == ""


def test_restore_abandoned_lock_fails_closed_with_recovery_hint(fake, tmp_path):
    dump = tmp_path / "d.sql.gz"
    make_gzip(dump)
    fake["lock"].mkdir()
    (fake["lock"] / "journal").write_text(
        "pid=999999\nutc=2026-01-01T00:00:00Z\ntarget=access_control\nphase=ACTIVE_RENAMED\n"
        "temp=access_control_restore_x\nrecovery=access_control_recovery_x\n"
    )
    r = run(RESTORE, [str(dump), "--confirm", "access_control"], fake, mode="happy")
    assert r.returncode == 75
    assert "--release-lock" in (r.stdout + r.stderr)
    assert "ACTIVE_RENAMED" in (r.stdout + r.stderr)  # journal shown
    assert fake["lock"].exists()  # never auto-removed


def test_release_lock_refuses_when_owner_alive(fake):
    proc = subprocess.Popen(["sleep", "30"])
    try:
        fake["lock"].mkdir()
        (fake["lock"] / "journal").write_text(f"pid={proc.pid}\ntarget=access_control\n")
        r = run(RESTORE, ["--release-lock", "--confirm", "access_control"], fake)
        assert r.returncode == 4  # owner alive -> refuse
        assert fake["lock"].exists()
    finally:
        proc.terminate()
        proc.wait()


def test_release_lock_removes_dead_lock(fake):
    fake["lock"].mkdir()
    (fake["lock"] / "journal").write_text("pid=999999\ntarget=access_control\n")
    r = run(RESTORE, ["--release-lock", "--confirm", "access_control"], fake)
    assert r.returncode == 0 and not fake["lock"].exists()


# --- signals ---------------------------------------------------------------
def _spawn(fake, mode):
    return subprocess.Popen(["sh", str(RESTORE), "d.sql.gz", "--confirm", "access_control"],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            env=_env(fake, mode), stdin=subprocess.DEVNULL,
                            start_new_session=True, cwd=str(fake["tmp"]))


def _wait_lock(fake, timeout=10):
    end = time.time() + timeout
    while time.time() < end and not fake["lock"].exists():
        time.sleep(0.1)
    time.sleep(0.4)


def test_sigterm_during_load_pre_swap_keeps_active_and_drops_temp(fake):
    make_gzip(fake["tmp"] / "d.sql.gz")
    proc = _spawn(fake, "block")
    _wait_lock(fake)
    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    proc.communicate(timeout=10)
    assert proc.returncode != 0
    assert 'RENAME TO' not in log_text(fake)      # never swapped
    assert dbs(fake) == ["access_control"]        # active intact, temp dropped
    assert not fake["lock"].exists()              # lock released (resolved)


def test_sigterm_after_active_renamed_rolls_back_to_active(fake):
    """SIGTERM after active->recovery and during promotion: reconcile restores
    the active DB from recovery; the active database is never lost."""
    make_gzip(fake["tmp"] / "d.sql.gz")
    proc = _spawn(fake, "block_promote")
    _wait_lock(fake)
    # Wait until active->recovery has been applied (active no longer present).
    end = time.time() + 10
    while time.time() < end and "access_control" in dbs(fake):
        time.sleep(0.1)
    assert "access_control" not in dbs(fake)      # mid-swap: active renamed away
    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    _out, err = proc.communicate(timeout=10)
    assert proc.returncode != 0
    assert "access_control" in dbs(fake)          # reconciled: active restored
    assert (b"rollback" in err.lower()) or (b"reconcil" in err.lower())


# --- --drop-recovery -------------------------------------------------------
def test_drop_recovery_requires_matching_confirm(fake):
    r = run(RESTORE, ["--drop-recovery", "access_control_recovery_20260101", "--confirm", "nope"], fake)
    assert r.returncode == 3 and log_text(fake) == ""


def test_drop_recovery_refuses_non_recovery_name(fake):
    r = run(RESTORE, ["--drop-recovery", "access_control", "--confirm", "access_control"], fake)
    assert r.returncode == 2


def test_drop_recovery_refuses_while_restore_locked(fake):
    fake["lock"].mkdir()  # a restore holds the mutex
    name = "access_control_recovery_20260101000000"
    r = run(RESTORE, ["--drop-recovery", name, "--confirm", name], fake)
    assert r.returncode == 75 and log_text(fake) == ""


def test_drop_recovery_happy_path(fake):
    name = "access_control_recovery_20260101000000"
    r = run(RESTORE, ["--drop-recovery", name, "--confirm", name], fake)
    assert r.returncode == 0
    assert f'DROP DATABASE IF EXISTS "{name}"' in log_text(fake)
    assert not fake["lock"].exists()
