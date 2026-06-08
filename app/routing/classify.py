"""Intent classification & routing.

A hybrid router: a fast deterministic rule layer always runs (and is the offline
fallback), while Claude provides the primary, reasoned classification when available.
Output decides whether a question goes to documents, the database, both, or is
out of scope — and whether it needs the agentic SQL→entities→documents flow.
"""
from __future__ import annotations

import re

from app.config import get_settings
from app.llm.client import get_llm
from app.models import RouteDecision

_HEB = re.compile(r"[֐-׿]")

_ROUTE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "route": {"type": "string", "enum": ["PDF", "SQL", "HYBRID", "NONE"]},
        "reasoning": {"type": "string"},
        "confidence": {"type": "number"},
        "languages": {"type": "array", "items": {"type": "string"}},
        "document_subquery": {"type": "string"},
        "sql_subquery": {"type": "string"},
        "entity_hint": {"type": "string"},
        "agentic": {"type": "boolean"},
        "strategy_note": {"type": "string"},
    },
    "required": [
        "route", "reasoning", "confidence", "languages", "document_subquery",
        "sql_subquery", "entity_hint", "agentic", "strategy_note",
    ],
}

_SYSTEM = (
    "You are the query router for a multi-source business knowledge assistant. "
    "Given the available sources and a user question, decide the route:\n"
    "- PDF: answerable purely from contract/project DOCUMENTS (clauses, risks, definitions).\n"
    "- SQL: answerable purely from the structured DATABASE (counts, sums, dates, status).\n"
    "- HYBRID: needs BOTH (e.g. find rows in the DB, then read what the documents say).\n"
    "- NONE: not answerable from EITHER source — out of scope. Choose NONE when the "
    "question asks about data none of the listed sources contain (e.g. employee "
    "headcount, office locations, HR/payroll, marketing) — do NOT force a SQL or "
    "document lookup that cannot succeed.\n"
    "Set agentic=true when the document step depends on the SQL results (e.g. 'which "
    "customers are overdue AND what do their contracts say' → query DB for the customers, "
    "then retrieve only those customers' contracts). Provide a focused document_subquery "
    "(what to look up in the documents) and sql_subquery (what to ask the database). "
    "Detect language(s) ('en','he'). Return JSON only."
)

# --- deterministic rule layer (also the offline fallback) -------------------
_DOC_KW = ["penalt", "suspension", "suspend", "clause", "terminat", "sla",
           "risk", "mitigation", "define", "definition", "mention", "what do",
           "what does", "agreement say", "contract say", "documentation", "brief"]
_SQL_KW = ["overdue", "invoice", "outstanding", "owe", "how many", "number of",
           "total ", "expire", "expir", "due ", "unpaid", "paid", "pending",
           "balance", "list all", "how much", "per customer"]
_DOMAIN = ["contract", "invoice", "project", "customer", "agreement", "payment",
           "penalt", "suspension", "sla", "risk", "overdue"]
_HEB_DOC = ["השע", "קנס", "סעיף", "ביטול", "סיכון", "שירות"]  # suspension/penalty/clause/risk


def rule_route(question: str) -> RouteDecision:
    q = question.lower()
    langs = ["he"] if _HEB.search(question) else ["en"]
    has_doc = any(k in q for k in _DOC_KW) or any(k in question for k in _HEB_DOC)
    has_sql = any(k in q for k in _SQL_KW)
    in_domain = any(k in q for k in _DOMAIN) or langs == ["he"]

    agentic = False
    if "overdue" in q and (any(k in q for k in ["suspension", "suspend", "agreement", "contract", "say"])
                           or any(k in question for k in _HEB_DOC)):
        route, agentic = "HYBRID", True
    elif ("expir" in q or "expire" in q) and any(k in q for k in ["penalt", "clause", "terminat"]):
        route, agentic = "HYBRID", True
    elif "project" in q and "risk" in q:
        route, agentic = "HYBRID", True
    elif has_doc and has_sql:
        route = "HYBRID"
    elif has_sql:
        route = "SQL"
    elif has_doc:
        route = "PDF"
    elif in_domain:
        route = "PDF"
    else:
        route = "NONE"

    reasoning = {
        "PDF": "Document-only signals (clauses/risks/definitions); no structured lookup needed.",
        "SQL": "Structured-data signals (counts/dates/status); answerable from the database.",
        "HYBRID": "Needs both a database lookup and document evidence.",
        "NONE": "No signals matching the available document or database sources.",
    }[route]
    return RouteDecision(
        route=route, reasoning=f"[rules] {reasoning}",
        confidence=0.55 if route != "NONE" else 0.5, languages=langs,
        document_subquery=question, sql_subquery=question,
        entity_hint="entities returned by the SQL step" if agentic else "",
        agentic=agentic, strategy_note="deterministic rule layer",
    )


def classify(question: str, capability_brief: str):
    s = get_settings()
    llm = get_llm()
    fallback_decision = rule_route(question)

    def _fallback() -> dict:
        return fallback_decision.model_dump()

    user = f"Available sources:\n{capability_brief}\n\nQuestion: {question}"
    data, call = llm.structured(
        purpose="routing", model=s.model_router, system=_SYSTEM, user=user,
        schema=_ROUTE_SCHEMA, fallback=_fallback,
    )
    decision = RouteDecision(**data)
    if not decision.languages:
        decision.languages = fallback_decision.languages
    return decision, call
