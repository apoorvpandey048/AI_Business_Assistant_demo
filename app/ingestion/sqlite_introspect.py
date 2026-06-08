"""SQLite schema introspection.

Produces a schema description (for schema-aware SQL generation) and a capability
profile (for the router, so it knows what the structured source can answer).
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Column:
    name: str
    type: str
    pk: bool = False
    values: list[str] | None = None  # distinct values for low-cardinality text columns


@dataclass
class Table:
    name: str
    columns: list[Column] = field(default_factory=list)
    row_count: int = 0
    foreign_keys: list[tuple[str, str, str]] = field(default_factory=list)  # (col, ref_table, ref_col)
    sample: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class SchemaInfo:
    tables: list[Table] = field(default_factory=list)

    def schema_text(self) -> str:
        lines = []
        for t in self.tables:
            cols = ", ".join(
                f"{c.name} {c.type}" + (" PRIMARY KEY" if c.pk else "")
                for c in t.columns
            )
            lines.append(f"TABLE {t.name} ({cols})")
            for col, ref_t, ref_c in t.foreign_keys:
                lines.append(f"    FOREIGN KEY {t.name}.{col} -> {ref_t}.{ref_c}")
            # Surface enum-like values so the model uses real categories (e.g. status).
            for c in t.columns:
                if c.values:
                    vals = ", ".join(repr(v) for v in c.values)
                    lines.append(f"    VALUES {t.name}.{c.name} ∈ {{{vals}}}")
        return "\n".join(lines)

    def table_names(self) -> list[str]:
        return [t.name for t in self.tables]

    def capabilities(self) -> list[str]:
        return [f"{t.name} ({t.row_count} rows)" for t in self.tables]


def introspect(db_path: Path) -> SchemaInfo:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    names = [
        r[0] for r in cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
    ]
    _SKIP = ("date", "ref", "email", "file", "pdf", "doc")

    def _enum_values(table: str, col: Column) -> list[str] | None:
        t = (col.type or "").upper()
        if col.pk or "INT" in t or "REAL" in t or col.name.endswith("_id"):
            return None
        if any(s in col.name.lower() for s in _SKIP):
            return None
        try:
            rows = cur.execute(
                f"SELECT DISTINCT {col.name} FROM {table} "
                f"WHERE {col.name} IS NOT NULL LIMIT 9"
            ).fetchall()
        except Exception:
            return None
        vals = [str(r[0]) for r in rows]
        return vals if 0 < len(vals) <= 8 else None

    tables: list[Table] = []
    for name in names:
        cols = [
            Column(name=r["name"], type=r["type"] or "", pk=bool(r["pk"]))
            for r in cur.execute(f"PRAGMA table_info({name})").fetchall()
        ]
        for c in cols:
            c.values = _enum_values(name, c)
        fks = [
            (r["from"], r["table"], r["to"])
            for r in cur.execute(f"PRAGMA foreign_key_list({name})").fetchall()
        ]
        count = cur.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
        sample = [dict(r) for r in cur.execute(f"SELECT * FROM {name} LIMIT 2").fetchall()]
        tables.append(Table(name=name, columns=cols, row_count=count, foreign_keys=fks, sample=sample))
    con.close()
    return SchemaInfo(tables=tables)
