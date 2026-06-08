"""Schema-aware SQL generation.

Live: Claude turns a natural-language sub-question into ONE read-only SELECT,
constrained by the schema and the demo date. Offline: a deterministic rule library
covers the demo intents (overdue invoices, expiring contracts, active projects,
outstanding balances) so the pipeline stays fully functional without a key.
"""
from __future__ import annotations

import re

from app.config import get_settings
from app.llm.client import get_llm

TODAY = "2026-06-08"

_SQL_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "sql": {"type": "string", "description": "A single read-only SQLite SELECT query."},
        "rationale": {"type": "string", "description": "One sentence on what the query returns."},
    },
    "required": ["sql", "rationale"],
}

_SYSTEM = (
    "You are a careful analytics engineer. Translate the user's question into exactly ONE "
    "read-only SQLite SELECT query. Rules: SELECT only — never INSERT/UPDATE/DELETE/DDL. "
    f"Use ONLY the given tables and columns. Today's date is {TODAY}; dates are ISO 'YYYY-MM-DD' "
    "strings, compare with date(). Use the exact VALUES listed for enum-like columns (e.g. "
    "status). Prefer explicit JOINs.\n"
    "Column selection (important): ALWAYS return the columns the question is about (e.g. the "
    "date columns for 'expire/expiring', amount columns for 'total/outstanding', status), PLUS "
    "human-readable identifiers (customer name, *_ref, title) AND any linking columns that point "
    "to source documents (pdf_file, doc_file) or entities (customer_id). NEVER return only id "
    "columns — results must be self-explanatory on their own. Return JSON only."
)


def _fallback_sql(nl: str) -> dict[str, str]:
    """Deterministic SQL for the demo intents, used when no LLM is available."""
    q = nl.lower()
    if "overdue" in q:
        return {
            "sql": (
                "SELECT c.id AS customer_id, c.name AS customer, i.invoice_ref, "
                "i.amount_usd, i.due_date "
                "FROM invoices i JOIN customers c ON c.id = i.customer_id "
                "WHERE i.status = 'overdue' ORDER BY i.due_date"
            ),
            "rationale": "Invoices with status 'overdue' and their customers.",
        }
    if "expir" in q or ("contract" in q and ("90" in q or "next" in q or "soon" in q)):
        return {
            "sql": (
                "SELECT c.name AS customer, ct.contract_ref, ct.title, ct.pdf_file, "
                "ct.end_date, ct.value_usd "
                "FROM contracts ct JOIN customers c ON c.id = ct.customer_id "
                f"WHERE ct.status = 'active' AND date(ct.end_date) BETWEEN date('{TODAY}') "
                f"AND date('{TODAY}', '+90 day') ORDER BY ct.end_date"
            ),
            "rationale": "Active contracts whose end_date falls within the next 90 days.",
        }
    if "active" in q and "project" in q:
        return {
            "sql": (
                "SELECT p.project_ref, p.name AS project, c.name AS customer, p.status, "
                "p.target_end_date, p.doc_file "
                "FROM projects p JOIN customers c ON c.id = p.customer_id "
                "WHERE p.status = 'active' ORDER BY p.target_end_date"
            ),
            "rationale": "Projects with status 'active' and their customers.",
        }
    if "outstanding" in q or ("total" in q and "invoice" in q) or "owe" in q:
        return {
            "sql": (
                "SELECT c.name AS customer, "
                "SUM(CASE WHEN i.status IN ('overdue','pending') THEN i.amount_usd ELSE 0 END) "
                "AS outstanding_usd "
                "FROM customers c JOIN invoices i ON i.customer_id = c.id "
                "GROUP BY c.id HAVING outstanding_usd > 0 ORDER BY outstanding_usd DESC"
            ),
            "rationale": "Outstanding (overdue + pending) invoice amounts per customer.",
        }
    # safe default
    return {
        "sql": "SELECT id, name, industry, country FROM customers ORDER BY name",
        "rationale": "Fallback: list of customers (no specific intent matched offline).",
    }


def generate_sql(nl_query: str, schema_text: str, entity_hint: str | None = None):
    s = get_settings()
    llm = get_llm()
    user = f"Schema:\n{schema_text}\n\nQuestion: {nl_query}"
    if entity_hint:
        user += f"\nContext: {entity_hint}"
    data, call = llm.structured(
        purpose="sql_generation", model=s.model_sql, system=_SYSTEM, user=user,
        schema=_SQL_SCHEMA, fallback=lambda: _fallback_sql(nl_query),
    )
    return data.get("sql", ""), data.get("rationale", ""), call
