"""Multi-aspect completeness battery (Trust & Evaluation Sprint, WS5).

The known client-discovered failure mode: a compound question ("what penalties AND
suspension clauses exist?") answered for only ONE aspect. Every case in
data/eval/multi_aspect.jsonl lists its aspects as synonym groups; an aspect counts
as covered when any synonym appears in the retrieved evidence or the answer.

The gate is FULL completeness per case — a partial answer is a failure, which is
the entire point of the battery.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CASES = [
    json.loads(line)
    for line in (ROOT / "data" / "eval" / "multi_aspect.jsonl")
    .read_text("utf-8").splitlines() if line.strip()
]


def _coverage(resp, aspects: list[list[str]]) -> tuple[float, list[int]]:
    # section titles are part of the evidence a user sees (citations carry them),
    # so they count toward aspect coverage ("5. Mitigations" covers "mitigat")
    blob = (" ".join(f"{e.content} {e.section or ''}" for e in resp.trace.evidence)
            + " " + (resp.answer or "")).lower()
    missed = [i for i, syns in enumerate(aspects)
              if not any(s.lower() in blob for s in syns)]
    return 1 - len(missed) / len(aspects), missed


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_all_aspects_covered(sample_engine, case):
    resp = sample_engine.ask(case["question"], scope="all")
    assert not resp.insufficient, f"declined a compound question: {resp.answer[:120]}"
    cov, missed = _coverage(resp, case["aspects"])
    assert cov == 1.0, (
        f"partial answer — missed aspect group(s) {missed} "
        f"({[case['aspects'][i] for i in missed]}); coverage {cov:.0%}"
    )
