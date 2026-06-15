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

from app.ingestion.metadata import extract_metadata, merge_metadata
from app.ingestion.segment import segment_lines

_HEB = re.compile(r"[֐-׿]")
_HEADING = re.compile(r"^\s*‎?\s*(\d+)\.\s+\S")
_CONTROL = re.compile(r"[‎‏‪-‮]")  # bidi control marks

# Real structural headers in the sample corpus (and documents like it):
#   "📑 PAGE 9 – HOSPITAL TRANSFERS"  /  "📑 דף 1 – דף שער"  (Hebrew)  /  "📄 <title>"
# Detected as section boundaries BEFORE the numbered-heading rule, because the
# numbered rule otherwise latches onto a flattened table-of-contents line. The header
# title is everything after the PAGE/דף N – separator (or after the 📄 for a doc title).
_STRUCT_HEADER = re.compile(
    r"^\s*[📑📄]\s*"
    r"(?:(?:PAGE|page|דף)\s*\d+\s*[–\-:]\s*)?"
    r"(?P<title>.+\S)\s*$"
)
# A table-of-contents line: 3+ "N." enumerators flattened onto one line. Such a line is
# NOT a section boundary — it is the ToC itself, and letting the numbered-heading rule
# fire on it stamps every following chunk with the ToC text (the bug this fixes).
_TOC_MARKERS = re.compile(r"\b\d+\.\s+\S")
_TOC_TITLE = re.compile(r"(?:TABLE\s+OF\s+CONTENTS|תוכן\s+עניינים)", re.I)


def _is_toc_line(line: str) -> bool:
    return len(_TOC_MARKERS.findall(line)) >= 3


def _struct_header_title(line: str) -> Optional[str]:
    """Return the section title if ``line`` is a structural header (📑/📄), else None."""
    m = _STRUCT_HEADER.match(line.strip())
    if not m:
        return None
    title = re.sub(r"\s+", " ", m.group("title")).strip()
    # A page header whose title is itself a ToC ("📑 PAGE 2 – TABLE OF CONTENTS") names
    # the ToC section; keep a clean label rather than the enumerator soup that follows.
    if _TOC_TITLE.search(title):
        return "Table of Contents"
    return title or None

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
    metadata: dict = field(default_factory=dict)  # entities/dates/amounts/ids (Phase 1)

    def as_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id, "document": self.document, "page": self.page,
            "section": self.section, "language": self.language, "text": self.text,
            "metadata": self.metadata,
        }


@dataclass
class IngestedDoc:
    document: str
    language: str
    chunks: list[Chunk] = field(default_factory=list)
    total_pages: int = 0
    empty_pages: list[int] = field(default_factory=list)  # pages with no extractable text
    metadata: dict = field(default_factory=dict)  # document-level union of chunk metadata


def _window(text: str, size: int = 700, overlap: int = 120, slack: int = 180) -> list[str]:
    """Split ``text`` into overlapping windows, preferring to break at a record or
    sentence boundary near the target size so a fact ("Surgeon: Dr. Richard Hall") is
    never cut mid-record. Falls back to a hard cut only when no boundary exists within
    ``slack`` chars of the target.
    """
    text = text.strip()
    if len(text) <= size:
        return [text] if text else []
    out, start = [], 0
    n = len(text)
    while start < n:
        hard_end = min(start + size, n)
        if hard_end >= n:
            out.append(text[start:].strip())
            break
        end = _best_break(text, start, hard_end, n, slack)
        out.append(text[start:end].strip())
        start = max(end - overlap, start + 1)
    return [c for c in out if c]


# Boundary markers, best first: record separators, then sentence ends.
_BREAKS = (" • ", " ● ", " ○ ", "; ", ". ", " – ", ", ")


def _best_break(text: str, start: int, target: int, n: int, slack: int) -> int:
    """Index to cut at: the latest boundary marker within ``[target-slack, target+slack]``,
    preferring stronger separators. Returns ``target`` if none is found."""
    lo = max(start + 1, target - slack)
    hi = min(n, target + slack)
    window = text[lo:hi]
    for marker in _BREAKS:
        pos = window.rfind(marker)
        if pos != -1:
            return lo + pos + len(marker)
    return target


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

        # Split the page into (section, body) blocks. Operate over LOGICAL lines
        # (segment_lines un-flattens pypdf's mega-line) so real headers are visible.
        # Header precedence: structural 📑/📄 header → numbered heading, but never a
        # table-of-contents line (which would otherwise hijack every following chunk).
        blocks: list[tuple[str, list[str]]] = [(current_section, [])]
        for line in segment_lines(text):
            stripped = line.strip()
            if not stripped:
                continue
            struct = _struct_header_title(stripped)
            if struct is not None:
                current_section = struct
                blocks.append((current_section, []))
                continue
            if _is_toc_line(stripped):
                # The ToC content itself — keep it as body under a clean section label,
                # but do NOT treat its leading "1." as a heading boundary.
                if current_section != "Table of Contents":
                    current_section = "Table of Contents"
                    blocks.append((current_section, []))
                blocks[-1][1].append(stripped)
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
                        metadata=extract_metadata(piece),
                    )
                )

    return IngestedDoc(document=document, language=doc_lang, chunks=chunks,
                       total_pages=total_pages, empty_pages=empty_pages,
                       metadata=merge_metadata(*(c.metadata for c in chunks)))


def ingest_pdf_dir(pdf_dir: Path) -> list[IngestedDoc]:
    docs = []
    for p in sorted(pdf_dir.glob("*.pdf")):
        docs.append(ingest_pdf(p))
    return docs
