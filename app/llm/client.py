"""Provider-agnostic LLM client.

The client owns everything that is the SAME across providers — the response cache, the
deterministic OFFLINE fallback ladder, and `LLMCall` accounting — and delegates the
actual model call to a provider strategy (`app/llm/providers/`):
- ``anthropic`` → Claude via the Anthropic SDK.
- ``openai``    → any OpenAI-compatible hosted endpoint (OpenAI, Groq, Gemini compat…).
- ``ollama``    → a local Ollama server over the OpenAI-compatible transport.

Every call site supplies a ``fallback`` so the whole pipeline keeps working (and stays
grounded) with no key, no network, or a provider error — a down Ollama looks like offline
mode, never a crash. Live responses are cached to disk so a prior question replays identically.
"""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Callable, Optional

from app.config import Settings, get_settings
from app.llm.providers import LLMProvider, make_provider
from app.models import LLMCall, ProviderStatus


Fallback = Callable[[], Any]


class LLMClient:
    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.s = settings or get_settings()
        self.provider: LLMProvider = make_provider(self.s)
        self._cache_path = self.s.cache_dir / "llm_cache.json"
        self._cache: dict[str, Any] = self._load_cache()

    def provider_status(self) -> ProviderStatus:
        """Read-only diagnostics for the configured provider (never raises)."""
        try:
            return self.provider.status()
        except Exception as exc:  # status must never break the page
            return ProviderStatus(
                provider=self.s.resolved_provider, transport=self.provider.transport,
                connection="unknown", health="unavailable",
                detail=f"Could not determine provider status: {exc}",
            )

    # -- cache -------------------------------------------------------------
    def _load_cache(self) -> dict[str, Any]:
        try:
            return json.loads(self._cache_path.read_text("utf-8"))
        except Exception:
            return {}

    def _save_cache(self) -> None:
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            self._cache_path.write_text(
                json.dumps(self._cache, ensure_ascii=False, indent=2), "utf-8"
            )
        except Exception:
            pass

    @staticmethod
    def _key(purpose: str, model: str, system: str, user: str) -> str:
        h = hashlib.sha256()
        h.update(f"{purpose}\x00{model}\x00{system}\x00{user}".encode("utf-8"))
        return h.hexdigest()

    # -- public API --------------------------------------------------------
    def structured(self, *, purpose, model, system, user, schema,
                   fallback=None, max_tokens=None, accept=None) -> tuple[dict[str, Any], LLMCall]:
        return self._run(purpose=purpose, model=model, system=system, user=user,
                         schema=schema, fallback=fallback, max_tokens=max_tokens,
                         accept=accept)

    def text(self, *, purpose, model, system, user,
             fallback=None, max_tokens=None) -> tuple[str, LLMCall]:
        data, call = self._run(purpose=purpose, model=model, system=system, user=user,
                               schema=None, fallback=fallback, max_tokens=max_tokens)
        return (data if isinstance(data, str) else data.get("text", "")), call

    # -- core --------------------------------------------------------------
    def _run(self, *, purpose, model, system, user, schema, fallback, max_tokens, accept=None):
        key = self._key(purpose, model, system, user)
        t0 = time.perf_counter()

        def _ok(result: Any) -> bool:
            # An optional quality gate (e.g. answer-language integrity). A result that
            # fails it is treated as if it never happened: never cached, never replayed,
            # so the call falls through to a fresh attempt or the deterministic fallback.
            if accept is None:
                return True
            try:
                return bool(accept(result))
            except Exception:
                return True            # a buggy acceptor must never break answering

        # cache-first: replay an identical prior call instantly (snappy demos) — but only
        # if the cached result still passes the quality gate (a previously-cached defective
        # answer self-heals instead of replaying forever).
        if self.s.cache_first and key in self._cache and _ok(self._cache[key]):
            return self._cache[key], LLMCall(
                purpose=purpose, model=model, mode="cached",
                duration_ms=round((time.perf_counter() - t0) * 1000, 1),
            )

        if self.s.use_live_llm and self.provider.available():
            try:
                result, usage = self.provider.generate(
                    model=model, system=system, user=user,
                    schema=schema, max_tokens=max_tokens)
                if not _ok(result):
                    raise ValueError("generation rejected by quality gate")
                if self.s.llm_cache_write:
                    self._cache[key] = result
                    self._save_cache()
                from app.pricing import call_cost
                return result, LLMCall(
                    purpose=purpose, model=model, mode="live",
                    input_tokens=usage[0], output_tokens=usage[1],
                    cost_usd=call_cost(model, usage[0], usage[1]),
                    duration_ms=round((time.perf_counter() - t0) * 1000, 1),
                )
            except Exception as exc:
                self._last_error = str(exc)

        if key in self._cache and _ok(self._cache[key]):
            return self._cache[key], LLMCall(
                purpose=purpose, model=model, mode="cached",
                duration_ms=round((time.perf_counter() - t0) * 1000, 1),
            )

        if fallback is not None:
            return fallback(), LLMCall(
                purpose=purpose, model=model, mode="stub",
                duration_ms=round((time.perf_counter() - t0) * 1000, 1),
            )

        raise RuntimeError(
            f"No live LLM, no cache, and no fallback for purpose={purpose!r}."
        )


_client: Optional[LLMClient] = None


def get_llm() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient()
    return _client


def reset_llm() -> None:
    """Drop the client singleton so the next get_llm() rebuilds with the current settings.

    Used after a runtime provider switch (sprint §14): the new client picks up the freshly
    resolved provider + models. The engine, the index, and the embedder are NOT touched —
    they are provider-independent — so the workspace is preserved across a switch."""
    global _client
    _client = None
