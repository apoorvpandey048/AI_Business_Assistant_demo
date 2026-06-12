"""AnthropicProvider — Claude via the Anthropic SDK.

A first-class provider, not a legacy shim: the structured-output path uses Anthropic's
native `output_config.format` JSON-schema mode. Kept fully supported for backward
compatibility even though the sprint's validation matrix focuses on OpenAI + Ollama.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from app.llm.providers.base import LLMProvider
from app.models import ProviderStatus

try:
    import anthropic
except Exception:  # pragma: no cover
    anthropic = None  # type: ignore


class AnthropicProvider(LLMProvider):
    name = "anthropic"
    transport = "anthropic"

    def __init__(self, settings) -> None:
        super().__init__(settings)
        self._client = None

    @property
    def client(self):
        if self._client is None and anthropic is not None and self.s.anthropic_key:
            self._client = anthropic.Anthropic(api_key=self.s.anthropic_key)
        return self._client

    def available(self) -> bool:
        return self.client is not None

    def generate(self, *, model, system, user, schema, max_tokens):
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens or self.s.llm_max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        if schema is not None:
            kwargs["output_config"] = {"format": {"type": "json_schema", "schema": schema}}
        resp = self.client.messages.create(**kwargs)
        text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
        usage = (getattr(resp.usage, "input_tokens", None),
                 getattr(resp.usage, "output_tokens", None))
        return (json.loads(text) if schema is not None else text), usage

    def status(self) -> ProviderStatus:
        s = self.s
        st = self._base_status()
        if not s.use_live_llm:
            st.connection, st.health = "disconnected", "unavailable"
            st.detail = "Offline mode — deterministic answers (no model calls)."
            if not s.anthropic_key:
                st.fix = "Set ANTHROPIC_API_KEY and ABA_OFFLINE_MODE=auto for live Claude answers."
            return st
        if s.anthropic_key:
            st.connection, st.health = "connected", "healthy"
            st.detail = "Anthropic API key configured (liveness confirmed on first answer)."
        else:
            st.connection, st.health = "disconnected", "unavailable"
            st.detail = "No Anthropic API key configured."
            st.fix = "Set ANTHROPIC_API_KEY in your .env."
        return st
