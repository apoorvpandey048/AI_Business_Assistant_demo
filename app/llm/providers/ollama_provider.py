"""OllamaProvider — a local Ollama server over the OpenAI-compatible transport.

Generation/routing/SQL calls reuse the OpenAI-compatible code path (Ollama exposes
`/v1/chat/completions`), so there is no second HTTP client and no new behavior in the
call sites. What this provider adds on top of `OpenAIProvider`:

  • an explicit request timeout (local CPU inference can be slow but must not hang forever);
  • a real health probe against the Ollama REST API (`/api/tags`) that reports whether the
    server is reachable and whether the configured model is pulled — with the exact fix
    command for each failure;
  • never crashes the engine: connection-refused / timeout / missing-model surface as clean
    exceptions, which the LLMClient already degrades through the deterministic offline ladder.
"""
from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from typing import Optional

from app.llm.providers.openai_provider import OpenAIProvider
from app.models import ProviderStatus


def _model_present(want: str, models: list[str]) -> bool:
    """Whether the configured model id matches a pulled Ollama model name.

    Tolerant of the optional ':latest'/tag suffix Ollama may report."""
    want = (want or "").strip()
    if not want:
        return False
    for m in models:
        m = (m or "").strip()
        if m == want or m.startswith(want + ":") or m.split(":latest")[0] == want:
            return True
    return False


class OllamaProvider(OpenAIProvider):
    name = "ollama"
    transport = "openai-compatible"

    def _timeout(self) -> Optional[float]:
        # local inference can be slow (CPU), but a hung server must not block forever
        return float(self.s.ollama_timeout)

    def available(self) -> bool:
        # the OpenAI SDK must be importable; no key is required for a local server
        return self.client is not None

    # -- health probe ------------------------------------------------------
    def _probe(self) -> tuple[bool, list[str], str]:
        """GET <ollama_url>/api/tags. Returns (reachable, model_names, error)."""
        tags_url = self.s.ollama_url.rstrip("/") + "/api/tags"
        try:
            req = urllib.request.Request(tags_url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=2.5) as r:
                data = json.loads(r.read().decode("utf-8") or "{}")
            names = [m.get("name", "") for m in data.get("models", []) if isinstance(m, dict)]
            return True, names, ""
        except (urllib.error.URLError, socket.timeout, ConnectionError, OSError, ValueError) as exc:
            return False, [], str(exc)

    def status(self) -> ProviderStatus:
        s = self.s
        st = self._base_status()
        st.provider = "ollama"
        # In forced-offline mode we don't touch the network; report deterministic mode.
        if s.offline_mode == "always":
            st.connection, st.health = "disconnected", "unavailable"
            st.detail = "Offline mode — deterministic answers (no model calls)."
            return st

        reachable, models, _err = self._probe()
        if not reachable:
            st.connection, st.health = "disconnected", "unavailable"
            st.detail = f"Ollama server is not reachable at {s.ollama_url}."
            st.fix = ("Start it:  ollama serve     "
                      "(not installed?  curl -fsSL https://ollama.com/install.sh | sh)")
            return st

        st.connection = "connected"
        want = s.model_generation
        if _model_present(want, models):
            st.health = "healthy"
            st.detail = f"Ollama is running and model {want} is available."
        else:
            st.health = "degraded"
            have = ", ".join(models) if models else "none"
            st.detail = (f"Ollama is running but model {want} is not pulled "
                         f"(installed: {have}).")
            st.fix = f"ollama pull {want}"
        return st
