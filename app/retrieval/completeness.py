"""Completeness verification for coverage-complete retrieval (Phase 2).

The "no facts missed" guarantee needs a check that the evidence actually COVERS what the
question references — not just that retrieval returned its top passages. This module is
the deterministic gap detector: given the question and the selected evidence, it lists
the distinctive terms the question asks about (entities, identifiers, content words)
that NO selected passage contains. Those are coverage gaps. The retriever then fires a
targeted exact-match pass per gap to fill them (bounded by ``completeness_max_passes``).

This is the local analogue of "verify, then fill the holes" — a single retrieval shot
can miss a passage that uses different surface words for the same entity; the gap check
catches the miss and a targeted lookup recovers it, all offline and deterministically.
"""
from __future__ import annotations

from app.retrieval.intent import _distinctive_terms  # quoted/identifier/proper terms
from app.retrieval.intent import content_terms, term_in_text


def _question_targets(query: str) -> list[str]:
    """The distinctive things a question is 'about' — proper nouns / identifiers first
    (an entity question's answer locus), then any remaining content words. De-duped,
    order-preserving."""
    seen: set[str] = set()
    out: list[str] = []
    for t in list(_distinctive_terms(query)) + list(content_terms(query)):
        k = t.lower()
        if k and k not in seen:
            seen.add(k)
            out.append(t)
    return out


def find_gaps(query: str, evidence_texts: list[str]) -> list[str]:
    """Return the question's target terms that appear in NONE of the selected evidence.

    A non-empty result means retrieval may have missed a fact the question asks about —
    the caller should run a targeted pass for each gap term. Empty (the common case for
    a well-covered answer) means no fill pass is needed.

    Conservative: a term covered by ANY evidence passage (Hebrew-prefix tolerant via
    ``term_in_text``) is not a gap, so this never fires spuriously on a complete answer.
    """
    targets = _question_targets(query)
    if not targets:
        return []
    gaps: list[str] = []
    for t in targets:
        if not any(term_in_text(t, txt) for txt in evidence_texts):
            gaps.append(t)
    return gaps
