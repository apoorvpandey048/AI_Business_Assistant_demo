"""Insufficient-evidence battery (Trust & Evaluation Sprint, WS7).

A large set of unanswerable questions (weather, sports, headcount, valuation,
unknown entities — English and Hebrew) that must produce an HONEST decline:
``insufficient=True`` and an EMPTY citations list (no irrelevant evidence dressed
up as sources). Paired answerable controls guard against over-declining.

Cases marked ``live_only`` need an LLM relevance judgment the deterministic
offline path cannot make (entity-anchored questions about an absent attribute);
they are skipped offline and exercised by scripts/eval_trust.py in live mode.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CASES = [
    json.loads(line)
    for line in (ROOT / "data" / "eval" / "unanswerable.jsonl")
    .read_text("utf-8").splitlines() if line.strip()
]
DECLINES = [c for c in CASES if c["expect"] == "decline" and not c.get("live_only")]
CONTROLS = [c for c in CASES if c["expect"] == "answer"]


@pytest.mark.parametrize("case", DECLINES, ids=[c["id"] for c in DECLINES])
def test_honest_decline(sample_engine, case):
    resp = sample_engine.ask(case["question"], scope="all")
    assert resp.insufficient, (
        f"answered an unanswerable question: {resp.answer[:160]!r} "
        f"(route {resp.trace.route.route if resp.trace.route else '?'})"
    )
    assert resp.citations == [], (
        f"declined but still presented {len(resp.citations)} citation(s) as sources"
    )


@pytest.mark.parametrize("case", CONTROLS, ids=[c["id"] for c in CONTROLS])
def test_controls_still_answer(sample_engine, case):
    """The decline guardrail must not over-fire on genuinely answerable questions."""
    resp = sample_engine.ask(case["question"], scope="all")
    assert not resp.insufficient, f"over-decline: {resp.answer[:160]!r}"
    assert resp.trace.evidence, "answered without evidence"
