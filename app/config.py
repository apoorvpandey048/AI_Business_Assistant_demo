"""Central configuration. Everything is env-driven (prefix ``ABA_``) with safe defaults.

The only secret that matters is the model API key (``ANTHROPIC_API_KEY`` or an
OpenAI-compatible key). Without one the app runs in offline mode using deterministic
fallbacks for routing, SQL generation, and answer extraction.
"""
from __future__ import annotations

import json
import os
from datetime import date
from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root (…/AI_Business_Assistant)
ROOT = Path(__file__).resolve().parent.parent

# Per-provider model defaults. Empty model settings resolve from here so a fresh
# clone "just works" after picking a provider — without sending a Claude model id to
# OpenAI or Ollama. Ollama resolves all three roles to the one validated local model.
PROVIDER_MODEL_DEFAULTS: dict[str, dict[str, str]] = {
    "anthropic": {
        "generation": "claude-opus-4-8",
        "router": "claude-sonnet-4-6",
        "sql": "claude-sonnet-4-6",
    },
    "openai": {
        "generation": "gpt-4o",
        "router": "gpt-4o-mini",
        "sql": "gpt-4o-mini",
    },
    # "ollama" is filled at runtime from `ollama_model` (the supported reference model).
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"),
        env_prefix="ABA_",
        extra="ignore",
        protected_namespaces=(),  # allow field names starting with "model_"
    )

    # --- LLM provider (sprint §13) -----------------------------------------
    # `provider` is the canonical, explicit selector. One of:
    #   openai    — OpenAI or any OpenAI-compatible hosted endpoint (Groq, Gemini compat…)
    #   ollama    — a local Ollama server (OpenAI-compatible transport @ localhost)
    #   anthropic — Claude via the Anthropic SDK (kept for backward compatibility)
    # If unset, we fall back to the legacy `llm_provider` (ABA_LLM_PROVIDER) so existing
    # .env files keep working; `provider` (ABA_PROVIDER) wins when both are set.
    provider: str = ""                  # ABA_PROVIDER   (canonical: openai|ollama|anthropic)
    llm_provider: str = "anthropic"     # ABA_LLM_PROVIDER (legacy: anthropic|openai)

    # Anthropic (key read unprefixed from the environment).
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")

    # OpenAI-compatible (key + base_url). Point base_url at the provider you want.
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_base_url: str = "https://api.openai.com/v1"

    # Local Ollama. `ollama_url` is the server ROOT — the OpenAI-compatible API lives at
    # <url>/v1 and the health probe at <url>/api/tags. One validated reference model.
    ollama_url: str = "http://localhost:11434"   # ABA_OLLAMA_URL
    ollama_model: str = "qwen2.5:7b-instruct"    # ABA_OLLAMA_MODEL (the supported model)
    ollama_timeout: float = 120.0                # ABA_OLLAMA_TIMEOUT (CPU inference is slow)

    # Model ids. Empty → resolved from the selected provider's defaults (see the
    # _resolve_models validator): anthropic→Claude, openai→gpt-4o(+mini), ollama→ollama_model.
    # Set explicitly to override (e.g. Groq/Gemini model names on the openai transport).
    model_generation: str = ""
    model_router: str = ""
    model_sql: str = ""
    offline_mode: str = "auto"  # auto | always | never
    llm_max_tokens: int = 2000
    # Serve an identical prior request from cache instead of re-calling the LLM.
    # Makes repeated/warmed questions instant (great for demos). New questions still
    # go live. Set false to always call the model.
    cache_first: bool = True
    # Persist live LLM responses to the replay cache. Evaluation harnesses set this
    # false so a live eval run can never mutate the demo replay state (a failing
    # live answer must not be replayed as the offline behavior afterwards).
    llm_cache_write: bool = True

    # --- Embeddings --------------------------------------------------------
    # backend: "auto" (OpenAI embeddings when provider=openai on api.openai.com,
    # else local model, else deterministic hashing), or force "openai"/"local"/"hashing".
    embedding_backend: str = "auto"
    embedding_model: str = "BAAI/bge-m3"               # local model name
    # Device for the local sentence-transformers embedder: "" = auto, "cpu", "cuda".
    # On a small GPU (e.g. 6 GB) running a 7B chat model in VRAM, force "cpu" so the
    # embedder does not contend for VRAM with Ollama. See docs/embedding-strategy.md.
    embedding_device: str = ""                          # ABA_EMBEDDING_DEVICE
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
    # 7 (not 5): multi-aspect questions ("suspension AND penalties") need the
    # second aspect's chunk to survive the cut when no cross-encoder reranker is
    # installed; the semantic relevance gate still trims weak tails below this.
    final_k: int = 7
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

    # --- Time anchor -------------------------------------------------------
    # "Today" as seen by SQL generation (date-window questions like "expiring in the
    # next 90 days"). Empty → the real current date. Tests and the evaluation suites
    # pin this to the seed-data anchor (2026-06-08) for deterministic results.
    reference_date: str = ""

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
    def today(self) -> str:
        return self.reference_date.strip() or date.today().isoformat()

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

    # --- provider resolution (sprint §13) ---------------------------------
    @property
    def resolved_provider(self) -> str:
        """The canonical provider name in {openai, ollama, anthropic}.

        ABA_PROVIDER wins; otherwise the legacy ABA_LLM_PROVIDER is honored so
        existing .env files keep working."""
        p = (self.provider or "").strip().lower()
        if p in ("openai", "ollama", "anthropic"):
            return p
        legacy = (self.llm_provider or "anthropic").strip().lower()
        return legacy if legacy in ("openai", "anthropic") else "anthropic"

    @property
    def transport_family(self) -> str:
        """Which SDK transport carries the call: anthropic vs OpenAI-compatible.
        Ollama speaks the OpenAI-compatible protocol, so it rides the openai transport."""
        return "anthropic" if self.resolved_provider == "anthropic" else "openai"

    @property
    def provider_base_url(self) -> str:
        """Base URL for the OpenAI-compatible client (ollama → <ollama_url>/v1)."""
        if self.resolved_provider == "ollama":
            return self.ollama_url.rstrip("/") + "/v1"
        return self.openai_base_url

    @property
    def is_local_endpoint(self) -> bool:
        if self.resolved_provider == "ollama":
            return True
        b = self.openai_base_url or ""
        return any(x in b for x in ("localhost", "127.0.0.1", "11434"))

    @property
    def has_api_key(self) -> bool:
        p = self.resolved_provider
        if p == "ollama":
            return True  # a local server needs no key
        if p == "openai":
            # local OpenAI-compatible endpoints need no key
            return bool(self.openai_key) or self.is_local_endpoint
        return bool(self.anthropic_key)

    @property
    def use_live_llm(self) -> bool:
        """Whether to attempt real model calls."""
        if self.offline_mode == "always":
            return False
        if self.offline_mode == "never":
            return True
        return self.has_api_key  # auto

    # --- model defaults resolution (sprint §13) ----------------------------
    @model_validator(mode="after")
    def _resolve_models(self) -> "Settings":
        """Fill any empty model id from the selected provider's defaults so a fresh
        clone works after just choosing a provider. Explicit ABA_MODEL_* always wins."""
        p = self.resolved_provider
        if p == "ollama":
            defaults = {"generation": self.ollama_model,
                        "router": self.ollama_model,
                        "sql": self.ollama_model}
        else:
            defaults = PROVIDER_MODEL_DEFAULTS.get(p, PROVIDER_MODEL_DEFAULTS["anthropic"])
        if not (self.model_generation or "").strip():
            self.model_generation = defaults["generation"]
        if not (self.model_router or "").strip():
            self.model_router = defaults["router"]
        if not (self.model_sql or "").strip():
            self.model_sql = defaults["sql"]
        return self


