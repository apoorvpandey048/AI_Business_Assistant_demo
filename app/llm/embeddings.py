"""Multilingual embeddings.

Default (production / Docker): a local sentence-transformers model — BGE-M3 or
multilingual-e5 — which handles English + Hebrew in one vector space, runs offline,
and needs no API key.

Fallback (when the model isn't installed, e.g. fast local dev / CI): a deterministic
character-n-gram hashing embedder. It is multilingual-agnostic (works on Hebrew too)
and keeps the dense branch meaningful enough to demonstrate the pipeline. The trace
always reports which backend produced the vectors, so nothing is hidden.
"""
from __future__ import annotations

import re
from typing import Optional

import numpy as np

from app.config import get_settings

_WORD = re.compile(r"\w+", re.UNICODE)


class _HashingEmbedder:
    """Deterministic, dependency-free embedding: hashed word + char n-grams, TF, L2."""

    backend = "hashing-fallback"

    def __init__(self, dim: int = 512) -> None:
        self.dim = dim

    def _features(self, text: str):
        text = text.lower()
        for w in _WORD.findall(text):
            yield f"w:{w}"
            padded = f"#{w}#"
            for n in (3, 4):
                for i in range(len(padded) - n + 1):
                    yield f"c{n}:{padded[i:i + n]}"

    def encode(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, t in enumerate(texts):
            for feat in self._features(t or ""):
                h = hash(feat) % self.dim
                out[i, h] += 1.0
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return out / norms


class _SentenceTransformerEmbedder:
    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer  # heavy import, lazy

        self.model = SentenceTransformer(model_name)
        self.backend = f"sentence-transformers:{model_name}"

    def encode(self, texts: list[str]) -> np.ndarray:
        vecs = self.model.encode(
            texts, normalize_embeddings=True, show_progress_bar=False
        )
        return np.asarray(vecs, dtype=np.float32)


class EmbeddingModel:
    """Singleton-ish wrapper that prefers the local model, falls back gracefully."""

    _instance: Optional["EmbeddingModel"] = None

    def __init__(self) -> None:
        s = get_settings()
        self.impl = None
        try:
            self.impl = _SentenceTransformerEmbedder(s.embedding_model)
        except Exception:
            self.impl = _HashingEmbedder()
        self.backend = self.impl.backend

    @classmethod
    def get(cls) -> "EmbeddingModel":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 1), dtype=np.float32)
        return self.impl.encode(texts)

    def embed_one(self, text: str) -> np.ndarray:
        return self.embed([text])[0]
