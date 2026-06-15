"""Deterministic query expansion for coverage-complete retrieval (Phase 2).

A single phrasing of a question retrieves a single neighborhood of the corpus. When the
goal is "no facts missed", that is not enough: a compound question ("penalties AND
suspension") and an entity question ("everything about Mohammad Ben") each have parts
that a single fused query under-weights. This module derives EXTRA phrasings — one per
aspect group, one per distinctive entity/identifier — that the retriever fuses into the
ranking via the existing ``extra_queries`` / RRF mechanism. More phrasings → more
ranked lists → better recall, while RRF keeps any single phrasing from dominating.

Fully deterministic and offline: it reuses the intent module's aspect/term analysis. An
optional single LLM rewrite can be layered on by the caller when live, but the floor
here needs no model.
"""
from __future__ import annotations

from app.retrieval.intent import aspect_groups, content_terms

_MAX_EXPANSIONS = 6  # cap so a term-heavy question can't explode the fusion input


def expand_queries(query: str, extra: list[str] | None = None) -> list[str]:
    """Return deterministic auxiliary phrasings to fuse alongside ``query``.

    - one phrasing per aspect group of a compound question, so each aspect gets its
      own ranked list instead of competing inside one query;
    - the caller's own extras (e.g. a router rewrite) are preserved and de-duplicated.

    Never includes ``query`` itself. Order-stable and capped at ``_MAX_EXPANSIONS``.
    """
    out: list[str] = []

    def _add(phrase: str) -> None:
        p = (phrase or "").strip()
        if not p or p.lower() == (query or "").strip().lower():
            return
        if p.lower() not in {o.lower() for o in out}:
            out.append(p)

    for caller_extra in (extra or []):
        _add(caller_extra)

    groups = aspect_groups(query)
    if len(groups) >= 2:
        for g in groups:
            _add(" ".join(g))
    else:
        # single-aspect: a focused phrasing of just the content terms still adds a
        # complementary ranked list (drops instruction/filler words the full query
        # carries), improving recall without changing the dominant query.
        terms = content_terms(query)
        if len(terms) >= 2:
            _add(" ".join(terms))

    return out[:_MAX_EXPANSIONS]
