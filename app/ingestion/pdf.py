"""PDF ingestion: extract text with real page numbers, normalize RTL (Hebrew),
and chunk in a section-aware way so every chunk carries document/page/section
metadata for citations.

RTL note: SOME PDF text extractors return Hebrew runs in reversed (visual) order;
others already return logical order. We DETECT the order per page and only reverse
visual-order text, so a logical-order extraction is never corrupted (the bug behind
the Jenny investigation: an upload extracted in logical order was being double-reversed
into garbage — ``מוחמד`` → ``דמחומ``). Latin/numeric runs (e.g. "SLA-2025", "(30)") are
left untouched in either case.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from pypdf import PdfReader

_HEB = re.compile(r"[֐-׿]")
_HEADING = re.compile(r"^\s*‎?\s*(\d+)\.\s+\S")
_CONTROL = re.compile(r"[‎‏‪-‮]")  # bidi control marks

# Hebrew final-form letters. Orthographically these occur ONLY at the END of a word,
# so their position is a direction fingerprint: in logical order they sit at word-ends,
# in visual (reversed) order they sit at word-starts. This is lexicon-free and works on
# any Hebrew text. See docs/hebrew-ingestion-fix-plan.md.
_HEB_FINALS = set("ךםןףץ")
_HEB_WORD = re.compile(r"[֐-׿]{2,}")


def _is_hebrew_token(tok: str) -> bool:
    return bool(_HEB.search(tok))


def detect_text_order(text: str) -> str:
    """Classify the reading order of Hebrew in extractor output.

    Returns ``"none"`` (no Hebrew), ``"logical"`` (already correct — leave as-is), or
    ``"visual"`` (reversed — must be flipped). Deterministic and offline.

    Primary signal: Hebrew final-form letters (ך ם ן ף ץ) appear only at word-ends in
    logical order and at word-starts when reversed. Tie-break: common Hebrew function
    words (the intent layer's stopword list) matched as-is vs reversed. When genuinely
    ambiguous, default to ``"logical"`` — leaving correct text alone is always safe,
    whereas reversing correct text is the corruption we are fixing.
    """
    toks = _HEB_WORD.findall(text or "")
    if not toks:
        return "none"
    final_end = sum(1 for t in toks if t[-1] in _HEB_FINALS)
    final_start = sum(1 for t in toks if t[0] in _HEB_FINALS)
    if final_end != final_start:
        return "logical" if final_end > final_start else "visual"
    # Tie-break on a small built-in lexicon of common Hebrew function words.
    try:
        from app.retrieval.intent import _STOP_HE as _anchors
    except Exception:  # pragma: no cover - defensive
        _anchors = set()
    if _anchors:
        as_is = sum(1 for t in toks if t in _anchors)
        rev = sum(1 for t in toks if t[::-1] in _anchors)
        if rev > as_is:
            return "visual"
    return "logical"


def _reverse_hebrew_runs(text: str) -> str:
    """Reverse Hebrew runs (chars + token order) to flip VISUAL → LOGICAL order.
    Latin/numeric tokens keep their position; only Hebrew spans are reversed."""
    out_lines = []
    for line in text.split("\n"):
        line = _CONTROL.sub("", line)
        tokens = line.split(" ")
        result: list[str] = []
        i = 0
        while i < len(tokens):
            if _is_hebrew_token(tokens[i]):
                j = i
                while j < len(tokens) and (_is_hebrew_token(tokens[j]) or tokens[j] == ""):
                    j += 1
                span = tokens[i:j]
                span = [t[::-1] for t in span][::-1]  # reverse chars + token order
                result.extend(span)
                i = j
            else:
                result.append(tokens[i])
                i += 1
        out_lines.append(" ".join(result))
    return "\n".join(out_lines)


def normalize_rtl(text: str) -> str:
    """Return Hebrew text in logical reading order.

    Only VISUAL-order extractor output is reversed; LOGICAL-order text (and any text
    with no Hebrew) is returned unchanged. This makes the function safe for extractors
    that already emit logical order — the previous unconditional reversal corrupted
    those (the Jenny investigation bug)."""
    if not _HEB.search(text):
        return text
    if detect_text_order(text) != "visual":
        return text
    return _reverse_hebrew_runs(text)


def detect_language(text: str) -> str:
    return "he" if _HEB.search(text) else "en"


@dataclass
class Chunk:
    chunk_id: str
    document: str
    page: int
    section: str
    language: str
    text: str

    def as_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id, "document": self.document, "page": self.page,
            "section": self.section, "language": self.language, "text": self.text,
        }


@dataclass
class IngestedDoc:
    document: str
    language: str
    chunks: list[Chunk] = field(default_factory=list)
    total_pages: int = 0
    empty_pages: list[int] = field(default_factory=list)  # pages with no extractable text


def _window(text: str, size: int = 700, overlap: int = 120) -> list[str]:
    text = text.strip()
    if len(text) <= size:
        return [text] if text else []
    out, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        out.append(text[start:end].strip())
        if end == len(text):
            break
        start = end - overlap
    return [c for c in out if c]


def _page_texts(path: Path) -> list[tuple[str, bool]]:
    """Return (text, needs_rtl_normalization) per page.

    Prefers a clean ``<name>.txt`` sidecar (logical-order text layer, e.g. from a
    Hebrew-aware parser) when present — those pages are already logical and must NOT
    be re-normalized. Otherwise extracts from the PDF and flags pages for RTL repair.
    """
    sidecar = path.with_suffix(".txt")
    if sidecar.exists():
        pages = sidecar.read_text("utf-8").split("\f")
        return [(p, False) for p in pages]
    reader = PdfReader(str(path))
    return [((page.extract_text() or ""), True) for page in reader.pages]


def ingest_pdf(path: Path) -> IngestedDoc:
    document = path.name
    chunks: list[Chunk] = []
    current_section = "Preamble"
    seq = 0
    doc_lang = "en"
    total_pages = 0
    empty_pages: list[int] = []

    for page_index, (raw, needs_norm) in enumerate(_page_texts(path), start=1):
        total_pages = page_index
        if not (raw or "").strip():
            empty_pages.append(page_index)
        text = normalize_rtl(raw) if needs_norm else raw
        if _HEB.search(text):
            doc_lang = "he"

        # split the page into (section, body) blocks using heading lines
        blocks: list[tuple[str, list[str]]] = [(current_section, [])]
        for line in text.split("\n"):
            stripped = line.strip()
            if not stripped:
                continue
            if _HEADING.match(stripped):
                current_section = re.sub(r"\s+", " ", stripped)
                blocks.append((current_section, []))
            else:
                blocks[-1][1].append(stripped)

        for section, lines in blocks:
            body = " ".join(lines).strip()
            if not body:
                continue
            for piece in _window(body):
                seq += 1
                chunks.append(
                    Chunk(
                        chunk_id=f"{document}::p{page_index}::c{seq}",
                        document=document,
                        page=page_index,
                        section=section,
                        language=detect_language(piece),
                        text=piece,
                    )
                )

    return IngestedDoc(document=document, language=doc_lang, chunks=chunks,
                       total_pages=total_pages, empty_pages=empty_pages)


def ingest_pdf_dir(pdf_dir: Path) -> list[IngestedDoc]:
    docs = []
    for p in sorted(pdf_dir.glob("*.pdf")):
        docs.append(ingest_pdf(p))
    return docs
