"""Regression tests — Hebrew / mixed-language intent detection and retrieval.

Production incident (client demo, June 2026): the first Hebrew question worked, the
second returned "insufficient evidence". Root cause chain:
1. Content tokens were ASCII-only, so a Hebrew question containing ONE Latin token
   (name / identifier) looked "term-dominated" → forced keyword mode.
2. The keyword gate required the term verbatim; "SLA2025" ≠ "SLA-2025" and
   "Tavor" ≠ "תבור" → zero evidence.
3. The safety net re-ran retrieval, which re-detected the same keyword intent →
   zero again → honest-sounding but WRONG "insufficient evidence".

Run:  .venv/bin/python -m pytest tests/test_multilingual_intent.py -q
"""
from __future__ import annotations

import pytest

from app.retrieval.intent import (content_terms, detect_intent, term_in_text,
                                  text_hits)

# --- pure-function: Unicode content tokens -----------------------------------

def test_content_terms_include_hebrew():
    terms = content_terms("מה אומר ההסכם של תבור על קנסות?")
    assert "ההסכם" in terms and "תבור" in terms and "קנסות" in terms
    assert "מה" not in terms and "של" not in terms          # Hebrew stopwords dropped


def test_content_terms_mixed_language():
    terms = content_terms("מה ההסכם של תבור אומר על SLA2025?")
    assert "sla2025" in terms
    assert "תבור" in terms                                   # Hebrew counts as content


# --- pure-function: a Hebrew question with one Latin token stays semantic ----

@pytest.mark.parametrize("q", [
    "מה ההסכם של תבור אומר על SLA2025?",
    "אילו קנסות מוגדרים בהסכם של Tavor?",
])
def test_mixed_hebrew_not_term_dominated(q):
    # Pre-fix: ASCII-only content tokens made these look "term-dominated" → keyword
    # mode → verbatim gate → zero evidence. They are fact-extraction questions and
    # must be semantic.
    assert detect_intent(q).mode == "semantic"


def test_pure_hebrew_semantic():
    assert detect_intent("מה אומר ההסכם של תבור מערכות על השעיית שירות?").mode == "semantic"


def test_english_keyword_lookup_still_keyword():
    intent = detect_intent("Which document mentions INI-MSA-2024?")
    assert intent.mode == "keyword"
    assert "INI-MSA-2024" in intent.gate_terms


# --- pure-function: Hebrew prefix-tolerant matching ---------------------------

@pytest.mark.parametrize("term,text,expected", [
    ("בהסכם", "הסכם שירותים זה נכרת בין הצדדים", True),   # ב prefix stripped
    ("ולחוזה", "חוזה ההתקשרות", True),                      # ו+ל double prefix
    ("קנס", "ייווסף קנס פיגורים", True),                    # plain containment
    ("הסכם", "אין כאן שום דבר", False),
    ("suspension", "Provider may suspend the Services", False),  # no stemming for Latin
    ("suspend", "Provider may suspend the Services", True),
])
def test_term_in_text_prefix_tolerance(term, text, expected):
    assert term_in_text(term, text) is expected


def test_text_hits_hebrew_prefixes():
    assert text_hits("ייווסף קנס פיגורים בשיעור 1.5%", ["הקנס"]) is True


# --- engine-level: the incident questions now answer --------------------------

@pytest.mark.parametrize("question", [
    "מה ההסכם של תבור אומר על SLA2025?",       # Latin id not verbatim (SLA-2025)
    "אילו קנסות מוגדרים בהסכם של Tavor?",       # Latin name; doc says תבור
])
def test_mixed_language_questions_recover(sample_engine, question):
    resp = sample_engine.ask(question, scope="all")
    assert not resp.insufficient, resp.answer
    docs = {e.document for e in resp.trace.evidence if e.document}
    assert "TAVOR_Contract_HE.pdf" in docs, f"evidence docs: {docs}"


def test_hebrew_demo_question_still_works(sample_engine):
    resp = sample_engine.ask("מה אומר ההסכם של תבור מערכות על השעיית שירות וקנסות?",
                             scope="all")
    assert not resp.insufficient
    assert any(e.document == "TAVOR_Contract_HE.pdf" for e in resp.trace.evidence)


def test_hebrew_out_of_scope_still_declines(sample_engine):
    # Honest grounding must survive the recall fixes: a Hebrew question with no
    # lexical/semantic overlap with the corpus still declines.
    resp = sample_engine.ask("מה תחזית מזג האוויר מחר בתל אביב?", scope="all")
    assert resp.insufficient, resp.answer
