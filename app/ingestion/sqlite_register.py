"""Register an uploaded SQLite database with the engine.

A customer uploads an arbitrary ``.db``/``.sqlite`` file. To make its tables queryable
through the existing single relational source — without redesigning the orchestrator —
we MERGE the uploaded tables into a working database that the ``RelationalSource`` is
bound to. The seed sample database is copied in first (so the flagship hybrid demo and
all existing behaviour keep working), then each uploaded file's tables are copied in with
collision-safe renaming.

The uploaded file itself is only ever read from (``CREATE TABLE ... AS SELECT``) — it is
never modified. The generic, read-only SQL path then answers questions over the new tables
immediately, with no code changes.
"""
from __future__ import annotations

import re
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path


def _sanitize(stem: str) -> str:
    s = re.sub(r"[^0-9a-zA-Z_]+", "_", stem).strip("_").lower()
    return s or "db"


def _q(identifier: str) -> str:
    """Safely quote a SQLite identifier."""
    return '"' + identifier.replace('"', '""') + '"'


@dataclass
class MergedTable:
    effective: str        # name as it now exists in the working DB
    original: str         # name in the uploaded file
    rows: int


def copy_seed(seed_path: Path, working_path: Path) -> None:
    """Initialise the working DB as a copy of the sample database."""
    working_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(seed_path, working_path)


def _user_tables(con: sqlite3.Connection, schema: str) -> list[str]:
    rows = con.execute(
        f"SELECT name FROM {schema}.sqlite_master "
        "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [r[0] for r in rows]


def merge_sqlite(
    upload_path: Path, working_path: Path, source_label: str | None = None
) -> list[MergedTable]:
    """Copy every user table from ``upload_path`` into ``working_path``.

    Returns the list of tables added (with their effective, possibly-renamed, names).
    On a name collision the table is suffixed with the (sanitised) source filename, then
    a counter — so nothing is ever silently overwritten.
    """
    working_path.parent.mkdir(parents=True, exist_ok=True)
    label = _sanitize(source_label or upload_path.stem)

    con = sqlite3.connect(str(working_path))
    try:
        con.execute("ATTACH DATABASE ? AS up", (str(upload_path),))
        existing = set(_user_tables(con, "main"))
        added: list[MergedTable] = []

        for original in _user_tables(con, "up"):
            effective = original
            if effective in existing:
                effective = f"{original}__{label}"
                n = 2
                while effective in existing:
                    effective = f"{original}__{label}_{n}"
                    n += 1
            con.execute(
                f"CREATE TABLE {_q(effective)} AS SELECT * FROM up.{_q(original)}"
            )
            existing.add(effective)
            rows = con.execute(f"SELECT COUNT(*) FROM {_q(effective)}").fetchone()[0]
            added.append(MergedTable(effective=effective, original=original, rows=int(rows)))

        con.commit()
        return added
    finally:
        try:
            con.execute("DETACH DATABASE up")
        except Exception:
            pass
        con.close()
