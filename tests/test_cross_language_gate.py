"""Sprint 15 — Phase 4: cross-language safety-net relevance gate.

Regression for the he->en bug: the lexical _on_topic gate cannot pass evidence that is
in a DIFFERENT script from the question (a Hebrew query shares no surface token with an
English passage), so semantically-retrieved cross-language evidence was being discarded
and the answer declined — the sprint's forbidden "answer exists but system says no
evidence" failure. The fix gates cross-script recoveries on the dense (semantic) score.

These tests exercise the deterministic helpers directly (no LLM / no embedding model):
_is_cross_script and _cross_script_relevant.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.routing.orchestrator import _is_cross_script, _cross_script_relevant
from app.models import Evidence


def _ev(cid: str, content: str) -> Evidence:
    return Evidence(id=cid, source_name="documents", source_kind="documents",
                    content=content, citation_label=f"[{cid}]", chunk_id=cid)


@dataclass
class _Cand:
    chunk_id: str
    dense_score: float


@dataclass
class _Trace:
    candidates: list = field(default_factory=list)


# --- cross-script detection ---------------------------------------------------------

def test_hebrew_question_english_evidence_is_cross_script():
    ev = [_ev("c1", "Patient: Mohammad Ben Diagnosis: Dementia")]
    assert _is_cross_script("מה האבחנה של מוחמד בן?", ev) is True


def test_english_question_hebrew_evidence_is_cross_script():
    ev = [_ev("c1", "מטופל: מוחמד בן אבחנה דמנציה")]
    assert _is_cross_script("What is the diagnosis?", ev) is True


def test_same_script_hebrew_is_not_cross_script():
    ev = [_ev("c1", "מטופל: מוחמד בן אבחנה דמנציה")]
    assert _is_cross_script("מה האבחנה?", ev) is False


def test_same_script_english_is_not_cross_script():
    ev = [_ev("c1", "Patient: Mohammad Ben Diagnosis: Dementia")]
    assert _is_cross_script("What is the diagnosis?", ev) is False


def test_no_evidence_is_not_cross_script():
    assert _is_cross_script("anything", []) is False


# --- semantic relevance floor -------------------------------------------------------

def test_relevant_cross_language_passes_floor():
    ev = [_ev("c1", "Diagnosis: Dementia")]
    tr = _Trace(candidates=[_Cand("c1", 0.55)])
    assert _cross_script_relevant(ev, tr, floor=0.42) is True


def test_offtopic_cross_language_fails_floor():
    ev = [_ev("c1", "Donepezil 10 mg daily")]
    tr = _Trace(candidates=[_Cand("c1", 0.34)])
    assert _cross_script_relevant(ev, tr, floor=0.42) is False


def test_missing_dense_score_trusts_generation():
    # no dense scores available → do not block (generation + language guard still apply)
    ev = [_ev("c1", "x")]
    tr = _Trace(candidates=[])
    assert _cross_script_relevant(ev, tr, floor=0.42) is True


def test_uses_top_evidence_chunk_score():
    ev = [_ev("c1", "Diagnosis: Dementia")]
    tr = _Trace(candidates=[_Cand("c1", 0.50), _Cand("c9", 0.10)])
    assert _cross_script_relevant(ev, tr, floor=0.42) is True
