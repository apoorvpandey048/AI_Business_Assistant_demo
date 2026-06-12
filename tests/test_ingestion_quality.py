"""Regression tests — ingestion quality signals for arbitrary customer PDFs.

A partially scanned PDF (some pages have no text layer) must still index, but the
client must be warned which part of their document is invisible to search. A fully
scanned PDF is rejected with a clear, friendly error (no OCR in this environment).

Run:  .venv/bin/python -m pytest tests/test_ingestion_quality.py -q
"""
from __future__ import annotations

import io
from pathlib import Path

import pytest

reportlab = pytest.importorskip("reportlab", reason="synthetic PDFs need reportlab")
from pypdf import PdfReader, PdfWriter  # noqa: E402

from app.engine import _page_warning  # noqa: E402
from app.ingestion.pdf import ingest_pdf  # noqa: E402


def _text_page_pdf() -> io.BytesIO:
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(72, 720, "Master Service Agreement between Foo Corp and Bar Ltd.")
    c.drawString(72, 700, "1. Term. The initial term is twelve (12) months.")
    c.showPage()
    c.save()
    buf.seek(0)
    return buf


def _write_pdf(path: Path, *, text_pages: int, blank_pages: int) -> None:
    w = PdfWriter()
    for _ in range(text_pages):
        w.append(PdfReader(_text_page_pdf()))
    for _ in range(blank_pages):
        w.add_blank_page(width=612, height=792)
    with open(path, "wb") as f:
        w.write(f)


def test_partially_scanned_pdf_indexes_with_warning(tmp_path):
    p = tmp_path / "partial_scan.pdf"
    _write_pdf(p, text_pages=1, blank_pages=1)
    doc = ingest_pdf(p)
    assert doc.chunks, "the text page must still index"
    assert doc.total_pages == 2 and doc.empty_pages == [2]
    warning = _page_warning(doc)
    assert warning and "1 of 2" in warning and "no extractable text" in warning


def test_clean_pdf_has_no_warning(tmp_path):
    p = tmp_path / "clean.pdf"
    _write_pdf(p, text_pages=2, blank_pages=0)
    doc = ingest_pdf(p)
    assert doc.empty_pages == []
    assert _page_warning(doc) is None
