"""Phase 1 — chunking & structure quality.

These lock the fixes that make "no facts missed" achievable at the ingestion layer:
- a flattened table-of-contents line no longer hijacks every chunk's section,
- real structural headers (📑 PAGE N – TITLE) become sections,
- boundary-aware windowing never splits a fact mid-record,
- deterministic per-chunk metadata (dates / amounts / ids / entities) is attached.

The structure assertions run against the real sample PDFs in data/uploads/pdfs when
present, and are skipped otherwise so a checkout without the (gitignored) customer
uploads still passes. The unit tests for segmentation / metadata / windowing always run.

Run:  .venv/bin/python -m pytest tests/test_chunk_structure.py -q
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.ingestion.metadata import extract_metadata, merge_metadata
from app.ingestion.pdf import _window, ingest_pdf
from app.ingestion.segment import segment_lines

PDF_DIR = Path(__file__).resolve().parent.parent / "data" / "uploads" / "pdfs"


def _has(name: str) -> bool:
    return (PDF_DIR / name).exists()


# --- segmentation ------------------------------------------------------------------
def test_segment_splits_flattened_bullets_and_header():
    # pypdf glues a header onto the preceding bullet record on one physical line.
    raw = ("●  Response:  Transferred  to  Hospital  \n"
           "📑  PAGE  9  –  HOSPITAL  TRANSFERS  \nHospital:  Northwestern")
    lines = segment_lines(raw)
    assert "📑  PAGE  9  –  HOSPITAL  TRANSFERS" in lines
    # the bullet glyph itself is stripped; its record survives as content
    assert any(l.startswith("Response:") for l in lines)
    assert not any(l.strip() == "●" for l in lines)


def test_segment_preserves_structure_emoji_but_drops_bare_bullet():
    lines = segment_lines("●  one  ●  two  📄  Title")
    assert lines == ["one", "two", "📄  Title"]


# --- boundary-aware windowing ------------------------------------------------------
def test_window_short_text_is_single_chunk():
    assert _window("a short line") == ["a short line"]


def test_window_breaks_on_record_boundary_not_mid_fact():
    # Build text > size so it must split; the fact must stay whole in one window.
    fact = "Surgeon: Dr. Richard Hall"
    filler = "x. " * 260            # ~780 chars of sentence-ended filler before the fact
    text = filler + fact + ". " + ("y. " * 100)
    parts = _window(text, size=700, overlap=120, slack=180)
    assert len(parts) >= 2
    assert any(fact in p for p in parts), "the fact must live wholly inside one chunk"


# --- metadata extraction -----------------------------------------------------------
def test_metadata_extracts_dates_money_ids_entities():
    md = extract_metadata(
        "Patient: Mohammad Ben  Diagnosis: COVID-19  Admission Date: 12 January 2026  "
        "Insurance: $12,000/month  Surgeon: Dr. Richard Hall"
    )
    assert "12 January 2026" in md.get("dates", [])
    assert any("12,000" in a for a in md.get("amounts", []))
    assert "COVID-19" in md.get("identifiers", [])
    ents = md.get("entities", [])
    assert "Mohammad Ben" in ents and "Dr. Richard Hall" in ents


def test_metadata_hebrew_amount_and_name():
    md = extract_metadata('אבחנה דמנציה תאריך 12 בינואר 2026 כיסוי 12,000 לחודש ד"ר סוזן פלדמן')
    assert "12 בינואר 2026" in md.get("dates", [])
    assert any("12,000" in a for a in md.get("amounts", []))
    assert any("סוזן" in e for e in md.get("entities", []))


def test_metadata_clean_whitespace_no_embedded_newlines():
    md = extract_metadata("Admitted\n \n12\n \nJanuary\n \n2026")
    assert md.get("dates") == ["12 January 2026"]


def test_merge_metadata_unions_and_dedupes():
    a = {"dates": ["12 January 2026"], "entities": ["Joni Carter"]}
    b = {"dates": ["12 January 2026"], "entities": ["Michel Carter"]}
    merged = merge_metadata(a, b)
    assert merged["dates"] == ["12 January 2026"]
    assert set(merged["entities"]) == {"Joni Carter", "Michel Carter"}


# --- structure on real sample PDFs (skipped if uploads absent) ---------------------
@pytest.mark.skipif(not _has("nursing_home_.pdf"), reason="sample upload not present")
def test_toc_no_longer_hijacks_every_section():
    doc = ingest_pdf(PDF_DIR / "nursing_home_.pdf")
    sections = {c.section for c in doc.chunks}
    # before the fix this doc had ONE section (the ToC line) across 12/13 chunks
    assert len(sections) >= 8, f"expected many real sections, got {sections}"
    # no chunk is labeled with the flattened enumerator soup
    assert not any(c.section.count(". ") >= 3 for c in doc.chunks)


@pytest.mark.skipif(not _has("nursing_home_.pdf"), reason="sample upload not present")
def test_real_page_headers_become_sections():
    doc = ingest_pdf(PDF_DIR / "nursing_home_.pdf")
    sections = {c.section.upper() for c in doc.chunks}
    assert any("HOSPITAL TRANSFERS" in s for s in sections)
    assert any("PATIENT SUMMARY" in s for s in sections)


@pytest.mark.skipif(not _has("nursing_home_.pdf"), reason="sample upload not present")
def test_key_facts_stay_intact_in_a_single_chunk():
    doc = ingest_pdf(PDF_DIR / "nursing_home_.pdf")
    blobs = [" ".join(c.text.split()) for c in doc.chunks]
    for fact in ("Dr. Richard Hall", "Open Reduction and Internal Fixation",
                 "$12,000", "Northwestern Memorial Hospital"):
        assert any(fact in b for b in blobs), f"{fact!r} was split across chunks"


@pytest.mark.skipif(not _has("nursing_home_.pdf"), reason="sample upload not present")
def test_chunks_carry_metadata():
    doc = ingest_pdf(PDF_DIR / "nursing_home_.pdf")
    assert any(c.metadata for c in doc.chunks), "no chunk carried extracted metadata"
    # document-level union is populated
    assert doc.metadata.get("entities"), "doc-level metadata union is empty"


@pytest.mark.skipif(not _has("-_88.pdf"), reason="hebrew sample upload not present")
def test_hebrew_doc_sections_and_facts():
    doc = ingest_pdf(PDF_DIR / "-_88.pdf")
    assert len({c.section for c in doc.chunks}) >= 6
    blobs = [" ".join(c.text.split()) for c in doc.chunks]
    assert any("מוחמד" in b for b in blobs)
