"""Regression tests — Hebrew PDF ingestion reading-order detection.

The Jenny investigation bug: ``normalize_rtl`` unconditionally reversed Hebrew, so a
PDF extracted in LOGICAL order was double-reversed into garbage (``מוחמד`` → ``דמחומ``),
making Hebrew uploads unsearchable. The fix detects order and reverses only VISUAL text.

Run:  .venv/bin/python -m pytest tests/test_hebrew_ingestion_order.py -q
"""
from __future__ import annotations

import io

import pytest

from app.ingestion.pdf import detect_text_order, normalize_rtl

# Logical-order Hebrew (correct reading order, as a logical-order extractor emits).
_LOGICAL = "תיק טיפול ארוך-טווח – מוחמד בן, גיל 88. המטופל מקבל טיפול רפואי בבית החולים."


# --- detector ---------------------------------------------------------------

def test_detect_logical_order():
    assert detect_text_order(_LOGICAL) == "logical"


def test_detect_no_hebrew():
    assert detect_text_order("Patient: Mohammad Ben, age 88. Diagnosis: Dementia.") == "none"
    assert detect_text_order("") == "none"


def test_detect_visual_order():
    # Build visual order explicitly: reverse chars of each Hebrew word AND word order.
    words = _LOGICAL.split(" ")
    visual = " ".join(w[::-1] for w in reversed(words))
    assert detect_text_order(visual) == "visual"


# --- normalize_rtl: the core guarantee --------------------------------------

def test_logical_text_left_unchanged():
    # The bug: this used to be reversed into garbage. It must now pass through intact.
    out = normalize_rtl(_LOGICAL)
    assert "מוחמד" in out and "דמחומ" not in out
    assert "טיפול" in out and "לופיט" not in out


def test_visual_text_is_repaired():
    words = _LOGICAL.split(" ")
    visual = " ".join(w[::-1] for w in reversed(words))
    out = normalize_rtl(visual)
    # after repair, real logical words are present again
    assert "מוחמד" in out
    assert "טיפול" in out


def test_non_hebrew_untouched():
    en = "1. Term. The initial term is twelve (12) months. SLA-2025 applies."
    assert normalize_rtl(en) == en


def test_mixed_hebrew_english_latin_preserved():
    # Latin identifiers/codes must survive regardless of Hebrew handling.
    mixed = "המטופל מקבל Donepezil 10mg ו-Metformin 500mg לפי קוד SLA-2025."
    out = normalize_rtl(mixed)
    assert "Donepezil" in out and "Metformin" in out and "SLA-2025" in out
    assert "10mg" in out and "500mg" in out


def test_hebrew_identifiers_and_names_searchable():
    # Hebrew names + embedded codes survive (logical-order input).
    text = "מטופל: מוחמד בן. מוסד: Lakeview Senior Care Center. תרופה: ויטמין D."
    out = normalize_rtl(text)
    assert "מוחמד" in out and "מטופל" in out and "Lakeview" in out


# --- end-to-end ingestion ----------------------------------------------------

from pathlib import Path  # noqa: E402

from app.ingestion.pdf import ingest_pdf  # noqa: E402

# Jenny's actual logical-order Hebrew upload — the real reproducer. Skipped when the
# binary isn't present (fresh checkout / CI), so the suite stays portable.
_JENNY_PDF = Path("data/uploads/pdfs/-_88.pdf")


@pytest.mark.skipif(not _JENNY_PDF.exists(),
                    reason="logical-order Hebrew reproducer PDF not present")
def test_ingest_logical_hebrew_pdf_is_searchable():
    from pypdf import PdfReader
    raw = " ".join((p.extract_text() or "") for p in PdfReader(str(_JENNY_PDF)).pages)
    # sanity: the real upload is logical order
    assert detect_text_order(raw) == "logical"
    doc = ingest_pdf(_JENNY_PDF)
    body = " ".join(c.text for c in doc.chunks)
    assert "מוחמד" in body, f"patient name corrupted in ingestion: {body[:120]!r}"
    assert "דמחומ" not in body, "Hebrew was wrongly reversed (the bug)"
    # Hebrew medical terms + embedded Latin both survive
    assert "טיפול" in body and "COVID-19" in body


# Bundled visual-order Hebrew contract — pypdf extracts it reversed; ingestion must
# still repair it (the Tavor-class path we must NOT regress). Tested against the raw
# PDF extraction directly to bypass the .txt sidecar.
_TAVOR_PDF = Path("data/pdfs/TAVOR_Contract_HE.pdf")


@pytest.mark.skipif(not _TAVOR_PDF.exists(),
                    reason="bundled Hebrew contract PDF not present")
def test_visual_order_pdf_extraction_is_repaired():
    from pypdf import PdfReader
    raw = " ".join((p.extract_text() or "") for p in PdfReader(str(_TAVOR_PDF)).pages)
    assert detect_text_order(raw) == "visual", "fixture should extract in visual order"
    repaired = normalize_rtl(raw)
    # logical Hebrew words present after repair
    assert "הסכם" in repaired and "תבור" in repaired
