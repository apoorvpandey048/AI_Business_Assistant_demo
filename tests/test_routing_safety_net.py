"""Regression tests for the document-routing safety net.

Covers the production incident where answerable questions about uploaded PDFs were routed
to NONE / "insufficient evidence" without attempting retrieval. See
docs/root-cause-analysis.md and docs/fix-design.md.

Hermetic & deterministic: forced offline (no API key path) with hashing embeddings and the
reranker disabled, so there is no network and no large-model download. In this mode the
deterministic ``rule_route`` sends the incident questions to NONE — which is precisely the
condition the safety net must recover from, so it exercises the fix directly.

Run:  .venv/bin/python -m pytest tests/test_routing_safety_net.py -q
"""
from __future__ import annotations

import os

# Must be set before importing app modules (Settings is lru_cached on first read).
os.environ.setdefault("ABA_OFFLINE_MODE", "always")        # no live LLM → rule_route + extractive
os.environ.setdefault("ABA_EMBEDDING_BACKEND", "hashing")  # deterministic, offline
os.environ.setdefault("ABA_ENABLE_RERANK", "false")        # no model download

from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

from app.config import ROOT, get_settings  # noqa: E402
from app.engine import Engine  # noqa: E402
from app.retrieval.intent import content_terms, is_document_lookup  # noqa: E402

# (question, substring that must appear in the grounded evidence/answer)
INCIDENT_CASES = [
    ("Who was this proposal prepared for?", "Vincent Ochs"),
    ("Who prepared the IMM valuation document?", "Apoorv Pandey"),
    ("What is the proposed valuation amount?", "$450"),
    ("What is Apoorv Pandey's email address?", "apoorv.pandey.23cse@bmu.edu.in"),
    ("What university is Apoorv currently attending?", "BML Munjal University"),
]


def _incident_pdfs() -> list[Path]:
    wanted = [
        ["IMM_Prototype_Scope_and_Valuation.pdf"],
        ["Apoorv-Pandey-B.Tech.-ComputerScience_Engineering-2026-06-02-07-29-09-289628.pdf",
         "Apoorv-Pandey-B.Tech.-ComputerScience&Engineering-2026-06-02-07-29-09-289628.pdf"],
    ]
    dirs = [ROOT / "data" / "uploads" / "pdfs", ROOT]
    out: list[Path] = []
    for names in wanted:
        hit = next((d / n for d in dirs for n in names if (d / n).exists()), None)
        if hit:
            out.append(hit)
    return out


@pytest.fixture(scope="module")
def engine():
    pdfs = _incident_pdfs()
    if len(pdfs) < 2:
        pytest.skip("incident PDFs (IMM + resume) not present in data/uploads/pdfs or repo root")
    get_settings.cache_clear()
    eng = Engine()                                   # fresh; not the process-wide singleton
    for p in pdfs:
        info = eng.add_pdf(p.name, p)
        assert info.status == "indexed", f"upload failed: {info.error}"
    return eng


def _evidence_text(resp) -> str:
    return " ".join(e.content for e in resp.trace.evidence).lower()


# --- the five incident questions must now be answerable -----------------------
@pytest.mark.parametrize("question,expected", INCIDENT_CASES)
def test_incident_questions_recover(engine, question, expected):
    resp = engine.ask(question)
    # The answer must be grounded in retrieved evidence (the bug was zero retrieval).
    assert resp.trace.evidence, f"no evidence retrieved for: {question}"
    assert not resp.insufficient, f"still declined as insufficient: {question}"
    # The exact fact is present in the grounded evidence (robust to offline snippet
    # truncation in the extractive generator; the live LLM extracts it verbatim).
    assert expected.lower() in _evidence_text(resp), (
        f"expected {expected!r} in grounded evidence for: {question}")


def test_safety_net_actually_fires_on_router_none(engine):
    """Offline rule_route declines these → the net must be what recovers them."""
    resp = engine.ask("What university is Apoorv currently attending?")
    assert resp.trace.route.route == "NONE"          # the router still declined
    assert any("safety net" in n.lower() for n in resp.trace.notes), resp.trace.notes
    assert resp.trace.evidence                        # …but evidence was recovered anyway


# --- honest grounding must be preserved (no false answers) --------------------
@pytest.mark.parametrize("question", [
    "What is our employee headcount in Berlin?",      # the canonical out-of-scope example
    "What is the weather forecast for tomorrow?",
])
def test_out_of_scope_still_declined(engine, question):
    resp = engine.ask(question)
    # The on-topic gate must reject off-topic recoveries, so this stays honest.
    assert resp.insufficient, f"out-of-scope question was wrongly answered: {question}\n{resp.answer}"
    assert not any(e.source_kind == "documents" for e in resp.trace.evidence)


# --- existing routes must be undisturbed -------------------------------------
def test_sql_route_not_disturbed(engine):
    resp = engine.ask("What is the total outstanding invoice amount per customer?")
    assert resp.trace.route.route == "SQL"
    assert resp.trace.evidence and all(
        e.source_kind == "relational" for e in resp.trace.evidence)
    # net must not inject document evidence when SQL already answered
    assert not any("safety net" in n.lower() for n in resp.trace.notes)


def test_keyword_identification_preserved(engine):
    """A genuine 'which document mentions X' lookup still names the document (not extraction)."""
    resp = engine.ask("Which document mentions BML?")
    assert "appears in" in resp.answer.lower()
    assert "Apoorv" in resp.answer                    # the resume, identified by name


# --- pure-function unit tests for the intent gate ----------------------------
@pytest.mark.parametrize("q,expected", [
    ("Which document mentions INI-MSA-2024?", True),
    ("find the file containing SLA-2025", True),
    ("which contract clauses mention suspension", True),
    ("What is Apoorv Pandey's email address?", False),
    ("Who was this proposal prepared for?", False),
    ("What is the proposed valuation amount?", False),
])
def test_is_document_lookup(q, expected):
    assert is_document_lookup(q) is expected


def test_content_terms_drops_stopwords():
    terms = content_terms("What is Apoorv Pandey's email address?")
    assert "apoorv" in terms and "email" in terms
    assert "what" not in terms and "is" not in terms
