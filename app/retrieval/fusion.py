"""Reciprocal Rank Fusion — robustly combine the dense and BM25 rankings.

RRF is order-based (not score-based), so it doesn't require the two retrievers'
scores to be on the same scale, and it's easy to surface in the inspector panel
(dense rank + bm25 rank → fused score).
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