# --- runtime provider override (sprint §14) --------------------------------
# A UI provider switch is a *runtime override* layered over the env defaults: it is
# written to data/runtime/provider.json so it survives a reload AND a process restart,
# and `get_settings()` applies it on top of the environment. `ABA_PROVIDER` in the env
# stays the default for a fresh clone / headless deployment; the override wins until the
# user reverts to the server default. Because a switch changes the transport family, the
# override carries the new provider's *reference* models so an env `ABA_MODEL_*` pin for
# one provider can't leak a wrong model id (e.g. gpt-4o) to another (Ollama).

_SUPPORTED_PROVIDERS = ("openai", "ollama", "anthropic")


def _runtime_override_path() -> Path:
    # Provider-independent: data dir is env-driven (default "data"); never depends on the
    # override itself, so there is no recursion with get_settings().
    d = os.environ.get("ABA_DATA_DIR", "data")
    base = Path(d)
    base = base if base.is_absolute() else (ROOT / base)
    return base / "runtime" / "provider.json"


def default_models_for(provider: str, ollama_model: str) -> dict[str, str]:
    """The reference generation/router/sql model ids for a provider (no env, no override)."""
    if provider == "ollama":
        return {"generation": ollama_model, "router": ollama_model, "sql": ollama_model}
    d = PROVIDER_MODEL_DEFAULTS.get(provider, PROVIDER_MODEL_DEFAULTS["anthropic"])
    return dict(d)


