"""Source-centric routing — the deterministic rule layer.

The router was evolved from *business-centric* ("does this sound like a contract
question?") to *source-centric* ("could an uploaded source contain the answer?"). These
tests pin that behaviour at the deterministic ``rule_route`` layer — the offline floor
beneath the LLM router — so document-evidence questions (authors, recipients, parties,
emails, valuations) route to PDF instead of NONE, while existing business routing
(SQL / HYBRID / honest-NONE) is preserved byte-for-byte.

Pure-function and hermetic: ``rule_route`` needs no engine, corpus, network, or API key,
so these are fast and fully deterministic regardless of embedding backend.

Run:  .venv/bin/python -m pytest tests/test_source_centric_routing.py -q
"""
from __future__ import annotations

import os

# Settings is lru_cached on first read — force the offline floor before importing app.
os.environ.setdefault("ABA_OFFLINE_MODE", "always")
os.environ.setdefault("ABA_EMBEDDING_BACKEND", "hashing")
os.environ.setdefault("ABA_ENABLE_RERANK", "false")

import pytest  # noqa: E402

from app.retrieval.intent import detect_intent  # noqa: E402
from app.routing.classify import rule_route  # noqa: E402


# --- NEW: document-evidence questions must route to PDF, not NONE -------------
# These are answerable from an uploaded document but carry NO contract-clause
# vocabulary. Under the old business-centric rules they fell through to NONE.
@pytest.mark.parametrize("question", [
    "Who prepared this document?",
    "Who is the recipient?",
    "What is the author's email?",
    "Who are the parties to this agreement?",
    "Which company authored this report?",
    "What valuation amount is proposed?",
    "Who was this proposal prepared for?",
    "What is the recipient's phone number?",
    "Who signed the document?",
    "Which organization created this report?",
])
def test_document_evidence_questions_route_pdf(question):
    decision = rule_route(question)
    assert decision.route == "PDF", (
        f"{question!r} routed to {decision.route}, expected PDF (a document could state it)")


# --- existing business routing must be preserved -----------------------------
@pytest.mark.parametrize("question,expected", [
    # pure SQL — structured aggregation, no document evidence
    ("What is the total outstanding invoice amount per customer?", "SQL"),
    ("How many invoices are overdue?", "SQL"),
    # contract / document clause questions
    ("What do our contracts say about service suspension?", "PDF"),
    ("Which contract clauses mention SLA-2025?", "PDF"),
    # agentic HYBRID — DB rows then their documents
    ("Which customers have overdue invoices, and what do their agreements say "
     "about service suspension?", "HYBRID"),
    ("What contracts expire in the next 90 days, and what penalties do they define?", "HYBRID"),
    ("Show all active projects and summarize the risks in their documentation.", "HYBRID"),
    # genuinely unanswerable from any source — insufficient evidence
    ("What is our employee headcount in Berlin?", "NONE"),
    ("What is the weather forecast for tomorrow?", "NONE"),
])
def test_business_routing_preserved(question, expected):
    assert rule_route(question).route == expected


def test_hebrew_questions_stay_in_scope():
    """Hebrew clause questions route to documents (never NONE) — RTL corpus support."""
    decision = rule_route("מה אומר ההסכם של תבור מערכות על השעיית שירות וקנסות?")
    assert decision.route in ("PDF", "HYBRID")
    assert decision.languages == ["he"]


def test_none_reasoning_is_evidence_framed_not_scope_framed():
    """NONE is 'insufficient evidence', never 'out of scope' — the system reasons about
    evidence availability, not whether a question is business-related."""
    reason = rule_route("What is our employee headcount in Berlin?").reasoning.lower()
    assert "insufficient evidence" in reason
    assert "out of scope" not in reason


def test_evidence_keyword_plus_sql_keyword_is_hybrid():
    """A document-evidence term AND a structured term → needs both sources."""
    decision = rule_route(
        "Which customers are overdue, and who signed their agreements?")
    assert decision.route == "HYBRID"


# --- the "90 days" keyword-gate trap (regression) ----------------------------
# A bare integer must NOT hard-gate retrieval (it derailed the agentic HYBRID document
# step), while genuine alphanumeric/hyphenated identifiers still anchor an exact match.
@pytest.mark.parametrize("query,is_keyword", [
    ("Which document mentions INI-MSA-2024?", True),            # hyphenated id → gate
    ("Which contract clauses mention SLA-2025?", True),         # hyphenated id → gate
    ("penalties for contracts expiring in the next 90 days", False),  # bare int → no gate
    ("what penalties apply within 30 days of termination", False),    # bare int → no gate
])
def test_bare_integer_does_not_hard_gate(query, is_keyword):
    assert (detect_intent(query).mode == "keyword") is is_keyword


def test_real_identifiers_still_gate():
    """The keyword-precision feature is intact: the exact id is kept as a gate term."""
    intent = detect_intent("Which contract clauses mention SLA-2025?")
    assert intent.mode == "keyword"
    assert "SLA-2025" in intent.gate_terms
