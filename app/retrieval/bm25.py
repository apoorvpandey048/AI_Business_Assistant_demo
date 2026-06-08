"""BM25 keyword search — the half of hybrid retrieval that catches exact identifiers
(e.g. "SLA-2025") that dense embeddings often miss. Unicode tokenization so Hebrew
works too.
"""
from __future__ import annotations

import re

from rank_bm25 import BM25Okapi

_TOKEN = re.compile(r"\w+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall((text or "").lower())


class BM25Index:
    def __init__(self) -> None:
        self._ids: list[str] = []
        self._bm25: BM25Okapi | None = None

    def build(self, ids: list[str], texts: list[str]) -> None:
        self._ids = list(ids)
        corpus = [tokenize(t) for t in texts]
        # guard against empty docs which break idf
        corpus = [toks if toks else ["∅"] for toks in corpus]
        self._bm25 = BM25Okapi(corpus)

    def search(self, query: str, k: int) -> list[tuple[str, float]]:
        if self._bm25 is None or not self._ids:
            return []
        scores = self._bm25.get_scores(tokenize(query) or ["∅"])
        ranked = sorted(zip(self._ids, scores), key=lambda x: x[1], reverse=True)
        return [(i, float(s)) for i, s in ranked[:k] if s > 0]
