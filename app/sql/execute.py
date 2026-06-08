"""Read-only SQL execution with a wall-clock guard."""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any


class SQLExecutionError(Exception):
    pass


def execute_readonly(
    db_path: Path, sql: str, timeout_seconds: int = 5, max_rows: int = 500
) -> tuple[list[str], list[dict[str, Any]]]:
    # Open the database strictly read-only (no writes can ever reach it).
    uri = f"file:{db_path}?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row

    deadline = time.perf_counter() + timeout_seconds

    def _guard() -> int:
        return 1 if time.perf_counter() > deadline else 0

    con.set_progress_handler(_guard, 100_000)
    try:
        cur = con.execute(sql)
        columns = [d[0] for d in cur.description] if cur.description else []
        rows = [dict(r) for r in cur.fetchmany(max_rows)]
        return columns, rows
    except sqlite3.OperationalError as exc:
        raise SQLExecutionError(str(exc)) from exc
    finally:
        con.close()
