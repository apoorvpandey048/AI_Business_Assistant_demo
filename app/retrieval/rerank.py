"""Cross-encoder reranking (optional).

When sentence-transformers + a cross-encoder are installed, we rerank the fused
top-N for precision. Otherwise we fall back to the fusion order. The trace always
reports which backend was used.
"""
from __future__ import annotations

from typing import Optional


class Reranker:
    _instance: Optional["Reranker"] = None

    def __init__(self, model_name: str) -> None:
        self.model = None
        self.backend = "none"
        try:
            from sentence_transformers import CrossEncoder

            self.model = CrossEncoder(model_name)
            self.backend = f"cross-encoder:{model_name}"
        except Exception:
            self.backend = "none (fusion order)"

    @classmethod
    def get(cls, model_name: str) -> "Reranker":
        if cls._instance is None:
            cls._instance = cls(model_name)
        return cls._instance

    def rerank(self, query: str, items: list[tuple[str, str]]) -> Optional[dict[str, float]]:
        """items: (chunk_id, text). Returns {chunk_id: score} or None if unavailable."""
        if self.model is None or not items:
            return None
        pairs = [(query, text) for _, text in items]
        scores = self.model.predict(pairs)
        return {cid: float(s) for (cid, _), s in zip(items, scores)}