def _load_provider_override() -> dict | None:
    """Read+validate the persisted override. Returns None on absence or any error."""
    try:
        raw = json.loads(_runtime_override_path().read_text("utf-8"))
        p = str(raw.get("provider", "")).strip().lower()
        if p not in _SUPPORTED_PROVIDERS:
            return None
        models = raw.get("models") or {}
        if not all(str(models.get(k, "")).strip() for k in ("generation", "router", "sql")):
            return None
        return {"provider": p, "models": {k: str(models[k]) for k in ("generation", "router", "sql")}}
    except Exception:
        return None


def set_runtime_provider(provider: str) -> dict:
    """Persist a UI provider switch and invalidate the settings cache.

    Caller is responsible for resetting the LLM client singleton (see
    app.llm.client.reset_llm) so the next call uses the new provider."""
    p = (provider or "").strip().lower()
    if p not in _SUPPORTED_PROVIDERS:
        raise ValueError(
            f"Unknown provider {provider!r}. Choose one of: {', '.join(_SUPPORTED_PROVIDERS)}."
        )
    base = Settings()  # env-driven base (the override is NOT applied here)
    payload = {"provider": p, "models": default_models_for(p, base.ollama_model)}
    path = _runtime_override_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")
    get_settings.cache_clear()
    return payload


def clear_runtime_provider() -> None:
    """Remove the override and revert to the env/`ABA_PROVIDER` default."""
    try:
        _runtime_override_path().unlink()
    except FileNotFoundError:
        pass
    except Exception:
        pass
    get_settings.cache_clear()


def provider_override_state() -> dict:
    """What is applied now vs. the server (env) default, for the UI's current/applied view."""
    ov = _load_provider_override()
    env_default = Settings().resolved_provider          # env, ignoring any override
    applied = get_settings().resolved_provider           # what calls actually use
    return {
        "applied": applied,
        "default": env_default,
        "source": "override" if ov else "env",
        "overridden": ov is not None,
    }


@lru_cache
def get_settings() -> Settings:
    ov = _load_provider_override()
    if ov:
        # init kwargs win over env, so the override's provider + reference models apply
        # cleanly on top of everything else the environment configures.
        return Settings(
            provider=ov["provider"],
            model_generation=ov["models"]["generation"],
            model_router=ov["models"]["router"],
            model_sql=ov["models"]["sql"],
        )
    return Settings()
