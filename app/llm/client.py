"""Provider-agnostic LLM client.

Supports two provider families through one interface:
- ``anthropic``  → Claude via the Anthropic SDK (structured output via output_config).
- ``openai``     → ANY OpenAI-compatible endpoint via the OpenAI SDK + base_url:
                   OpenAI, Groq (free), Gemini's compat API (free), Ollama (local/free),
                   OpenRouter, Together, …

Structured output uses each provider's JSON mode where available and a tolerant
JSON extractor otherwise, so the same call sites work across all of them.

A deterministic OFFLINE path remains: every call site supplies a ``fallback`` so the
whole pipeline keeps working (and stays grounded) with no key or network. Live
responses are cached to disk so a once-run demo replays identically.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any, Callable, Optional

from app.config import Settings, get_settings
from app.models import LLMCall

try:
    import anthropic
except Exception:  # pragma: no cover
    anthropic = None  # type: ignore

try:
    import openai
except Exception:  # pragma: no cover
    openai = None  # type: ignore


Fallback = Callable[[], Any]


def _extract_json(text: str) -> Any:
    """Tolerantly pull a JSON object out of a model response (handles code fences)."""
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


class LLMClient:
    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.s = settings or get_settings()
        self._anthropic = None
        self._openai = None
        self._cache_path = self.s.cache_dir / "llm_cache.json"
        self._cache: dict[str, Any] = self._load_cache()

    # -- provider clients (lazy) -------------------------------------------
    @property
    def anthropic_client(self):
        if self._anthropic is None and anthropic is not None and self.s.anthropic_key:
            self._anthropic = anthropic.Anthropic(api_key=self.s.anthropic_key)
        return self._anthropic

    @property
    def openai_client(self):
        if self._openai is None and openai is not None:
            self._openai = openai.OpenAI(
                api_key=self.s.openai_key or "no-key",  # local endpoints ignore it
                base_url=self.s.openai_base_url,
            )
        return self._openai

    def _live_client(self):
        return self.openai_client if self.s.llm_provider == "openai" else self.anthropic_client

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
                   fallback=None, max_tokens=None) -> tuple[dict[str, Any], LLMCall]:
        return self._run(purpose=purpose, model=model, system=system, user=user,
                         schema=schema, fallback=fallback, max_tokens=max_tokens)

    def text(self, *, purpose, model, system, user,
             fallback=None, max_tokens=None) -> tuple[str, LLMCall]:
        data, call = self._run(purpose=purpose, model=model, system=system, user=user,
                               schema=None, fallback=fallback, max_tokens=max_tokens)
        return (data if isinstance(data, str) else data.get("text", "")), call

    # -- core --------------------------------------------------------------
    def _run(self, *, purpose, model, system, user, schema, fallback, max_tokens):
        key = self._key(purpose, model, system, user)
        t0 = time.perf_counter()

        # cache-first: replay an identical prior call instantly (snappy demos).
        if self.s.cache_first and key in self._cache:
            return self._cache[key], LLMCall(
                purpose=purpose, model=model, mode="cached",
                duration_ms=round((time.perf_counter() - t0) * 1000, 1),
            )

        if self.s.use_live_llm and self._live_client() is not None:
            try:
                result, usage = self._dispatch(model, system, user, schema, max_tokens)
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

        if key in self._cache:
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

    def _dispatch(self, model, system, user, schema, max_tokens):
        if self.s.llm_provider == "openai":
            return self._call_openai(model, system, user, schema, max_tokens)
        return self._call_anthropic(model, system, user, schema, max_tokens)

    # -- anthropic ---------------------------------------------------------
    def _call_anthropic(self, model, system, user, schema, max_tokens):
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens or self.s.llm_max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        if schema is not None:
            kwargs["output_config"] = {"format": {"type": "json_schema", "schema": schema}}
        resp = self.anthropic_client.messages.create(**kwargs)
        text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
        usage = (getattr(resp.usage, "input_tokens", None),
                 getattr(resp.usage, "output_tokens", None))
        return (json.loads(text) if schema is not None else text), usage

    # -- openai-compatible (OpenAI / Groq / Gemini / Ollama / …) ------------
    def _call_openai(self, model, system, user, schema, max_tokens):
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
            try:  # JSON mode where supported (OpenAI, Groq)
                resp = self.openai_client.chat.completions.create(
                    response_format={"type": "json_object"}, **kwargs)
            except Exception:
                resp = None
        if resp is None:
            resp = self.openai_client.chat.completions.create(**kwargs)
        text = resp.choices[0].message.content or ""
        usage = (getattr(getattr(resp, "usage", None), "prompt_tokens", None),
                 getattr(getattr(resp, "usage", None), "completion_tokens", None))
        return (_extract_json(text) if schema is not None else text), usage


_client: Optional[LLMClient] = None


def get_llm() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient()
    return _client
