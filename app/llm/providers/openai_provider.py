"""OpenAIProvider — any OpenAI-compatible hosted endpoint (OpenAI, Groq, Gemini compat…).

Structured output uses JSON mode where the endpoint supports it, with a tolerant JSON
extractor otherwise, so the same call sites work across every OpenAI-compatible backend.
`OllamaProvider` subclasses this and changes only the timeout and the health probe.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from app.llm.providers.base import LLMProvider, extract_json
from app.models import ProviderStatus

try:
    import openai
except Exception:  # pragma: no cover
    openai = None  # type: ignore


class OpenAIProvider(LLMProvider):
    name = "openai"
    transport = "openai-compatible"

    def __init__(self, settings) -> None:
        super().__init__(settings)
        self._client = None

    # -- client ------------------------------------------------------------
    def _timeout(self) -> Optional[float]:
        return None  # hosted endpoints use the SDK default

    @property
    def client(self):
        if self._client is None and openai is not None:
            kwargs: dict[str, Any] = {
                "api_key": self.s.openai_key or "no-key",   # local endpoints ignore it
                "base_url": self.s.provider_base_url,
            }
            t = self._timeout()
            if t is not None:
                kwargs["timeout"] = t
            self._client = openai.OpenAI(**kwargs)
        return self._client

    def available(self) -> bool:
        return self.client is not None

    # -- call --------------------------------------------------------------
    def generate(self, *, model, system, user, schema, max_tokens):
        sys = system
        if schema is not None:
            sys = (system + "\n\nRespond with a SINGLE JSON object conforming to this "
                   "JSON schema. Output JSON only — no markdown, no prose:\n"
                   + json.dumps(schema))
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "system", "content": sys},
                         {"role": "user", "content": user}],
            "max_tokens": max_tokens or self.s.llm_max_tokens,
            "temperature": 0,  # deterministic routing / SQL / grounded generation
        }
        resp = None
        if schema is not None:
            try:  # JSON mode where supported (OpenAI, Groq, Ollama)
                resp = self.client.chat.completions.create(
                    response_format={"type": "json_object"}, **kwargs)
            except Exception:
                resp = None
        if resp is None:
            resp = self.client.chat.completions.create(**kwargs)
        text = resp.choices[0].message.content or ""
        usage = (getattr(getattr(resp, "usage", None), "prompt_tokens", None),
                 getattr(getattr(resp, "usage", None), "completion_tokens", None))
        return (extract_json(text) if schema is not None else text), usage

    # -- status ------------------------------------------------------------
    def status(self) -> ProviderStatus:
        s = self.s
        st = self._base_status()
        configured = bool(s.openai_key) or s.is_local_endpoint
        if not s.use_live_llm:
            st.connection, st.health = "disconnected", "unavailable"
            st.detail = "Offline mode — deterministic answers (no model calls)."
            if not configured:
                st.fix = "Set OPENAI_API_KEY and ABA_OFFLINE_MODE=auto for live answers."
            return st
        if configured:
            st.connection, st.health = "connected", "healthy"
            st.detail = f"API key configured for {s.provider_base_url} " \
                        f"(liveness confirmed on first answer)."
        else:
            st.connection, st.health = "disconnected", "unavailable"
            st.detail = "No OPENAI_API_KEY configured."
            st.fix = "Set OPENAI_API_KEY in your .env (or point ABA_OPENAI_BASE_URL at a local endpoint)."
        return st
