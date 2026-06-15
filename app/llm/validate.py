"""Provider validation (sprint §14, Workstream 5).

After a switch — and on demand from Settings — we validate the *active* provider end to end
so the user never has to discover a broken provider by asking a question and silently getting
offline answers. Four independent checks, each returning pass / fail / skipped + an exact fix:

  • health      — the provider's own status probe (reachable / key present / model pulled)
  • routing     — a real ``structured()`` JSON call (does structured output actually work?)
  • generation  — a real ``text()`` call (does the model produce a reply?)
  • embeddings  — the active embedder produces a usable vector (always works offline via hashing)

Design rules:
  • NEVER raises — every failure becomes a clean `fail` check; no stack trace ever escapes.
  • NEVER pollutes the replay cache — the live probes call the provider directly (bypassing
    the LLMClient cache) so a validation run cannot become a future offline "answer".
  • Offline / no-key → the live probes are `skipped` ("deterministic fallbacks"), not `fail`.
"""
from __future__ import annotations

import re
import time
from typing import Callable

from app.config import Settings, get_settings
from app.llm.client import get_llm
from app.models import ProviderCheck, ProviderStatus, ProviderValidation

# Minimal schema for the routing probe — just enough to exercise structured/JSON output.
_ROUTE_SCHEMA = {
    "type": "object",
    "properties": {"route": {"type": "string"}},
    "required": ["route"],
}


def _ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 1)


def _clean_error(msg: str) -> str:
    """One readable line — no tracebacks, no file paths, capped length."""
    line = re.sub(r"\s+", " ", (msg or "").strip()).strip()
    line = re.sub(r"(/[^\s]+/)+[^\s]+\.py[^\s]*", "<internal>", line)  # scrub any path that slipped in
    return (line[:220] + "…") if len(line) > 221 else (line or "The provider call failed.")


def _fix_for(s: Settings) -> str | None:
    p = s.resolved_provider
    if p == "ollama":
        return (f"Confirm Ollama is running (ollama serve) and the model is pulled "
                f"(ollama pull {s.model_generation}).")
    if p == "anthropic":
        return "Verify ANTHROPIC_API_KEY is set and valid."
    return "Verify OPENAI_API_KEY (and ABA_OPENAI_BASE_URL) are set and valid."


# -- individual checks -------------------------------------------------------

def _check_health(status: ProviderStatus) -> ProviderCheck:
    t0 = time.perf_counter()
    if status.offline:
        return ProviderCheck(name="health", status="skipped",
                             detail="Offline mode — deterministic fallbacks (no model calls).",
                             duration_ms=_ms(t0))
    if status.health == "healthy":
        return ProviderCheck(name="health", status="pass",
                             detail=status.detail or "Provider is healthy.", duration_ms=_ms(t0))
    return ProviderCheck(name="health", status="fail",
                         detail=status.detail or "Provider is unavailable.",
                         fix=status.fix, duration_ms=_ms(t0))


def _live_probe(name: str, run: Callable[..., str]) -> ProviderCheck:
    """Run a real provider call (bypassing the cache). Skipped when offline/unconfigured."""
    s = get_settings()
    llm = get_llm()
    t0 = time.perf_counter()
    if not (s.use_live_llm and llm.provider.available()):
        return ProviderCheck(name=name, status="skipped",
                             detail="No live provider configured — running on deterministic "
                                    "offline fallbacks.", duration_ms=_ms(t0))
    try:
        detail = run(llm, s)
        return ProviderCheck(name=name, status="pass", detail=detail, duration_ms=_ms(t0))
    except Exception as exc:  # the probe's whole purpose is to catch this cleanly
        return ProviderCheck(name=name, status="fail", detail=_clean_error(str(exc)),
                             fix=_fix_for(s), duration_ms=_ms(t0))


def _routing(llm, s: Settings) -> str:
    out, _usage = llm.provider.generate(
        model=s.model_router,
        system="You are a query router. Reply with a single JSON object.",
        user='Pick a route for this question. Question: "How many invoices are overdue?"',
        schema=_ROUTE_SCHEMA, max_tokens=50,
    )
    if not isinstance(out, dict):
        raise ValueError("structured output did not return a JSON object")
    return f"Structured JSON works via {s.model_router} (route={out.get('route', '?')})."


def _generation(llm, s: Settings) -> str:
    out, _usage = llm.provider.generate(
        model=s.model_generation,
        system="You are a health check. Reply with exactly the two letters: OK",
        user="Reply OK.", schema=None, max_tokens=10,
    )
    txt = (out if isinstance(out, str) else str(out)).strip()
    if not txt:
        raise ValueError("the model returned an empty reply")
    return f"Generation works via {s.model_generation} (replied {len(txt)} char(s))."


def _check_embeddings() -> ProviderCheck:
    t0 = time.perf_counter()
    try:
        import numpy as np

        from app.llm.embeddings import EmbeddingModel
        em = EmbeddingModel.get()
        v = em.embed(["provider validation probe"])
        ok_shape = getattr(v, "shape", (0, 0))
        if v is None or ok_shape[0] < 1 or ok_shape[1] < 2 or not bool(np.isfinite(v).all()):
            return ProviderCheck(name="embeddings", status="fail",
                                 detail="The embedding backend did not return a usable vector.",
                                 fix="Check ABA_EMBEDDING_BACKEND — the deterministic hashing "
                                     "backend always works offline.", duration_ms=_ms(t0))
        degraded = bool(getattr(em, "_last_degraded", False))
        note = " (degraded to hashing for this probe — retrieval falls back to BM25)" if degraded else ""
        return ProviderCheck(name="embeddings", status="pass",
                             detail=f"Active backend: {em.backend}; produced {ok_shape[1]}-dim "
                                    f"vectors{note}.", duration_ms=_ms(t0))
    except Exception as exc:
        return ProviderCheck(name="embeddings", status="fail", detail=_clean_error(str(exc)),
                             fix="Check ABA_EMBEDDING_BACKEND; the hashing embedder needs no setup.",
                             duration_ms=_ms(t0))


# -- public entry point ------------------------------------------------------

def validate_provider() -> ProviderValidation:
    """Validate the active provider end to end. Never raises."""
    s = get_settings()
    status = get_llm().provider_status()
    checks = [
        _check_health(status),
        _live_probe("routing", _routing),
        _live_probe("generation", _generation),
        _check_embeddings(),
    ]
    failed = [c for c in checks if c.status == "fail"]
    live = [c for c in checks if c.status == "pass" and c.name in ("routing", "generation")]
    ok = not failed

    if failed:
        summary = (f"{len(failed)} check(s) failed — see the remediation below. The engine "
                   f"keeps answering with deterministic fallbacks until this is fixed.")
    elif not live:
        summary = ("Provider configured. Running on deterministic offline fallbacks — set a key "
                   "(or start Ollama) for live model answers.")
    else:
        summary = f"All checks passed — {s.resolved_provider} is ready for live answers."

    return ProviderValidation(provider=s.resolved_provider, ok=ok, summary=summary, checks=checks)
