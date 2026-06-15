"""Reciprocal Rank Fusion — robustly combine the dense and BM25 rankings.

RRF is order-based (not score-based), so it doesn't require the two retrievers'
scores to be on the same scale, and it's easy to surface in the inspector panel
(dense rank + bm25 rank → fused score).

Phase 3 adds ``weighted_rank_fusion`` — the same RRF backbone, but each input ranking
carries a weight so entity- and graph-derived rankings can join dense + BM25 without
overpowering them. ``reciprocal_rank_fusion`` is the unweighted special case and is
kept unchanged for existing callers.
"""
from __future__ import annotations


def reciprocal_rank_fusion(
    ranked_lists: list[list[str]], k: int = 60
) -> dict[str, float]:
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, doc_id in enumerate(ranked, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return scores


def weighted_rank_fusion(
    weighted_lists: list[tuple[list[str], float]], k: int = 60
) -> dict[str, float]:
    """RRF where each ranked list contributes ``weight / (k + rank)``.

    Lets heterogeneous signals (dense, BM25, entity, graph) fuse on one scale while a
    weak/auxiliary signal (e.g. graph proximity) is down-weighted so it adds recall
    without out-voting the primary lexical+dense evidence. A weight of 1.0 reproduces
    plain RRF for that list.
    """
    scores: dict[str, float] = {}
    for ranked, weight in weighted_lists:
        if weight == 0 or not ranked:
            continue
        for rank, doc_id in enumerate(ranked, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + weight / (k + rank)
    return scores

