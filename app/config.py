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
    # Read the (unprefixed) Anthropic key directly from the environment.
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    llm_provider: str = "anthropic"
    model_generation: str = "claude-opus-4-8"
    model_router: str = "claude-sonnet-4-6"
    model_sql: str = "claude-sonnet-4-6"
    offline_mode: str = "auto"  # auto | always | never
    llm_max_tokens: int = 2000

    # --- Embeddings --------------------------------------------------------
    embedding_model: str = "BAAI/bge-m3"
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
    min_evidence_score: float = 0.02

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
    def has_api_key(self) -> bool:
        key = self.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")
        return bool(key and key.strip())

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
