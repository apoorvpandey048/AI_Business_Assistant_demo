"""Regression tests — the keyword gate must degrade, not silently fail.

Pre-fix behaviour: keyword intent + zero verbatim hits → empty evidence for EVERY
phrasing. Post-fix contract:
- a document-IDENTIFICATION lookup ("which document mentions X") with the term found
  nowhere still returns nothing — honesty beats guessing;
- a fact-EXTRACTION question that merely looked keyword-ish falls back to hybrid
  semantic retrieval on the original question, and the trace says so.

Run:  .venv/bin/python -m pytest tests/test_keyword_fallback.py -q
"""
from __future__ import annotations


def test_identification_lookup_with_missing_term_declines(sample_engine):
    resp = sample_engine.ask("Which document mentions ZZGX-9999?", scope="all")
    assert resp.insufficient
    assert not any(e.source_kind == "documents" for e in resp.trace.evidence)


def test_extraction_question_falls_back_to_semantic(sample_engine):
    # "SLA2025" is term-dominated but never appears verbatim (docs have "SLA-2025").
    # Pre-fix: keyword gate → zero evidence. Post-fix: semantic fallback answers.
    resp = sample_engine.ask("מה ההסכם של תבור אומר על SLA2025?", scope="all")
    assert not resp.insufficient
    assert resp.trace.evidence
    dr = resp.trace.document_retrieval
    assert dr is not None and dr.intent == "semantic"


def test_keyword_lookup_with_real_term_unchanged(sample_engine):
    # The precision behaviour that keyword mode exists for must be preserved:
    # an exact-id lookup returns ONLY the document that contains it.
    resp = sample_engine.ask("Which document mentions INI-MSA-2024?", scope="all")
    assert not resp.insufficient
    docs = {e.document for e in resp.trace.evidence}
    assert docs == {"INITECH_Agreement.pdf"}, docs
    assert resp.trace.document_retrieval.intent == "keyword"
