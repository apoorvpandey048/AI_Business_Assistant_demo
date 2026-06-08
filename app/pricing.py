"""Token pricing → per-answer cost transparency for the inspector panel.

Prices are USD per 1M tokens (input, output). Embeddings run on a local model, so
they cost $0. Offline answers (deterministic fallback / cache) also cost $0.
"""
from __future__ import annotations

from app.models import CostSummary, LLMCall

# USD per 1,000,000 tokens (input, output)
PRICES: dict[str, tuple[float, float]] = {
    "claude-opus-4-8": (5.0, 25.0),
    "claude-opus-4-7": (5.0, 25.0),
    "claude-opus-4-6": (5.0, 25.0),
    "claude-opus-4-5": (5.0, 25.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-sonnet-4-5": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}


def call_cost(model: str, input_tokens: int | None, output_tokens: int | None) -> float | None:
    if input_tokens is None and output_tokens is None:
        return None
    if model not in PRICES:  # unknown / non-Anthropic (e.g. a free provider) — don't guess
        return None
    pin, pout = PRICES[model]
    return round((input_tokens or 0) * pin / 1e6 + (output_tokens or 0) * pout / 1e6, 6)


def summarize(calls: list[LLMCall]) -> CostSummary:
    in_tok = sum(c.input_tokens or 0 for c in calls)
    out_tok = sum(c.output_tokens or 0 for c in calls)
    live = [c for c in calls if c.mode == "live"]
    total = round(sum(c.cost_usd or 0.0 for c in calls), 6)
    priced = [c for c in live if c.cost_usd is not None]
    if not live:
        note = "Offline (deterministic / cached) — $0.00. Embeddings are local (no API cost)."
    elif not priced:
        note = (f"{len(live)} live call(s) via a non-Anthropic provider — token pricing not "
                f"tracked here. Embeddings local (no API cost).")
    else:
        note = (f"{len(live)} live call(s); embeddings local (no API cost). "
                f"≈ ${total:.4f} for this answer.")
    return CostSummary(input_tokens=in_tok, output_tokens=out_tok,
                       total_usd=total, live_calls=len(live), note=note)
