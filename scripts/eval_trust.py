"""Trust Score evaluation harness (Trust & Evaluation Sprint, WS4/WS5/WS7/WS9).

Runs every evaluation battery and aggregates a single TRUST SCORE with seven
components, each traceable to raw per-case results:

  routing        route matches the golden route (scripts/eval.py question set)
  retrieval      Recall@k — the expected document appears in the evidence (qa.jsonl)
  evidence       evidence coverage — the expected text was retrieved (qa.jsonl)
  answers        aspect completeness over compound questions (multi_aspect.jsonl)
  conflicts      contradiction handling — detect, report both sides, never resolve
                 silently, zero false positives on clean data (contradiction fixtures)
  grounding      honesty — unanswerable questions decline with no citations, paired
                 answerable controls still answer (unanswerable.jsonl)
  citations      citation verification passes on answered questions

Batteries are data-driven (data/eval/*.jsonl + data/eval/contradictions/). The
report is written to docs/trust-report.md. Deterministic offline; with an API key
it exercises the live model stack instead (the report records the mode).

Usage:
    .venv/bin/python scripts/eval_trust.py            # run + write report
    .venv/bin/python scripts/eval_trust.py --verbose  # + per-case detail on stdout
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("ABA_REFERENCE_DATE", "2026-06-08")  # seed-data anchor
# An evaluation run must never mutate product state: live answers recorded here
# would otherwise become the offline replay behavior afterwards (cache poisoning —
# found when a failing live answer started replaying in the offline gates).
os.environ.setdefault("ABA_LLM_CACHE_WRITE", "false")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

EVAL_DIR = ROOT / "data" / "eval"
FIXTURES = EVAL_DIR / "contradictions"
REPORT = ROOT / "docs" / "trust-report.md"

WEIGHTS = {
    "routing": 0.15, "retrieval": 0.15, "evidence": 0.15, "answers": 0.15,
    "conflicts": 0.15, "grounding": 0.15, "citations": 0.10,
}


def _load(name: str) -> list[dict]:
    cases = []
    for line in (EVAL_DIR / name).read_text("utf-8").splitlines():
        line = line.strip()
        if line:
            cases.append(json.loads(line))
    return cases


# -- battery A: routing + citations (golden routes) ---------------------------

def run_routing(eng) -> tuple[float, float, list[str]]:
    from scripts.eval import QUESTIONS
    rows, ok, cite_ok, cite_n = [], 0, 0, 0
    for ex in QUESTIONS:
        resp = eng.ask(ex.question, scope="all")
        route = resp.trace.route.route if resp.trace.route else "?"
        hit = route == ex.route
        ok += hit
        if ex.route != "NONE" and not resp.insufficient:
            cite_n += 1
            cite_ok += bool(resp.trace.citation_check and resp.trace.citation_check.verified)
        rows.append(f"| {ex.label} | {ex.route} | {route} | {'✓' if hit else '✗'} |")
    return ok / len(QUESTIONS), (cite_ok / cite_n if cite_n else 1.0), rows


# -- battery B: retrieval + evidence coverage (qa.jsonl) -----------------------

def run_qa(eng) -> tuple[float, float, list[str]]:
    from scripts.eval_qa import run_case
    cases = _load("qa.jsonl")
    recall_hit = recall_n = cover_hit = cover_n = 0
    rows = []
    for case in cases:
        ok, problems, layer = run_case(eng, case)
        if case.get("expect_doc"):
            recall_n += 1
            recall_hit += not any(p.startswith("recall") for p in problems)
        if case.get("expect_in_evidence"):
            cover_n += 1
            cover_hit += not any(p.startswith("coverage") for p in problems)
        rows.append(f"| {case['id']} | {'✓' if ok else '✗ ' + layer} |")
    return (recall_hit / recall_n if recall_n else 1.0,
            cover_hit / cover_n if cover_n else 1.0, rows)


# -- battery C: multi-aspect completeness --------------------------------------

def aspect_coverage(resp, aspects: list[list[str]]) -> float:
    """Fraction of aspects with at least one synonym present in evidence (text or
    section title — both are shown to the user) or the answer."""
    blob = (" ".join(f"{e.content} {e.section or ''}" for e in resp.trace.evidence)
            + " " + (resp.answer or "")).lower()
    hit = sum(1 for syns in aspects if any(s.lower() in blob for s in syns))
    return hit / len(aspects) if aspects else 1.0


def run_multi_aspect(eng) -> tuple[float, list[str]]:
    cases = _load("multi_aspect.jsonl")
    scores, rows = [], []
    for case in cases:
        resp = eng.ask(case["question"], scope="all")
        cov = aspect_coverage(resp, case["aspects"])
        scores.append(cov)
        flag = "✓" if cov == 1.0 else f"PARTIAL {cov:.0%}"
        rows.append(f"| {case['id']} | {len(case['aspects'])} | {flag} |")
    return sum(scores) / len(scores), rows


# -- battery D: honesty (unanswerable + controls) -------------------------------

def run_unanswerable(eng) -> tuple[float, list[str], int]:
    cases = _load("unanswerable.jsonl")
    live = eng.settings.use_live_llm
    n = ok = skipped = 0
    rows = []
    for case in cases:
        if case.get("live_only") and not live:
            skipped += 1
            rows.append(f"| {case['id']} | {case['expect']} | skipped (live-only) |")
            continue
        resp = eng.ask(case["question"], scope="all")
        n += 1
        if case["expect"] == "decline":
            hit = resp.insufficient and not resp.citations
            why = "" if hit else (" — answered" if not resp.insufficient
                                  else " — declined but cited evidence")
        else:  # control: must still answer
            hit = (not resp.insufficient) and bool(resp.trace.evidence)
            why = "" if hit else " — over-decline"
        ok += hit
        rows.append(f"| {case['id']} | {case['expect']} | {'✓' if hit else '✗' + why} |")
    return (ok / n if n else 1.0), rows, skipped


# -- battery E: contradiction handling -----------------------------------------

CONTRA_PROBES = [
    ("paid vs overdue", "Has invoice INV-1187 been paid?", "payment_status",
     ["paid", "overdue|unpaid"]),
    ("expiry date", "When does contract ACM-MSA-2025 expire?", "end_date",
     ["2026-08-20", "2027-08-20"]),
    ("invoice amount", "How much is invoice INV-1201?", "amount",
     ["18,000|18000", "19,500|19500"]),
]


def run_contradictions() -> tuple[float, list[str]]:
    """Fresh engine + the contradicting amendment: every seeded conflict must be
    detected AND reported with both values; the clean engine must stay silent."""
    from app.config import get_settings
    from app.engine import Engine

    rows = []
    if not (FIXTURES / "CONTRA_Amendment_2026.pdf").exists():
        return 0.0, ["| fixtures missing — run scripts/make_contradiction_fixtures.py | ✗ |"]
    get_settings.cache_clear()
    eng = Engine()

    # clean-corpus gate first (same engine, before the amendment lands)
    clean_ok = True
    for q in ("Which customers have overdue invoices, and what do their agreements "
              "say about service suspension?",
              "What is the total outstanding invoice amount per customer?"):
        if eng.ask(q, scope="all").trace.conflicts:
            clean_ok = False
    rows.append(f"| zero false positives on clean corpus | {'✓' if clean_ok else '✗'} |")

    info = eng.add_pdf("CONTRA_Amendment_2026.pdf", FIXTURES / "CONTRA_Amendment_2026.pdf")
    if info.status != "indexed":
        return 0.0, rows + [f"| amendment ingestion failed: {info.error} | ✗ |"]

    import re as _re
    hits = [clean_ok]
    for label, q, attr, must_have in CONTRA_PROBES:
        resp = eng.ask(q, scope="all")
        detected = any(c.attribute == attr for c in resp.trace.conflicts)
        a = resp.answer.lower()
        reported = all(_re.search(alt.lower(), a.replace(",", "")) for alt in must_have)
        explicit = any(w in a for w in ("conflict", "disagree", "סתירה"))
        ok = detected and reported and explicit
        hits.append(ok)
        rows.append(f"| {label}: detected={'✓' if detected else '✗'} "
                    f"both-values={'✓' if reported else '✗'} "
                    f"explicit={'✓' if explicit else '✗'} | {'✓' if ok else '✗'} |")
    return sum(hits) / len(hits), rows


# -- report ---------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--offline", action="store_true",
                    help="force the hermetic deterministic stack (rule router, "
                         "hashing embeddings, extractive generation) — same as the "
                         "test suite; no API key or network needed")
    args = ap.parse_args()
    if args.offline:
        os.environ.update({
            "ABA_OFFLINE_MODE": "always", "ABA_EMBEDDING_BACKEND": "hashing",
            "ABA_ENABLE_RERANK": "false", "ABA_CACHE_FIRST": "false",
        })

    from app.engine import get_engine
    eng = get_engine()
    mode = "live" if eng.settings.use_live_llm else "offline (deterministic)"

    print(f"\nTrust evaluation | mode: {mode} | "
          f"embeddings: {eng.document_source.index.embedder.backend}\n")

    routing, citations_a, routing_rows = run_routing(eng)
    recall, evidence, qa_rows = run_qa(eng)
    answers, ma_rows = run_multi_aspect(eng)
    grounding, un_rows, skipped = run_unanswerable(eng)
    conflicts, contra_rows = run_contradictions()

    components = {
        "routing": routing, "retrieval": recall, "evidence": evidence,
        "answers": answers, "conflicts": conflicts, "grounding": grounding,
        "citations": citations_a,
    }
    trust = sum(WEIGHTS[k] * v for k, v in components.items()) * 100

    print(f"{'component':<12} {'weight':>7} {'score':>7}")
    print("-" * 30)
    for k, v in components.items():
        print(f"{k:<12} {WEIGHTS[k]:>6.0%} {v:>6.1%}")
    print("-" * 30)
    print(f"TRUST SCORE: {trust:.1f} / 100\n")

    stamp = _dt.date.today().isoformat()
    lines = [
        "# Trust Report",
        "",
        f"*Generated by `scripts/eval_trust.py` on {stamp} — mode: **{mode}**,",
        f"embeddings: {eng.document_source.index.embedder.backend}. Regenerate with"
        f" `.venv/bin/python scripts/eval_trust.py`.*",
        "",
        f"## Trust Score: **{trust:.1f} / 100**",
        "",
        "| Component | What it measures | Weight | Score |",
        "| --- | --- | --- | --- |",
        f"| Routing quality | golden routes (scripts/eval.py set) | {WEIGHTS['routing']:.0%} | {routing:.1%} |",
        f"| Retrieval quality | Recall@k (qa.jsonl) | {WEIGHTS['retrieval']:.0%} | {recall:.1%} |",
        f"| Evidence quality | evidence coverage (qa.jsonl) | {WEIGHTS['evidence']:.0%} | {evidence:.1%} |",
        f"| Answer quality | aspect completeness (multi_aspect.jsonl) | {WEIGHTS['answers']:.0%} | {answers:.1%} |",
        f"| Conflict handling | contradiction fixtures: detect + report + no silent resolution | {WEIGHTS['conflicts']:.0%} | {conflicts:.1%} |",
        f"| Grounding / honesty | unanswerable battery + answerable controls | {WEIGHTS['grounding']:.0%} | {grounding:.1%} |",
        f"| Citation quality | citation verification on answered questions | {WEIGHTS['citations']:.0%} | {citations_a:.1%} |",
        "",
        "## A — Routing (golden routes)",
        "",
        "| Case | Expected | Got | OK |",
        "| --- | --- | --- | --- |",
        *routing_rows,
        "",
        "## B — Retrieval & evidence coverage (qa.jsonl)",
        "",
        "| Case | Result |",
        "| --- | --- |",
        *qa_rows,
        "",
        "## C — Multi-aspect completeness (multi_aspect.jsonl)",
        "",
        "| Case | Aspects | Result |",
        "| --- | --- | --- |",
        *ma_rows,
        "",
        "## D — Honesty: unanswerable battery + controls (unanswerable.jsonl)",
        "",
        f"*{skipped} live-only case(s) skipped in offline mode.*",
        "",
        "| Case | Expect | Result |",
        "| --- | --- | --- |",
        *un_rows,
        "",
        "## E — Contradiction handling (data/eval/contradictions/)",
        "",
        "| Check | OK |",
        "| --- | --- |",
        *contra_rows,
        "",
        "## Reading this report",
        "",
        "- Every component score traces to the per-case tables above — no aggregate",
        "  hides a failing case.",
        "- The conflict component is pass/fail per seeded contradiction: *detected*",
        "  (trace.conflicts), *both-values* (the answer contains both sides), and",
        "  *explicit* (the answer states the disagreement). A silent resolution scores 0.",
        "- Offline mode exercises the deterministic fallbacks (rule router, extractive",
        "  generation); live mode exercises the configured model stack. Run both before",
        "  a release and compare.",
        "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report written to {REPORT.relative_to(ROOT)}")

    if args.verbose:
        for r in routing_rows + qa_rows + ma_rows + un_rows + contra_rows:
            print(r)
    return 0 if trust >= 90 else 1


if __name__ == "__main__":
    sys.exit(main())
