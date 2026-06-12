"""LLMProvider — the provider strategy interface (sprint §13, Workstream 2).

Each provider isolates ONE transport's quirks (SDK, JSON mode, base URL, timeout,
health probe) behind three operations. The `LLMClient` owns everything that is
provider-agnostic — the response cache, the offline/deterministic fallback ladder, and
`LLMCall` accounting — and delegates only the actual call and the health probe here.

Contract (matches the pre-refactor `_dispatch`, so call sites are untouched):
    generate(model, system, user, schema, max_tokens) -> (result, (in_tok, out_tok))
        result is a dict when `schema` is provided, else a str.
    status() -> ProviderStatus   (read-only diagnostics for Settings)
    available() -> bool          (can a live call be attempted right now?)
"""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any, Optional

from app.config import Settings
from app.models import ProviderStatus


def extract_json(text: str) -> Any:
    """Tolerantly pull a JSON object out of a model response (handles code fences).

    Shared by the OpenAI-compatible providers (OpenAI, Ollama) whose JSON mode is not
    always honored by every model — qwen2.5 included."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?", "", t).strip()
        t = re.sub(r"```$", "", t).strip()
    try:
        return json.loads(t)
    except Exception:
        start, end = t.find("{"), t.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(t[start:end + 1])
        raise


class LLMProvider(ABC):
    name: str = "base"            # openai | ollama | anthropic
    transport: str = ""          # anthropic | openai-compatible

    def __init__(self, settings: Settings) -> None:
        self.s = settings

    @abstractmethod
    def available(self) -> bool:
        """Whether a live call can be attempted (SDK importable + minimally configured)."""

    @abstractmethod
    def generate(self, *, model: str, system: str, user: str,
                 schema: Optional[dict], max_tokens: Optional[int]) -> tuple[Any, tuple]:
        """Run one model call. Returns (result, (input_tokens, output_tokens))."""

    @abstractmethod
    def status(self) -> ProviderStatus:
        """Read-only provider diagnostics for Settings (never raises)."""

    # -- shared status scaffolding -----------------------------------------
    def _base_status(self) -> ProviderStatus:
        s = self.s
        return ProviderStatus(
            provider=s.resolved_provider,
            transport=self.transport,
            generation_model=s.model_generation,
            router_model=s.model_router,
            sql_model=s.model_sql,
            base_url=s.provider_base_url if self.transport == "openai-compatible" else None,
            offline=not s.use_live_llm,
        )
