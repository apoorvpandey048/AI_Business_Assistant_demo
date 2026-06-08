"""SQL safety layer.

The model never touches the database directly. Generated SQL is parsed with sqlglot
and only allowed through if it is a single, read-only SELECT (or WITH…SELECT) over
known tables. A LIMIT is injected if missing. Anything else is rejected with a reason.
"""
from __future__ import annotations

from typing import Optional

import sqlglot
from sqlglot import exp

_FORBIDDEN = (
    exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter,
    exp.Command, exp.Pragma, exp.Set,
)


class SQLValidationError(Exception):
    pass


def validate_select(
    sql: str, allowed_tables: set[str], row_limit: int = 200
) -> str:
    """Return a safe, LIMIT-bounded SELECT, or raise SQLValidationError."""
    sql = (sql or "").strip().rstrip(";").strip()
    if not sql:
        raise SQLValidationError("empty query")

    try:
        statements = sqlglot.parse(sql, dialect="sqlite")
    except Exception as exc:
        raise SQLValidationError(f"parse error: {exc}") from exc

    statements = [s for s in statements if s is not None]
    if len(statements) != 1:
        raise SQLValidationError("only a single statement is allowed")

    tree = statements[0]

    # Top-level must be a SELECT (optionally wrapped in WITH / set ops / subquery)
    if not isinstance(tree, (exp.Select, exp.Union, exp.With, exp.Subquery)):
        raise SQLValidationError(f"only SELECT queries are allowed (got {type(tree).__name__})")

    for node in tree.walk():
        node = node[0] if isinstance(node, tuple) else node
        if isinstance(node, _FORBIDDEN):
            raise SQLValidationError(f"forbidden statement type: {type(node).__name__}")

    # Table allow-list
    used = {t.name for t in tree.find_all(exp.Table) if t.name}
    unknown = used - allowed_tables
    if unknown:
        raise SQLValidationError(f"unknown table(s): {sorted(unknown)}")

    # Inject a LIMIT on the outermost SELECT if absent
    select = tree.find(exp.Select)
    if select is not None and select.args.get("limit") is None:
        select.set("limit", exp.Limit(expression=exp.Literal.number(row_limit)))

    return tree.sql(dialect="sqlite")


def referenced_tables(sql: str) -> list[str]:
    try:
        tree = sqlglot.parse_one(sql, dialect="sqlite")
        return sorted({t.name for t in tree.find_all(exp.Table) if t.name})
    except Exception:
        return []


def primary_table(sql: str) -> Optional[str]:
    """The driving table in the FROM clause — the right label for result rows."""
    try:
        tree = sqlglot.parse_one(sql, dialect="sqlite")
        from_ = tree.find(exp.From)
        if from_ is not None:
            tbl = from_.find(exp.Table)
            if tbl is not None and tbl.name:
                return tbl.name
    except Exception:
        pass
    tables = referenced_tables(sql)
    return tables[0] if tables else None
