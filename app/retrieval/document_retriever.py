"""The document retrieval orchestrator: dense + BM25 → RRF → rerank → top-k,
with metadata filtering and a full per-candidate trace for the inspector panel.
"""
from __future__ import annotations

from typing import Any, Optional

import numpy as np

from app.config import get_settings
from app.llm.embeddings import EmbeddingModel
from app.models import DocumentRetrievalTrace, Evidence, RetrievalCandidate
from app.retrieval.bm25 import BM25Index
from app.retrieval.fusion import reciprocal_rank_fusion
from app.retrieval.rerank import Reranker
from app.retrieval.vector_store import VectorStore, make_vector_store


def _snippet(text: str, n: int = 240) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[:n] + "…"


class DocumentIndex:
    def __init__(self) -> None:
        self.s = get_settings()
        self.chunks: dict[str, dict[str, Any]] = {}
        self.embedder = EmbeddingModel.get()
        self.store: VectorStore = make_vector_store()
        self.bm25 = BM25Index()
        self.reranker = (
            Reranker.get(self.s.reranker_model) if self.s.enable_rerank else None
        )

    # -- build --------------------------------------------------------------
    def build(self, chunks: list[dict[str, Any]]) -> None:
        self.chunks = {c["chunk_id"]: c for c in chunks}
        ids = [c["chunk_id"] for c in chunks]
        texts = [c["text"] for c in chunks]
        vectors = self.embedder.embed(texts)
        self.store.add(ids, vectors)
        self.bm25.build(ids, texts)

    @property
    def n_chunks(self) -> int:
        return len(self.chunks)

    def _allowed_ids(self, filters: dict[str, Any]) -> Optional[set[str]]:
        docs = filters.get("documents")
        if not docs:
            return None
        docs = set(docs)
        return {cid for cid, c in self.chunks.items() if c["document"] in docs}

    # -- retrieve -----------------------------------------------------------
    def retrieve(
        self, query: str, filters: Optional[dict[str, Any]] = None, final_k: Optional[int] = None
    ) -> tuple[list[Evidence], DocumentRetrievalTrace]:
        filters = filters or {}
        final_k = final_k or self.s.final_k
        allowed = self._allowed_ids(filters)

        # 1) dense
        qvec = self.embedder.embed_one(query)
        dense = self.store.search(qvec, self.s.dense_top_k, allowed_ids=allowed)
        dense_rank = {cid: i + 1 for i, (cid, _) in enumerate(dense)}
        dense_score = {cid: sc for cid, sc in dense}

        # 2) bm25 (filter to allowed after search)
        bm25 = self.bm25.search(query, self.s.bm25_top_k)
        if allowed is not None:
            bm25 = [(cid, sc) for cid, sc in bm25 if cid in allowed]
        bm25_rank = {cid: i + 1 for i, (cid, _) in enumerate(bm25)}
        bm25_score = {cid: sc for cid, sc in bm25}

        # 3) RRF fusion
        fused = reciprocal_rank_fusion(
            [[c for c, _ in dense], [c for c, _ in bm25]], k=self.s.rrf_k
        )
        if not fused:
            trace = DocumentRetrievalTrace(
                query=query, filters=filters,
                embedding_backend=self.embedder.backend,
                reranker_backend=self.reranker.backend if self.reranker else "disabled",
                params=self._params(), candidates=[],
            )
            return [], trace

        fused_order = sorted(fused, key=lambda c: fused[c], reverse=True)

        # 4) rerank top-N
        rerank_scores: dict[str, float] = {}
        topn = fused_order[: self.s.rerank_top_n]
        if self.reranker is not None:
            scored = self.reranker.rerank(
                query, [(cid, self.chunks[cid]["text"]) for cid in topn]
            )
            if scored:
                rerank_scores = scored

        def final_key(cid: str) -> float:
            return rerank_scores.get(cid, fused[cid])

        final_order = sorted(fused_order, key=final_key, reverse=True)
        final_rank = {cid: i + 1 for i, cid in enumerate(final_order)}
        selected = final_order[:final_k]

        # 5) build candidates (inspector) + evidence (selected)
        candidates: list[RetrievalCandidate] = []
        for cid in final_order[: max(self.s.rerank_top_n, final_k)]:
            c = self.chunks[cid]
            candidates.append(RetrievalCandidate(
                chunk_id=cid, document=c["document"], page=c.get("page"),
                section=c.get("section"), language=c.get("language"),
                snippet=_snippet(c["text"]),
                dense_rank=dense_rank.get(cid), dense_score=_round(dense_score.get(cid)),
                bm25_rank=bm25_rank.get(cid), bm25_score=_round(bm25_score.get(cid)),
                rrf_score=_round(fused.get(cid), 5),
                rerank_score=_round(rerank_scores.get(cid)),
                final_rank=final_rank.get(cid), selected=cid in selected,
            ))

        evidence: list[Evidence] = []
        for cid in selected:
            c = self.chunks[cid]
            label = f"[{c['document']} p.{c.get('page')}]"
            evidence.append(Evidence(
                id=f"doc::{cid}", source_name="contracts_pdf", source_kind="documents",
                content=c["text"], citation_label=label, score=_round(final_key(cid)),
                language=c.get("language"), document=c["document"], page=c.get("page"),
                chunk_id=cid, section=c.get("section"),
            ))

        trace = DocumentRetrievalTrace(
            query=query, filters=filters,
            embedding_backend=self.embedder.backend,
            reranker_backend=self.reranker.backend if self.reranker else "disabled",
            params=self._params(), candidates=candidates,
        )
        return evidence, trace

    def _params(self) -> dict[str, Any]:
        return {
            "dense_top_k": self.s.dense_top_k, "bm25_top_k": self.s.bm25_top_k,
            "rrf_k": self.s.rrf_k, "rerank_top_n": self.s.rerank_top_n,
            "final_k": self.s.final_k, "vector_backend": self.store.backend,
        }


def _round(x: Optional[float], n: int = 4) -> Optional[float]:
    return round(x, n) if isinstance(x, (int, float)) else None
