"""Sprint 15 — Phase 2: Hebrew ingestion & entity regression tests.

Covers the Hebrew-parity ingestion fixes:
- Unicode identifier extraction (metadata + intent gate terms) — R3
- Hebrew sentence/clause chunk boundaries — R4
- Hebrew honorific normalization (entity dedup) — R5
- No corruption of logical- or visual-order Hebrew, mixed HE/EN searchability.

All deterministic, offline, embedding-independent.
"""
from __future__ import annotations

from app.ingestion.metadata import extract_metadata
from app.ingestion.pdf import detect_text_order, normalize_rtl, _best_break
from app.retrieval.intent import detect_intent
from app.retrieval.entity_index import normalize_entity


# --- R3: Hebrew / mixed-script identifiers ------------------------------------------

def test_metadata_extracts_hebrew_identifier():
    md = extract_metadata("חוזה מספר תיק-4582 פעיל")
    assert "תיק-4582" in md.get("identifiers", [])


def test_metadata_extracts_short_hebrew_code():
    md = extract_metadata("קוד מטופל: ח-001 במחלקה")
    assert "ח-001" in md.get("identifiers", [])


def test_metadata_plain_hebrew_words_are_not_identifiers():
    md = extract_metadata("מוחמד בן גיל 88 שנים")
    assert md.get("identifiers", []) == []


def test_metadata_still_extracts_ascii_identifier():
    md = extract_metadata("Clause references SLA-2025 and INV-1187.")
    ids = md.get("identifiers", [])
    assert "SLA-2025" in ids and "INV-1187" in ids


def test_metadata_mixed_script_chunk_keeps_both():
    md = extract_metadata("ההסכם SLA-2025 והתיק תיק-4582 מקושרים")
    ids = md.get("identifiers", [])
    assert "SLA-2025" in ids and "תיק-4582" in ids


def test_intent_hebrew_identifier_becomes_gate_term():
    intent = detect_intent("איזה מסמך מזכיר את תיק-4582?")
    assert any("תיק-4582" in t for t in intent.gate_terms), intent.gate_terms


# --- R4: Hebrew chunk boundaries ----------------------------------------------------

def test_best_break_finds_hebrew_clause_end():
    # period butting a Hebrew letter (no trailing space) is a valid break point
    text = "א" * 40 + "מאושפז.הניתוח" + "ב" * 40
    target = 45
    idx = _best_break(text, 0, target, len(text), slack=20)
    # break should land right after the '.' (inside the slack window), not the hard target
    assert text[idx - 1] == "."


def test_best_break_prefers_ascii_marker_when_present():
    text = "word one. " + "x" * 60
    idx = _best_break(text, 0, 8, len(text), slack=20)
    assert text[idx - 2:idx] == ". "  # landed right after the ". " marker


# --- R5: Hebrew honorific normalization ---------------------------------------------

def test_hebrew_honorific_stripped_for_dedup():
    assert normalize_entity('ד"ר סוזן פלדמן') == normalize_entity("סוזן פלדמן")


def test_hebrew_lawyer_honorific_stripped():
    assert normalize_entity('עו"ד דוד לוי') == normalize_entity("דוד לוי")


def test_english_honorific_still_stripped():
    assert normalize_entity("Dr. Richard Hall") == normalize_entity("richard hall")


# --- No-corruption guarantees (logical / visual / mixed) ----------------------------

def test_logical_order_hebrew_unchanged():
    logical = "תיק טיפול ארוך-טווח – מוחמד בן, גיל 88"
    assert detect_text_order(logical) == "logical"
    assert normalize_rtl(logical) == logical


def test_visual_order_hebrew_is_reversed_to_logical():
    logical = "מוחמד בן גיל שמונים ושמונה שנים"
    # synthesize a visual-order extraction: reverse char order within each token and
    # reverse token order (what a visual-order extractor would emit)
    toks = logical.split(" ")
    visual = " ".join(t[::-1] for t in toks[::-1])
    assert detect_text_order(visual) == "visual"
    assert normalize_rtl(visual) == logical


def test_mixed_hebrew_english_identifier_searchable():
    # the SLA code must survive normalization untouched in a mixed line
    line = "ההסכם SLA-2025 פעיל"
    assert "SLA-2025" in normalize_rtl(line)
