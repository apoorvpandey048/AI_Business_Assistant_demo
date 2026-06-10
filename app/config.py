"""Central configuration. Everything is env-driven (prefix ``ABA_``) with safe defaults.

The only secret that matters is ``ANTHROPIC_API_KEY``. Without it the app runs in
offline mode using deterministic cached answers for the scripted demo questions.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root (…/AI_Business_Assistant)
ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"),
        env_prefix="ABA_",
        extra="ignore",
        protected_namespaces=(),  # allow field names starting with "model_"
    )

    # --- LLM ---------------------------------------------------------------
    # provider: "anthropic" or "openai" (the latter is any OpenAI-compatible
    # endpoint — OpenAI, Groq, Gemini's compat API, Ollama, OpenRouter, …).
    llm_provider: str = "anthropic"

    # Anthropic (key read unprefixed from the environment).
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")

    # OpenAI-compatible (key + base_url). Point base_url at the provider you want.
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_base_url: str = "https://api.openai.com/v1"

    model_generation: str = "claude-opus-4-8"
    model_router: str = "claude-sonnet-4-6"
    model_sql: str = "claude-sonnet-4-6"
    offline_mode: str = "auto"  # auto | always | never
    llm_max_tokens: int = 2000
    # Serve an identical prior request from cache instead of re-calling the LLM.
    # Makes repeated/warmed questions instant (great for demos). New questions still
    # go live. Set false to always call the model.
    cache_first: bool = True

    # --- Embeddings --------------------------------------------------------
    # backend: "auto" (OpenAI embeddings when provider=openai on api.openai.com,
    # else local model, else deterministic hashing), or force "openai"/"local"/"hashing".
    embedding_backend: str = "auto"
    embedding_model: str = "BAAI/bge-m3"               # local model name
    openai_embed_model: str = "text-embedding-3-small"  # used for the openai backend
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    enable_rerank: bool = True

    # --- Vector store ------------------------------------------------------
    vector_backend: str = "numpy"  # numpy | qdrant
    qdrant_url: str = "http://qdrant:6333"
    qdrant_collection: str = "documents"

    # --- Retrieval tuning --------------------------------------------------
    dense_top_k: int = 20
    bm25_top_k: int = 20
    rrf_k: int = 60
    final_k: int = 5
    rerank_top_n: int = 20
    # Semantic relevance gate: keep passages within `keep_ratio` of the top fusion score
    # (drops the clearly-weaker tail) but never return fewer than `min_keep` for a real
    # question. `min_evidence_score` is an absolute fusion-score floor for junk removal.
    min_evidence_score: float = 0.015
    semantic_keep_ratio: float = 0.35
    semantic_min_keep: int = 3

    # --- SQL safety --------------------------------------------------------
    sql_row_limit: int = 200
    sql_timeout_seconds: int = 5

    # --- Paths -------------------------------------------------------------
    data_dir: str = "data"

    # ----------------------------------------------------------------------
    @property
    def data_path(self) -> Path:
        p = Path(self.data_dir)
        return p if p.is_absolute() else (ROOT / p)

    @property
    def pdf_dir(self) -> Path:
        return self.data_path / "pdfs"

    @property
    def db_path(self) -> Path:
        return self.data_path / "business.db"

    @property
    def cache_dir(self) -> Path:
        return self.data_path / "cache"

    @property
    def anthropic_key(self) -> str:
        return (self.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY") or "").strip()

    @property
    def openai_key(self) -> str:
        return (
            self.openai_api_key
            or os.environ.get("OPENAI_API_KEY")
            or os.environ.get("ABA_OPENAI_API_KEY")
            or ""
        ).strip()

    @property
    def is_local_endpoint(self) -> bool:
        b = self.openai_base_url or ""
        return any(x in b for x in ("localhost", "127.0.0.1", "11434"))

    @property
    def has_api_key(self) -> bool:
        if self.llm_provider == "openai":
            # local endpoints (e.g. Ollama) need no key
            return bool(self.openai_key) or self.is_local_endpoint
        return bool(self.anthropic_key)

    @property
    def use_live_llm(self) -> bool:
        """Whether to attempt real Claude calls."""
        if self.offline_mode == "always":
            return False
        if self.offline_mode == "never":
            return True
        return self.has_api_key  # auto


@lru_cache
def get_settings() -> Settings:
    return Settings()
