"""Logical-line segmentation for extractor output.

``pypdf`` (and most PDF text extractors) collapse a page into one long run with only
incidental ``\\n`` breaks: bullet records, field rows, and section headers all land on
the same physical "line". The section-detection logic downstream needs *logical* lines
— one per bullet/record/header — so it can find real headers
(``📑 PAGE 9 – HOSPITAL TRANSFERS``) instead of latching onto the table-of-contents
line that happens to start with a number.

This is fully deterministic and offline, and script-agnostic: the markers it splits on
(bullet glyphs, the 📑/📄 structure emojis) appear identically in the English and
Hebrew sample documents.
"""
from __future__ import annotations

import re

# Record/bullet markers that begin a new logical line. The structure emojis (📑 page
# header, 📄 doc title) and the common bullet glyphs in the sample corpus.
_BULLETS = "●○■◦▪‣⁃"
_STRUCTURE = "📑📄"
# A break point is immediately before one of the marker glyphs. pypdf pads inter-token
# gaps with double spaces, so the markers are reliably space-delimited.
_SPLIT_BEFORE = re.compile(r"\s*(?=[" + _BULLETS + _STRUCTURE + r"])")
# Leading bullet glyphs (NOT the structure emojis — those carry the header text and
# must be preserved so the header detector can see "📑 PAGE 9 – …"). Stripped from the
# front of a unit so a bare "●" never becomes its own contentless logical line.
_LEADING_BULLET = re.compile(r"^[" + _BULLETS + r"]\s*")


def segment_lines(text: str) -> list[str]:
    """Turn extractor page text into logical lines.

    Splits on real newlines, then on bullet/structure markers. Returns non-empty,
    stripped logical lines in reading order. A logical line never spans two bullets or
    two structure markers, so a downstream header scan sees
    ``📑 PAGE 9 – HOSPITAL TRANSFERS`` as its own line even though the extractor glued
    it to the preceding bullet record.
    """
    out: list[str] = []
    for physical in (text or "").split("\n"):
        physical = physical.strip()
        if not physical:
            continue
        for piece in _SPLIT_BEFORE.split(physical):
            piece = _LEADING_BULLET.sub("", piece.strip()).strip()
            if piece:
                out.append(piece)
    return out
