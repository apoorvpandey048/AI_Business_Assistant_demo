"""Regression tests — the evidence panel contract (trustworthy citations).

Client report: evidence was displayed that did not support the answer, and an
"insufficient evidence" answer showed (previous/irrelevant) evidence. Contract now:
- ``citations`` contains ONLY evidence whose id the answer verifiably cited —
  there is no "fall back to everything retrieved";
- ``used`` flags mirror the verified citation ids exactly;
- an insufficient answer with no inline citations exposes no citations at all.

Run:  .venv/bin/python -m pytest tests/test_evidence_relevance.py -q
"""
from __future__ import annotations


def test_citations_subset_of_verified_cited_ids(sample_engine):
    resp = sample_engine.ask("What do our contracts say about service suspension?",
                             scope="all")
    assert resp.trace.citation_check is not None
    cited = set(resp.trace.citation_check.cited_ids)
    assert {c.id for c in resp.citations} <= cited
    # used flags mirror the same verified set — answer, chips, and inspector agree
    for e in resp.trace.evidence:
        assert e.used == (e.id in cited)


def test_insufficient_answer_exposes_no_citations(sample_engine):
    resp = sample_engine.ask("What is our employee headcount in Berlin?", scope="all")
    assert resp.insufficient
    assert resp.citations == []
    assert not any(e.used for e in resp.trace.evidence)


def test_no_all_evidence_fallback(sample_engine):
    # Every citation must be one of the answer's cited ids; uncited retrieved
    # evidence may appear ONLY in the trace (Inspector), never as a citation.
    resp = sample_engine.ask("What penalties do the contracts define?", scope="all")
    assert resp.trace.evidence, "expected evidence for an answerable question"
    cited = set(resp.trace.citation_check.cited_ids)
    for c in resp.citations:
        assert c.id in cited, f"citation {c.id} was never cited by the answer"
