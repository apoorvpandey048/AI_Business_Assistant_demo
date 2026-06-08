"""PDF ingestion: extract text with real page numbers, normalize RTL (Hebrew),
and chunk in a section-aware way so every chunk carries document/page/section
metadata for citations.

RTL note: PDF text extractors return Hebrew runs in reversed (visual) order. We
restore logical order in the ingestion layer so the index matches logical-order
Hebrew queries. Latin/numeric runs (e.g. "SLA-2025", "(30)") are already correct
and are left untouched.
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


def _is_hebrew_token(tok: str) -> bool:
    return bool(_HEB.search(tok))


def normalize_rtl(text: str) -> str:
    """Restore logical reading order for Hebrew runs in extractor output."""
    if not _HEB.search(text):
        return text
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

    for page_index, (raw, needs_norm) in enumerate(_page_texts(path), start=1):
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

    return IngestedDoc(document=document, language=doc_lang, chunks=chunks)


def ingest_pdf_dir(pdf_dir: Path) -> list[IngestedDoc]:
    docs = []
    for p in sorted(pdf_dir.glob("*.pdf")):
        docs.append(ingest_pdf(p))
    return docs
