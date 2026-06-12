"""Document-QA evaluation harness — measures retrieval & answer quality over a
labelled question set, and attributes every failure to a pipeline layer.

Metrics:
- Recall@k          expected document appears in the selected evidence
- Evidence coverage expected text appears in the retrieved evidence
- Answer coverage   expected text appears in evidence or answer (offline answers
                    are extractive, so evidence containment is the stable signal)
- Honesty           expect_insufficient cases actually decline
- Precision (lookup) keyword lookups return ONLY the expected document

Eval set: data/eval/qa.jsonl — one JSON object per line:
    id, lang, question, expect_doc?, expect_in_evidence?, expect_insufficient?,
    expect_only_doc? (lookup precision), expect_source_kind?

Runs against the SAMPLE corpus (scope=all) and is deterministic offline.
Exit code 1 if any case fails — wire into CI as a regression gate.

Usage:
    .venv/bin/python scripts/eval_qa.py            # summary table
    .venv/bin/python scripts/eval_qa.py --verbose  # + failure-layer detail
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("ABA_REFERENCE_DATE", "2026-06-08")  # seed-data anchor

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

EVAL_SET = ROOT / "data" / "eval" / "qa.jsonl"


def _load_cases() -> list[dict]:
    cases = []
    for line in EVAL_SET.read_text("utf-8").splitlines():
        line = line.strip()
        if line:
            cases.append(json.loads(line))
    return cases


def _layer(resp, case) -> str:
    """Attribute a failing case to the pipeline layer that lost the answer."""
    t = resp.trace
    ev_docs = {e.document for e in t.evidence if e.document}
    cand_docs = ({c.document for c in t.document_retrieval.candidates}
                 if t.document_retrieval else set())
    doc = case.get("expect_doc")
    if doc and doc not in ev_docs:
        if doc in cand_docs:
            return "ranking"
        if t.route and t.route.route in ("NONE", "SQL") and not t.safety_net:
            return "routing"
        return "retrieval"
    return "generation"


def run_case(eng, case) -> tuple[bool, list[str], str]:
    resp = eng.ask(case["question"], scope="all")
    t = resp.trace
    problems: list[str] = []

    ev_docs = {e.document for e in t.evidence if e.document}
    ev_text = " ".join(e.content for e in t.evidence)
    blob = (ev_text + " " + (resp.answer or "")).lower()

    if case.get("expect_insufficient"):
        if not resp.insufficient:
            problems.append("expected insufficient, got an answer")
    else:
        if resp.insufficient:
            problems.append("false negative: declined as insufficient")
        if not t.evidence:
            problems.append("no evidence retrieved")

    doc = case.get("expect_doc")
    if doc and doc not in ev_docs:
        problems.append(f"recall: {doc} not in evidence (got {sorted(ev_docs) or '∅'})")
    if case.get("expect_only_doc") and doc and ev_docs and ev_docs != {doc}:
        problems.append(f"precision: extra documents in evidence {sorted(ev_docs - {doc})}")

    text = case.get("expect_in_evidence")
    if text and text.lower() not in blob:
        problems.append(f"coverage: {text!r} not found in evidence/answer")

    kind = case.get("expect_source_kind")
    if kind and not any(e.source_kind == kind for e in t.evidence):
        problems.append(f"expected {kind} evidence")

    layer = _layer(resp, case) if problems else "ok"
    return (not problems), problems, layer


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    from app.engine import get_engine
    eng = get_engine()
    cases = _load_cases()

    print(f"\nEval set: {len(cases)} case(s) | "
          f"mode: {'live' if eng.settings.use_live_llm else 'offline'} | "
          f"embeddings: {eng.document_source.index.embedder.backend}\n")
    print(f"{'ok':>3} {'layer':<11} {'lang':<4} {'id':<26} question")
    print("-" * 100)

    n_pass = 0
    recall_hit = recall_total = 0
    cover_hit = cover_total = 0
    by_layer: dict[str, int] = {}
    for case in cases:
        ok, problems, layer = run_case(eng, case)
        n_pass += ok
        if case.get("expect_doc"):
            recall_total += 1
            recall_hit += not any(p.startswith("recall") for p in problems)
        if case.get("expect_in_evidence"):
            cover_total += 1
            cover_hit += not any(p.startswith("coverage") for p in problems)
        if not ok:
            by_layer[layer] = by_layer.get(layer, 0) + 1
        flag = "✓" if ok else "✗"
        print(f"{flag:>3} {layer:<11} {case.get('lang','?'):<4} {case['id']:<26} "
              f"{case['question'][:46]}")
        if args.verbose and problems:
            for p in problems:
                print(f"      · {p}")

    print("-" * 100)
    print(f"passed:            {n_pass}/{len(cases)}")
    if recall_total:
        print(f"Recall@k:          {recall_hit}/{recall_total} "
              f"({100 * recall_hit / recall_total:.0f}%)")
    if cover_total:
        print(f"Evidence coverage: {cover_hit}/{cover_total} "
              f"({100 * cover_hit / cover_total:.0f}%)")
    if by_layer:
        print(f"failures by layer: " +
              ", ".join(f"{k}={v}" for k, v in sorted(by_layer.items())))
    print()
    return 0 if n_pass == len(cases) else 1


if __name__ == "__main__":
    sys.exit(main())
