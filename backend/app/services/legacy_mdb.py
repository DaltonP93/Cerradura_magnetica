"""Importer for the legacy Access database (iCCard3000.mdb).

Uses the `mdbtools` command line utilities (`mdb-tables`, `mdb-export`) to
extract the tables, finds the one that carries the consumer data (columns
compatible with ConsumerNO / Name / CardID / Department), and feeds it to the
same CSV import pipeline used for Excel exports. mdbtools is installed in the
backend Docker image; on bare-metal installs: `apt-get install mdbtools`.
"""
import subprocess
from collections.abc import Callable

from sqlalchemy.orm import Session

from app.services.importer import HEADER_ALIASES, ImportSummary, import_cardholders_csv

# (command, mdb_path, table_or_None) -> stdout bytes
Runner = Callable[[list[str]], bytes]


class MdbToolsNotAvailable(RuntimeError):
    pass


def _run(cmd: list[str]) -> bytes:
    try:
        return subprocess.run(cmd, capture_output=True, check=True, timeout=60).stdout
    except FileNotFoundError as exc:
        raise MdbToolsNotAvailable(
            "mdbtools is not installed on the server (apt-get install mdbtools)"
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise ValueError(f"{cmd[0]} failed: {exc.stderr.decode(errors='replace')[:200]}") from exc


def list_tables(mdb_path: str, run: Runner | None = None) -> list[str]:
    run = run or _run  # resolved at call time so tests can substitute the runner
    output = run(["mdb-tables", "-1", mdb_path]).decode("utf-8", errors="replace")
    return [t.strip() for t in output.splitlines() if t.strip()]


def export_table(mdb_path: str, table: str, run: Runner | None = None) -> bytes:
    return (run or _run)(["mdb-export", mdb_path, table])


def _headers_of(csv_bytes: bytes) -> set[str]:
    first_line = csv_bytes.split(b"\n", 1)[0].decode("utf-8", errors="replace")
    return {h.strip().strip('"').lower().replace(" ", "") for h in first_line.split(",")}


def _table_score(headers: set[str]) -> int:
    """How many canonical import fields this table provides."""
    mapped = {HEADER_ALIASES[h] for h in headers if h in HEADER_ALIASES}
    if not {"name", "card_number"}.issubset(mapped):
        return 0
    return len(mapped)


def import_mdb(
    db: Session, organization_id: int, mdb_path: str, run: Runner | None = None
) -> tuple[ImportSummary, str]:
    """Find the consumer table in the .mdb and import it.

    Returns (summary, source_table). Raises ValueError if no table fits.
    """
    tables = list_tables(mdb_path, run)
    if not tables:
        raise ValueError("No tables found in the .mdb file")

    best: tuple[int, str, bytes] | None = None
    for table in tables:
        try:
            csv_bytes = export_table(mdb_path, table, run)
        except ValueError:
            continue
        score = _table_score(_headers_of(csv_bytes))
        if score > 0 and (best is None or score > best[0]):
            best = (score, table, csv_bytes)

    if best is None:
        raise ValueError(
            "No table with consumer columns (Name + CardID) found. "
            f"Tables in file: {', '.join(tables[:20])}"
        )
    return import_cardholders_csv(db, organization_id, best[2]), best[1]
