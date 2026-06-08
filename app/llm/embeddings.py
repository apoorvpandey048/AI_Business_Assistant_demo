"""Multilingual embeddings with a backend ladder.

Selection (ABA_EMBEDDING_BACKEND, default "auto"):
- **openai**  → OpenAI-compatible embeddings (e.g. text-embedding-3-small): high
                quality, multilingual (incl. Hebrew), cheap, no heavy local model.
                Auto-selected when provider=openai on api.openai.com with a key.
- **local**   → a local sentence-transformers model (BGE-M3 / e5): offline, no key.
- **hashing** → deterministic character-n-gram hashing (no deps). Always available;
                uses a stable hash (NOT Python's salted hash) so retrieval is
                reproducible across processes.

The trace always reports which backend produced the vectors.
"""
from __future__ import annotations

import hashlib
import re
import struct
from typing import Optional

import numpy as np

from app.config import get_settings

try:
    import openai
except Exception:  # pragma: no cover
    openai = None  # type: ignore

_WORD = re.compile(r"\w+", re.UNICODE)


def _stable_hash(s: str) -> int:
    # deterministic across processes (Python's builtin hash() is salted by PYTHONHASHSEED)
    return struct.unpack("<I", hashlib.blake2b(s.encode("utf-8"), digest_size=4).digest())[0]


def _l2(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return v / n


class _HashingEmbedder:
    backend = "hashing (deterministic)"

    def __init__(self, dim: int = 512) -> None:
        self.dim = dim

    def _features(self, text: str):
        for w in _WORD.findall((text or "").lower()):
            yield f"w:{w}"
            padded = f"#{w}#"
            for n in (3, 4):
                for i in range(len(padded) - n + 1):
                    yield f"c{n}:{padded[i:i + n]}"

    def encode(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, t in enumerate(texts):
            for feat in self._features(t):
                out[i, _stable_hash(feat) % self.dim] += 1.0
        return _l2(out)


class _SentenceTransformerEmbedder:
    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_name)
        self.backend = f"local:{model_name}"

    def encode(self, texts: list[str]) -> np.ndarray:
        return np.asarray(
            self.model.encode(texts, normalize_embeddings=True, show_progress_bar=False),
            dtype=np.float32,
        )


class _OpenAIEmbedder:
    def __init__(self, settings) -> None:
        self.client = openai.OpenAI(
            api_key=settings.openai_key or "no-key", base_url=settings.openai_base_url
        )
        self.model = settings.openai_embed_model
        self.backend = f"openai:{self.model}"

    def encode(self, texts: list[str]) -> np.ndarray:
        vecs: list[list[float]] = []
        for i in range(0, len(texts), 256):
            batch = [t if (t and t.strip()) else " " for t in texts[i:i + 256]]
            resp = self.client.embeddings.create(model=self.model, input=batch)
            vecs.extend(d.embedding for d in resp.data)
        return _l2(np.asarray(vecs, dtype=np.float32))


class EmbeddingModel:
    _instance: Optional["EmbeddingModel"] = None

    def __init__(self) -> None:
        s = get_settings()
        pref = (s.embedding_backend or "auto").lower()
        want_openai = pref == "openai" or (
            pref == "auto"
            and s.llm_provider == "openai"
            and "openai.com" in (s.openai_base_url or "")
            and bool(s.openai_key)
        )

        # Ordered candidates, selected by construction only (no network probe — that
        # added a slow cold API call to startup). Runtime failures (e.g. a rotated key)
        # are caught in embed() and degrade to the hashing backend, so we never crash.
        candidates: list = []
        if want_openai and openai is not None:
            candidates.append(lambda: _OpenAIEmbedder(s))
        if pref in ("auto", "local"):
            candidates.append(lambda: _SentenceTransformerEmbedder(s.embedding_model))
        candidates.append(lambda: _HashingEmbedder())

        impl = None
        for make in candidates:
            try:
                impl = make()
                break
            except Exception:
                continue
        self.impl = impl or _HashingEmbedder()
        self.backend = self.impl.backend
        self._query_cache: dict[str, np.ndarray] = {}

    @classmethod
    def get(cls) -> "EmbeddingModel":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 1), dtype=np.float32)
        try:
            return self.impl.encode(texts)
        except Exception:
            # configured backend failed at runtime (e.g. rotated key / network) —
            # degrade to the always-available deterministic hashing backend.
            if not isinstance(self.impl, _HashingEmbedder):
                self.impl = _HashingEmbedder()
                self.backend = self.impl.backend
                return self.impl.encode(texts)
            raise

    def embed_one(self, text: str) -> np.ndarray:
        # memoize query embeddings so repeated/clicked questions don't re-embed
        v = self._query_cache.get(text)
        if v is None:
            v = self.embed([text])[0]
            self._query_cache[text] = v
        return v
