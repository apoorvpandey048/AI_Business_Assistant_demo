"""Deterministic per-chunk metadata extraction.

Pulls structured facts — dates, money amounts, identifiers, emails, phones, and
candidate person/organization names — out of a chunk's text using regex and small
lexicons. No LLM, no network: the same offline-safe discipline as ``intent.py``.

This metadata is the substrate the later phases consume:
- Phase 2's completeness verifier checks that every entity/amount/id the question
  references actually has supporting evidence.
- Phase 3's entity index and knowledge graph are built from these extractions plus the
  structured-source rows.

The goal is RECALL, not precision: it is fine to over-extract a candidate name here
(a downstream consumer can confirm it), but a missed identifier is a missed fact.
"""
from __future__ import annotations

import re
from typing import Any

# --- identifiers: structured codes like FC-2026-10458, INV-1187, SLA-2025 ----------
# A run of LETTERS-(optional more letter/number groups) joined by - or _, with at least
# one digit somewhere, OR a pure alphanumeric code with both letters and digits.
_IDENTIFIER = re.compile(r"\b[A-Z][A-Z0-9]*(?:[-_/][A-Z0-9]+)+\b")

# --- money: $12,000  |  USD 12,000  |  12,000 לחודש (Hebrew "per month") -----------
_MONEY = re.compile(
    r"(?:[$₪€£]\s?\d[\d,]*(?:\.\d+)?)"
    r"|(?:\b(?:USD|ILS|EUR|GBP)\s?\d[\d,]*(?:\.\d+)?)"
    r"|(?:\b\d[\d,]{2,}(?:\.\d+)?\s?(?:לחודש|ש\"ח|שקלים|dollars?|usd))",
    re.I,
)

# --- dates: 12 January 2026 | 12 בינואר 2026 | 2026-02-10 | 02/10/2026 -------------
_MONTHS_EN = (r"January|February|March|April|May|June|July|August|September|October|"
              r"November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec")
_MONTHS_HE = r"בינואר|בפברואר|במרץ|באפריל|במאי|ביוני|ביולי|באוגוסט|בספטמבר|באוקטובר|בנובמבר|בדצמבר"
_DATE = re.compile(
    r"(?:\b\d{1,2}\s+(?:" + _MONTHS_EN + r"|" + _MONTHS_HE + r")\s+\d{4})"
    r"|(?:\b(?:" + _MONTHS_EN + r")\s+\d{1,2},?\s+\d{4})"
    r"|(?:\b\d{4}-\d{2}-\d{2}\b)"
    r"|(?:\b\d{1,2}/\d{1,2}/\d{2,4}\b)",
    re.I,
)

_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_PHONE = re.compile(r"(?<!\w)(?:\+?\d[\d\-\s().]{6,}\d)(?!\w)")

# --- person / organization candidates ----------------------------------------------
# A run of 2+ capitalized tokens ("Richard Hall", "Northwestern Memorial Hospital"),
# allowing an internal honorific/particle (Dr., of, the). Hebrew names are caught by a
# separate proper-noun pass since Hebrew has no case.
_TITLE = r"(?:Dr|Mr|Mrs|Ms|Prof|Hon|Judge|Rev)\.?"
_PROPER_EN = re.compile(
    r"\b(?:" + _TITLE + r"\s+)?"
    r"[A-Z][a-z]+(?:\s+(?:of|the|and|&|[A-Z][a-z'.]+)){1,4}\b"
)
# Hebrew honorific-led names (ד"ר סוזן פלדמן). Hebrew letters run, 2-4 tokens. Allows
# an in-word geresh/apostrophe (ריצ'רד) so such names aren't truncated.
_HEB_NAME = re.compile(
    r'(?:ד"ר|פרופ\'?|מר|גב\'?|השופט(?:ת)?)\s+[֐-׿]+(?:[\'’][֐-׿]+)?'
    r'(?:\s+[֐-׿]+(?:[\'’][֐-׿]+)?){0,3}'
)

# Common words that start a capitalized run but are not entities — trims obvious noise
# from the recall-first proper-noun pass.
_STOP_PROPER = {
    "the", "this", "that", "page", "section", "case", "patient", "date", "event",
    "in", "of", "and", "for", "to", "from",
}

# A field LABEL is any word that appears immediately before a colon ("Age:", "Surgeon:").
# Detected per-text (data-driven, not hardcoded) so a proper-noun run that absorbed the
# next field's label — "Mohammad Ben Age" from "…Mohammad Ben Age: 88…" — can be trimmed
# back to the real entity "Mohammad Ben".
_LABEL_WORD = re.compile(r"([A-Za-z][\w'.]*)\s*:")


def _field_labels(text: str) -> set[str]:
    return {m.group(1).lower() for m in _LABEL_WORD.finditer(text)}


def _clean(seq: list[str]) -> list[str]:
    """De-dupe case-insensitively, preserve order, strip trailing punctuation."""
    seen, out = set(), []
    for s in seq:
        s = s.strip().strip(",.;:")
        if not s:
            continue
        k = s.lower()
        if k not in seen:
            seen.add(k)
            out.append(s)
    return out


def _persons(text: str, labels: set[str]) -> list[str]:
    found: list[str] = []
    for m in _PROPER_EN.finditer(text):
        span = m.group(0)
        toks = span.split()
        if toks[0].lower().strip(".") in _STOP_PROPER:
            continue
        # Trim trailing field-label tokens the greedy run absorbed from the next field
        # ("Mohammad Ben Age" → "Mohammad Ben"). Keep ≥1 token.
        while len(toks) > 1 and toks[-1].lower().strip(".") in labels:
            toks.pop()
        cleaned = " ".join(toks)
        if len(toks) >= 2:                 # an entity is a multi-token proper run
            found.append(cleaned)
    found += [m.group(0) for m in _HEB_NAME.finditer(text)]
    return _clean(found)


def extract_metadata(text: str) -> dict[str, list[str]]:
    """Return structured facts found in ``text``. Every value is a de-duplicated,
    order-preserving list of strings. Empty lists are omitted from the result so a
    chunk dict stays small.

    Whitespace is collapsed first (pypdf pads tokens with ``\\n`` and double spaces),
    so extracted values read cleanly ("12 January 2026", not "12\\n \\nJanuary")."""
    text = " ".join((text or "").split())
    labels = _field_labels(text)
    raw = {
        "identifiers": _clean(m.group(0) for m in _IDENTIFIER.finditer(text)),
        "amounts": _clean(m.group(0) for m in _MONEY.finditer(text)),
        "dates": _clean(m.group(0) for m in _DATE.finditer(text)),
        "emails": _clean(m.group(0) for m in _EMAIL.finditer(text)),
        "phones": _clean(m.group(0) for m in _PHONE.finditer(text)),
        "entities": _persons(text, labels),
    }
    return {k: v for k, v in raw.items() if v}


def merge_metadata(*metas: dict[str, Any]) -> dict[str, list[str]]:
    """Union several metadata dicts (e.g. across the chunks of a document)."""
    out: dict[str, list[str]] = {}
    for meta in metas:
        for k, vals in (meta or {}).items():
            out.setdefault(k, [])
            out[k] = _clean(out[k] + list(vals))
    return {k: v for k, v in out.items() if v}
