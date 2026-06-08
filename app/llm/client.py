"""Provider-agnostic LLM client (default: Anthropic Claude).

Design goals:
- One narrow interface (`structured`, `text`) the rest of the engine depends on, so
  swapping providers is a single-file change.
- Structured output via Claude's `output_config.format` (JSON schema) — no brittle
  parsing of free-form text.
- A deterministic OFFLINE path: every call site supplies a `fallback` so the whole
  pipeline keeps working (and stays grounded) with no API key or network. Live
  responses are also cached to disk so a once-run demo replays identically.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Callable, Optional

from app.config import Settings, get_settings
from app.models import LLMCall

try:  # the SDK is a hard dep, but guard so import never crashes the app
    import anthropic
except Exception:  # pragma: no cover
    anthropic = None  # type: ignore


Fallback = Callable[[], Any]


class LLMClient:
    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.s = settings or get_settings()
        self._client = None
        self._cache_path = self.s.cache_dir / "llm_cache.json"
        self._cache: dict[str, Any] = self._load_cache()

    # -- anthropic client (lazy) -------------------------------------------
    @property
    def client(self):
        if self._client is None and anthropic is not None and self.s.has_api_key:
            self._client = anthropic.Anthropic(
                api_key=self.s.anthropic_api_key or None
            )
        return self._client

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
    def structured(
        self,
        *,
        purpose: str,
        model: str,
        system: str,
        user: str,
        schema: dict[str, Any],
        fallback: Optional[Fallback] = None,
        max_tokens: Optional[int] = None,
    ) -> tuple[dict[str, Any], LLMCall]:
        return self._run(
            purpose=purpose, model=model, system=system, user=user,
            schema=schema, fallback=fallback, max_tokens=max_tokens,
        )

    def text(
        self,
        *,
        purpose: str,
        model: str,
        system: str,
        user: str,
        fallback: Optional[Fallback] = None,
        max_tokens: Optional[int] = None,
    ) -> tuple[str, LLMCall]:
        data, call = self._run(
            purpose=purpose, model=model, system=system, user=user,
            schema=None, fallback=fallback, max_tokens=max_tokens,
        )
        return (data if isinstance(data, str) else data.get("text", "")), call

    # -- core --------------------------------------------------------------
    def _run(
        self,
        *,
        purpose: str,
        model: str,
        system: str,
        user: str,
        schema: Optional[dict[str, Any]],
        fallback: Optional[Fallback],
        max_tokens: Optional[int],
    ) -> tuple[Any, LLMCall]:
        key = self._key(purpose, model, system, user)
        t0 = time.perf_counter()

        # 1) live call
        if self.s.use_live_llm and self.client is not None:
            try:
                result, usage = self._call_anthropic(model, system, user, schema, max_tokens)
                self._cache[key] = result
                self._save_cache()
                from app.pricing import call_cost
                return result, LLMCall(
                    purpose=purpose, model=model, mode="live",
                    input_tokens=usage[0], output_tokens=usage[1],
                    cost_usd=call_cost(model, usage[0], usage[1]),
                    duration_ms=round((time.perf_counter() - t0) * 1000, 1),
                )
            except Exception as exc:  # fall through to cache / fallback
                self._last_error = str(exc)

        # 2) cached (a prior live run)
        if key in self._cache:
            return self._cache[key], LLMCall(
                purpose=purpose, model=model, mode="cached",
                duration_ms=round((time.perf_counter() - t0) * 1000, 1),
            )

        # 3) deterministic fallback (keeps the pipeline running offline)
        if fallback is not None:
            return fallback(), LLMCall(
                purpose=purpose, model=model, mode="stub",
                duration_ms=round((time.perf_counter() - t0) * 1000, 1),
            )

        raise RuntimeError(
            f"No live LLM, no cache, and no fallback for purpose={purpose!r}. "
            "Set ANTHROPIC_API_KEY for live answers."
        )

    def _call_anthropic(
        self,
        model: str,
        system: str,
        user: str,
        schema: Optional[dict[str, Any]],
        max_tokens: Optional[int],
    ) -> tuple[Any, tuple[Optional[int], Optional[int]]]:
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens or self.s.llm_max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        if schema is not None:
            kwargs["output_config"] = {
                "format": {"type": "json_schema", "schema": schema}
            }
        resp = self.client.messages.create(**kwargs)
        text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
        usage = (
            getattr(resp.usage, "input_tokens", None),
            getattr(resp.usage, "output_tokens", None),
        )
        if schema is not None:
            return json.loads(text), usage
        return text, usage


_client: Optional[LLMClient] = None


def get_llm() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient()
    return _client
