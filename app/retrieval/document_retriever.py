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
from app.retrieval.intent import QueryIntent, detect_intent, text_hits
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
        vectors = self._embed_cached(texts)
        self.store.add(ids, vectors)
        self.bm25.build(ids, texts)

    def add_chunks(self, new_chunks: list[dict[str, Any]]) -> int:
        """Index additional chunks at runtime (uploaded PDFs) without re-embedding the
        existing corpus. Embeds only the new chunks, appends them to the dense store,
        and rebuilds the (cheap) BM25 index over the full corpus. Returns how many were
        newly added (duplicates by chunk_id are skipped)."""
        fresh = [c for c in new_chunks if c["chunk_id"] not in self.chunks]
        if not fresh:
            return 0
        ids = [c["chunk_id"] for c in fresh]
        texts = [c["text"] for c in fresh]
        vectors = self.embedder.embed(texts)
        for c in fresh:
            self.chunks[c["chunk_id"]] = c
        self.store.extend(ids, vectors)
        # BM25 has no incremental API and is cheap to rebuild over the full corpus.
        all_ids = list(self.chunks)
        all_texts = [self.chunks[i]["text"] for i in all_ids]
        self.bm25.build(all_ids, all_texts)
        return len(fresh)

    def _embed_cached(self, texts: list[str]) -> np.ndarray:
        """Cache document embeddings on disk so (re)starts don't re-call the API.
        Keyed by backend + corpus content, so any change re-embeds automatically."""
        import hashlib

        cdir = self.s.cache_dir / "embeddings"

        def path_for(backend: str):
            h = hashlib.sha256(backend.encode("utf-8"))
            for t in texts:
                h.update(b"\x00")
                h.update(t.encode("utf-8"))
            return cdir / (h.hexdigest()[:40] + ".npy")

        cached = path_for(self.embedder.backend)
        if cached.exists():
            try:
                return np.load(cached)
            except Exception:
                pass
        vectors = self.embedder.embed(texts)  # may downgrade backend on failure
        try:
            cdir.mkdir(parents=True, exist_ok=True)
            np.save(path_for(self.embedder.backend), vectors)
        except Exception:
            pass
        return vectors

    @property
    def n_chunks(self) -> int:
        return len(self.chunks)

    def _allowed_ids(self, filters: dict[str, Any]) -> Optional[set[str]]:
        docs = filters.get("documents")
        langs = filters.get("languages")
        if not docs and not langs:
            return None
        ids = set(self.chunks)
        if docs:
            docset = set(docs)
            ids = {cid for cid in ids if self.chunks[cid]["document"] in docset}
        if langs:
            langset = set(langs)
            lang_ids = {cid for cid in ids if self.chunks[cid].get("language") in langset}
            # Only apply the language filter when it leaves something to retrieve,
            # so a language with no matching chunks degrades gracefully.
            if lang_ids:
                ids = lang_ids
        return ids

    # -- retrieve -----------------------------------------------------------
    def retrieve(
        self, query: str, filters: Optional[dict[str, Any]] = None,
        final_k: Optional[int] = None, intent: Optional[QueryIntent] = None,
    ) -> tuple[list[Evidence], DocumentRetrievalTrace]:
        filters = filters or {}
        final_k = final_k or self.s.final_k
        allowed = self._allowed_ids(filters)
        intent = intent or detect_intent(query)
        # Search on the intent's terms, not the instruction sentence — so "find the
        # document containing X" searches for X, not for "find/document/containing".
        search_q = intent.search_query or query

        # 1) dense + 2) bm25 over the intent-aware search query
        qvec = self.embedder.embed_one(search_q)
        dense = self.store.search(qvec, self.s.dense_top_k, allowed_ids=allowed)
        dense_rank = {cid: i + 1 for i, (cid, _) in enumerate(dense)}
        dense_score = {cid: sc for cid, sc in dense}

        bm25 = self.bm25.search(search_q, self.s.bm25_top_k)
        if allowed is not None:
            bm25 = [(cid, sc) for cid, sc in bm25 if cid in allowed]
        bm25_rank = {cid: i + 1 for i, (cid, _) in enumerate(bm25)}
        bm25_score = {cid: sc for cid, sc in bm25}

        # 3) RRF fusion (always computed — drives the semantic path and the inspector)
        fused = reciprocal_rank_fusion(
            [[c for c, _ in dense], [c for c, _ in bm25]], k=self.s.rrf_k
        )
        fused_order = sorted(fused, key=lambda c: fused[c], reverse=True)

        # Exact keyword hits: chunks that literally contain a distinctive search term.
        hit_ids: set[str] = set()
        if intent.gate_terms:
            hit_ids = {cid for cid, c in self.chunks.items()
                       if text_hits(c["text"], intent.gate_terms)}
            if allowed is not None:
                hit_ids &= allowed

        rerank_scores: dict[str, float] = {}

        if intent.mode == "keyword":
            # KEYWORD path: only chunks that actually contain the term are evidence,
            # ranked BM25-first (exact lexical match) then dense. This is what stops a
            # semantically-similar-but-irrelevant chunk from ever being surfaced.
            if not hit_ids:
                # Explicit lookup, term found nowhere → return NOTHING rather than guess
                # with semantically-similar text. Honesty beats a confident wrong answer.
                strategy = (f"{intent.reason} No document contains the term — "
                            "returning no evidence (declining to guess).")
                return [], self._empty_trace(query, filters, intent, "keyword", strategy)
            def kkey(cid: str):
                return (bm25_score.get(cid, 0.0), dense_score.get(cid, 0.0),
                        fused.get(cid, 0.0))
            order = sorted(hit_ids, key=kkey, reverse=True)
            selected = order[:final_k]
            used_mode = "keyword"
            strategy = f"{intent.reason} {len(hit_ids)} exact match(es); other passages excluded."
        else:
            # SEMANTIC path: hybrid + optional rerank, then trim the weak tail.
            used_mode = "semantic"
            strategy = intent.reason
            if not fused:
                return [], self._empty_trace(query, filters, intent, used_mode, strategy)

            topn = fused_order[: self.s.rerank_top_n]
            if self.reranker is not None:
                scored = self.reranker.rerank(
                    search_q, [(cid, self.chunks[cid]["text"]) for cid in topn]
                )
                if scored:
                    rerank_scores = scored
            order = sorted(fused_order, key=lambda c: rerank_scores.get(c, fused[c]),
                           reverse=True)
            selected = self._semantic_select(order, fused, final_k)

        def score_of(cid: str) -> Optional[float]:
            return rerank_scores.get(cid, fused.get(cid, 0.0))

        final_rank = {cid: i + 1 for i, cid in enumerate(order)}
        sel_set = set(selected)

        # 4) candidates (inspector) — the considered set with full scoring + hit flag
        candidates: list[RetrievalCandidate] = []
        for cid in order[: max(self.s.rerank_top_n, final_k)]:
            c = self.chunks[cid]
            candidates.append(RetrievalCandidate(
                chunk_id=cid, document=c["document"], page=c.get("page"),
                section=c.get("section"), language=c.get("language"),
                snippet=_snippet(c["text"]),
                dense_rank=dense_rank.get(cid), dense_score=_round(dense_score.get(cid)),
                bm25_rank=bm25_rank.get(cid), bm25_score=_round(bm25_score.get(cid)),
                rrf_score=_round(fused.get(cid), 5),
                rerank_score=_round(rerank_scores.get(cid)),
                final_rank=final_rank.get(cid), selected=cid in sel_set,
                keyword_hit=cid in hit_ids,
            ))

        # 5) evidence (selected only)
        evidence: list[Evidence] = []
        for cid in selected:
            c = self.chunks[cid]
            label = f"[{c['document']} p.{c.get('page')}]"
            evidence.append(Evidence(
                id=f"doc::{cid}", source_name="contracts_pdf", source_kind="documents",
                content=c["text"], citation_label=label, score=_round(score_of(cid)),
                language=c.get("language"), document=c["document"], page=c.get("page"),
                chunk_id=cid, section=c.get("section"),
            ))

        trace = DocumentRetrievalTrace(
            query=query, filters=filters,
            embedding_backend=self.embedder.backend,
            reranker_backend=self.reranker.backend if self.reranker else "disabled",
            params=self._params(), candidates=candidates,
            intent=used_mode, search_terms=intent.terms or intent.gate_terms,
            exact_hits=len(hit_ids), strategy=strategy,
        )
        return evidence, trace

    def _semantic_select(
        self, order: list[str], fused: dict[str, float], final_k: int
    ) -> list[str]:
        """Keep passages within `keep_ratio` of the top fusion score (trim the clearly
        weaker tail), but never fewer than `min_keep`, never more than `final_k`."""
        if not order:
            return []
        top = max(fused.get(order[0], 0.0), 1e-9)
        floor = max(top * self.s.semantic_keep_ratio, self.s.min_evidence_score)
        kept: list[str] = []
        for i, cid in enumerate(order):
            if len(kept) >= final_k:
                break
            if i < self.s.semantic_min_keep or fused.get(cid, 0.0) >= floor:
                kept.append(cid)
        return kept

    def _empty_trace(self, query, filters, intent, used_mode, strategy):
        return DocumentRetrievalTrace(
            query=query, filters=filters,
            embedding_backend=self.embedder.backend,
            reranker_backend=self.reranker.backend if self.reranker else "disabled",
            params=self._params(), candidates=[],
            intent=used_mode, search_terms=intent.terms or intent.gate_terms,
            exact_hits=0, strategy=strategy,
        )

    def _params(self) -> dict[str, Any]:
        return {
            "dense_top_k": self.s.dense_top_k, "bm25_top_k": self.s.bm25_top_k,
            "rrf_k": self.s.rrf_k, "rerank_top_n": self.s.rerank_top_n,
            "final_k": self.s.final_k, "vector_backend": self.store.backend,
        }


def _round(x: Optional[float], n: int = 4) -> Optional[float]:
    return round(x, n) if isinstance(x, (int, float)) else None
