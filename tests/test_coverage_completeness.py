"""Phase 2 — coverage-complete retrieval ("no facts missed").

Locks the guarantees that an enumeration / multi-fact question returns the COMPLETE set
of relevant passages rather than a fixed top-k, while a plain single-fact question (and
the honest-decline path) is unchanged so the precision batteries don't regress.

Unit tests for intent / expansion / gap detection always run. The retrieval-shape tests
run against the real sample PDFs when present and are skipped otherwise.

Run:  .venv/bin/python -m pytest tests/test_coverage_completeness.py -q
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.retrieval.completeness import find_gaps
from app.retrieval.expand import expand_queries
from app.retrieval.intent import is_enumeration

PDF_DIR = Path(__file__).resolve().parent.parent / "data" / "uploads" / "pdfs"


def _has(name: str) -> bool:
    return (PDF_DIR / name).exists()


# --- enumeration intent ------------------------------------------------------------
@pytest.mark.parametrize("q", [
    "list every incident in the record",
    "what are all the medications",
    "how many hospital transfers were there",
    "enumerate the assets",
    "כל התרופות של מוחמד",
    "כמה אירועים היו",
])
def test_enumeration_detected(q):
    assert is_enumeration(q) is True


@pytest.mark.parametrize("q", [
    "what is the surgeon's name",
    "who is the primary physician",
    "what is the diagnosis",
    "מה האבחנה",
])
def test_non_enumeration_not_flagged(q):
    assert is_enumeration(q) is False


# --- query expansion ---------------------------------------------------------------
def test_expand_splits_compound_question_into_aspects():
    ex = expand_queries("what penalties and suspension clauses exist")
    joined = " ".join(ex).lower()
    assert "penalties" in joined and "suspension" in joined
    # the original query is never echoed back as its own expansion
    assert "what penalties and suspension clauses exist" not in [e.lower() for e in ex]


def test_expand_preserves_caller_extras_and_dedupes():
    ex = expand_queries("list all risks", extra=["project risks", "project risks"])
    assert ex.count("project risks") == 1


# --- completeness gap detection ----------------------------------------------------
def test_find_gaps_flags_uncovered_term():
    gaps = find_gaps("what did Dr. Hall and Dr. Feldman decide",
                     ["Dr. Hall performed the surgery"])
    # Feldman appears in no evidence passage → a gap; Hall is covered → not a gap
    assert any("feldman" in g.lower() for g in gaps)
    assert not any(g.lower() == "hall" for g in gaps)


def test_find_gaps_empty_when_all_covered():
    assert find_gaps("the ORIF procedure", ["the ORIF procedure was successful"]) == []


def test_find_gaps_no_targets_no_gaps():
    # a question with no distinctive content terms cannot have gaps
    assert find_gaps("what is it", ["anything"]) == []


# --- retrieval shape on real PDFs --------------------------------------------------
def _index():
    from app.ingestion.pdf import ingest_pdf
    from app.retrieval.document_retriever import DocumentIndex
    docs = [ingest_pdf(p) for p in sorted(PDF_DIR.glob("*.pdf"))]
    chunks = [c.as_dict() for d in docs for c in d.chunks]
    idx = DocumentIndex()
    idx.build(chunks)
    return idx


@pytest.mark.skipif(not _has("nursing_home_.pdf"), reason="sample upload not present")
def test_enumeration_returns_more_than_single_fact():
    idx = _index()
    nh = {"documents": ["nursing_home_.pdf"]}
    single, _ = idx.retrieve("what is the surgeon's name?", filters=nh)
    every, etr = idx.retrieve(
        "list every incident and hospital transfer in the nursing record", filters=nh)
    assert etr.enumeration is True
    assert len(single) <= idx.s.final_k
    # enumeration must surface substantially more of the document
    assert len(every) > idx.s.final_k


@pytest.mark.skipif(not _has("nursing_home_.pdf"), reason="sample upload not present")
def test_enumeration_never_exceeds_cap():
    idx = _index()
    ev, _ = idx.retrieve("list every single detail and record and note and item",
                         filters={"documents": ["nursing_home_.pdf"]})
    assert len(ev) <= idx.s.coverage_max_k


@pytest.mark.skipif(not _has("nursing_home_.pdf"), reason="sample upload not present")
def test_single_fact_unchanged_no_enumeration_no_fill():
    idx = _index()
    ev, tr = idx.retrieve("who is the attending surgeon?",
                          filters={"documents": ["nursing_home_.pdf"]})
    assert tr.enumeration is False
    assert tr.completeness_gaps == []      # fill never fires on a non-enumeration
    assert len(ev) <= idx.s.final_k
