"""Relational (SQLite) source.

Generates schema-aware SQL, validates it (read-only), executes it, and turns each
row into fully-attributed Evidence (table, row key, exact SQL). Also exposes an
explicit entity → document linking step used by the agentic hybrid flow.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Optional

from app.config import get_settings
from app.ingestion.sqlite_introspect import SchemaInfo
from app.models import Evidence, SourceInfo, SqlExecutionTrace
from app.sql.execute import SQLExecutionError, execute_readonly
from app.sql.generate import generate_sql
from app.sql.validate import (SQLValidationError, primary_table, referenced_tables,
                              validate_select)

_KEY_COLS = ("invoice_ref", "contract_ref", "project_ref", "customer", "name")


def _row_key(row: dict[str, Any], table: str) -> str:
    for c in _KEY_COLS:
        if c in row and row[c] is not None:
            return str(row[c])
    if "id" in row:
        return f"{table}#{row['id']}"
    return table


def _row_text(row: dict[str, Any]) -> str:
    return "; ".join(f"{k}={v}" for k, v in row.items())


class RelationalSource:
    name = "business_db"
    kind = "relational"

    def __init__(self, db_path: Path, schema: SchemaInfo) -> None:
        self.db_path = db_path
        self.schema = schema
        self.s = get_settings()

    # -- description --------------------------------------------------------
    def describe(self) -> SourceInfo:
        # Data-driven description so the router sees the ACTUAL tables currently
        # registered (sample + any uploaded databases), not a hardcoded list.
        tables = self.schema.tables
        table_lines = []
        for t in tables:
            cols = ", ".join(c.name for c in t.columns[:8])
            more = "" if len(t.columns) <= 8 else ", …"
            table_lines.append(f"{t.name}({cols}{more})")
        table_summary = "; ".join(table_lines) if table_lines else "no tables yet"
        description = (
            f"Structured records in a SQLite database with {len(tables)} table(s): "
            f"{table_summary}."
        )
        return SourceInfo(
            name=self.name, kind="relational",
            title="Structured database (SQLite)",
            description=description,
            capabilities=[
                "counts, sums, averages, min/max, group-by and filters over the tables listed",
                "date-range, status and category filters; ranking and aggregation",
                f"available tables: {', '.join(t.name for t in tables) or 'none'}",
            ],
            status="active",
            details={
                "tables": self.schema.capabilities(),
                "schema": self.schema.schema_text(),
            },
        )

    def _scoped_schema_text(self, scoped: Optional[set[str]]) -> str:
        """Schema text limited to the tables in scope, so generated SQL only ever
        references tables the current scope is allowed to read."""
        if scoped is None:
            return self.schema.schema_text()
        sub = SchemaInfo(tables=[t for t in self.schema.tables if t.name in scoped])
        return sub.schema_text()

    # -- query --------------------------------------------------------------
    def run(
        self, nl_query: str, purpose: str = "sql", entity_hint: Optional[str] = None,
        allowed_tables: Optional[list[str]] = None,
    ) -> tuple[list[Evidence], SqlExecutionTrace, Any]:
        scoped = set(allowed_tables) if allowed_tables is not None else None
        sql, rationale, call = generate_sql(
            nl_query, self._scoped_schema_text(scoped), entity_hint=entity_hint
        )
        trace = SqlExecutionTrace(
            purpose=purpose, natural_language=nl_query, generated_sql=sql,
        )
        allowed = scoped if scoped is not None else set(self.schema.table_names())
        try:
            validated = validate_select(sql, allowed, row_limit=self.s.sql_row_limit)
            trace.validated_sql = validated
            trace.valid = True
            trace.tables = referenced_tables(validated)
        except SQLValidationError as exc:
            trace.valid = False
            trace.validation_error = str(exc)
            return [], trace, call

        t0 = time.perf_counter()
        try:
            columns, rows = execute_readonly(
                self.db_path, validated,
                timeout_seconds=self.s.sql_timeout_seconds, max_rows=self.s.sql_row_limit,
            )
        except SQLExecutionError as exc:
            trace.valid = False
            trace.validation_error = f"execution error: {exc}"
            return [], trace, call
        trace.duration_ms = round((time.perf_counter() - t0) * 1000, 1)
        trace.columns = columns
        trace.rows = rows
        trace.row_count = len(rows)

        primary = primary_table(validated) or (trace.tables[0] if trace.tables else self.name)
        evidence: list[Evidence] = []
        for i, row in enumerate(rows[:15]):
            key = _row_key(row, primary)
            evidence.append(Evidence(
                id=f"sql::{purpose}::{i}",
                source_name=self.name, source_kind="relational",
                content=_row_text(row),
                citation_label=f"[{self.name}: {primary} {key}]",
                table=primary, row_ids=[key], sql=validated, columns=columns,
            ))
        return evidence, trace, call

    # -- agentic linking step ----------------------------------------------
    def extract_customer_ids(self, rows: list[dict[str, Any]]) -> list[int]:
        ids: list[int] = []
        for r in rows:
            if "customer_id" in r and r["customer_id"] is not None:
                ids.append(int(r["customer_id"]))
            elif "id" in r and "name" in r and "industry" in r:  # a customers row
                ids.append(int(r["id"]))
        # de-dup, preserve order
        seen, out = set(), []
        for i in ids:
            if i not in seen:
                seen.add(i); out.append(i)
        return out

    def link_customers_to_documents(
        self, customer_ids: list[int]
    ) -> tuple[list[str], list[str], SqlExecutionTrace]:
        """Map customer ids → their contract PDFs (the entity→document bridge)."""
        ids_csv = ",".join(str(int(i)) for i in customer_ids) or "NULL"
        sql = (
            "SELECT c.name AS customer, ct.pdf_file "
            "FROM contracts ct JOIN customers c ON c.id = ct.customer_id "
            f"WHERE ct.customer_id IN ({ids_csv})"
        )
        trace = SqlExecutionTrace(
            purpose="entity_link", natural_language="link customers to their contract documents",
            generated_sql=sql,
        )
        try:
            validated = validate_select(sql, set(self.schema.table_names()), self.s.sql_row_limit)
            trace.validated_sql = validated
            trace.valid = True
            trace.tables = referenced_tables(validated)
            t0 = time.perf_counter()
            columns, rows = execute_readonly(self.db_path, validated, self.s.sql_timeout_seconds)
            trace.duration_ms = round((time.perf_counter() - t0) * 1000, 1)
            trace.columns = columns
            trace.rows = rows
            trace.row_count = len(rows)
        except (SQLValidationError, SQLExecutionError) as exc:
            trace.valid = False
            trace.validation_error = str(exc)
            return [], [], trace

        pdfs = [r["pdf_file"] for r in rows if r.get("pdf_file")]
        names = [r["customer"] for r in rows if r.get("customer")]
        return pdfs, names, trace
