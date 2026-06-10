"""Pluggable dense vector store.

Default: an in-process NumPy store (zero dependencies, fully deterministic) — ideal
for a demo whose value is orchestration, not the vector DB. A Qdrant adapter behind
the same interface is a one-flag production swap (ABA_VECTOR_BACKEND=qdrant), which
reinforces the thesis we told the client: orchestration matters more than the store.
"""
from __future__ import annotations

from typing import Optional, Protocol

import numpy as np

from app.config import get_settings


class VectorStore(Protocol):
    backend: str

    def add(self, ids: list[str], vectors: np.ndarray) -> None: ...

    def extend(self, ids: list[str], vectors: np.ndarray) -> None: ...

    def search(
        self, query: np.ndarray, k: int, allowed_ids: Optional[set[str]] = None
    ) -> list[tuple[str, float]]: ...


class NumpyVectorStore:
    backend = "numpy"

    def __init__(self) -> None:
        self._ids: list[str] = []
        self._index: dict[str, int] = {}
        self._matrix: Optional[np.ndarray] = None

    def add(self, ids: list[str], vectors: np.ndarray) -> None:
        self._ids = list(ids)
        self._index = {i: n for n, i in enumerate(ids)}
        self._matrix = np.asarray(vectors, dtype=np.float32)

    def extend(self, ids: list[str], vectors: np.ndarray) -> None:
        """Append new vectors at runtime (uploaded documents) without re-embedding."""
        new = np.asarray(vectors, dtype=np.float32)
        if new.size == 0 or len(ids) == 0:
            return
        if self._matrix is None or self._matrix.size == 0:
            self.add(list(ids), new)
            return
        base = len(self._ids)
        self._ids.extend(ids)
        for n, i in enumerate(ids):
            self._index[i] = base + n
        self._matrix = np.vstack([self._matrix, new])

    def search(
        self, query: np.ndarray, k: int, allowed_ids: Optional[set[str]] = None
    ) -> list[tuple[str, float]]:
        if self._matrix is None or len(self._ids) == 0:
            return []
        q = np.asarray(query, dtype=np.float32).reshape(-1)
        scores = self._matrix @ q  # vectors are L2-normalized → cosine similarity
        if allowed_ids is not None:
            mask = np.full(len(self._ids), -np.inf, dtype=np.float32)
            for i in allowed_ids:
                idx = self._index.get(i)
                if idx is not None:
                    mask[idx] = 0.0
            scores = scores + mask
        k = min(k, len(self._ids))
        top = np.argpartition(-scores, kth=k - 1)[:k]
        top = top[np.argsort(-scores[top])]
        return [(self._ids[i], float(scores[i])) for i in top if np.isfinite(scores[i])]


class QdrantVectorStore:
    """Production swap. Same interface; stores dense vectors in Qdrant."""

    backend = "qdrant"

    def __init__(self) -> None:
        from qdrant_client import QdrantClient
        from qdrant_client.http import models as qm

        s = get_settings()
        self._qm = qm
        self.collection = s.qdrant_collection
        self.client = QdrantClient(url=s.qdrant_url)
        self._ids: list[str] = []

    def add(self, ids: list[str], vectors: np.ndarray) -> None:
        qm = self._qm
        dim = int(vectors.shape[1])
        self.client.recreate_collection(
            collection_name=self.collection,
            vectors_config=qm.VectorParams(size=dim, distance=qm.Distance.COSINE),
        )
        self._ids = list(ids)
        points = [
            qm.PointStruct(id=n, vector=vectors[n].tolist(), payload={"chunk_id": ids[n]})
            for n in range(len(ids))
        ]
        self.client.upsert(collection_name=self.collection, points=points)

    def extend(self, ids: list[str], vectors: np.ndarray) -> None:
        """Append new points to the existing collection (uploaded documents)."""
        if len(ids) == 0:
            return
        qm = self._qm
        base = len(self._ids)
        self._ids.extend(ids)
        points = [
            qm.PointStruct(id=base + n, vector=vectors[n].tolist(),
                           payload={"chunk_id": ids[n]})
            for n in range(len(ids))
        ]
        self.client.upsert(collection_name=self.collection, points=points)

    def search(
        self, query: np.ndarray, k: int, allowed_ids: Optional[set[str]] = None
    ) -> list[tuple[str, float]]:
        qm = self._qm
        flt = None
        if allowed_ids is not None:
            flt = qm.Filter(must=[qm.FieldCondition(
                key="chunk_id", match=qm.MatchAny(any=list(allowed_ids)))])
        hits = self.client.search(
            collection_name=self.collection,
            query_vector=np.asarray(query, dtype=np.float32).reshape(-1).tolist(),
            limit=k, query_filter=flt,
        )
        return [(h.payload["chunk_id"], float(h.score)) for h in hits]


def make_vector_store() -> VectorStore:
    s = get_settings()
    if s.vector_backend == "qdrant":
        try:
            return QdrantVectorStore()
        except Exception:
            pass  # fall back to in-process store if Qdrant isn't reachable
    return NumpyVectorStore()
