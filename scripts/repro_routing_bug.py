"""Reproduce / validate the document-routing bug (and the safety-net fix).

Uploads the two PDFs from the incident, runs the five known-failing questions through
the full engine, and prints the route, retrieval, and final answer for each — then runs
a router-BYPASS retrieval probe proving retrieval can answer every question.

    .venv/bin/python -m scripts.repro_routing_bug            # use configured provider (live)
    ABA_OFFLINE_MODE=always ABA_EMBEDDING_BACKEND=hashing \
        .venv/bin/python -m scripts.repro_routing_bug        # deterministic, no network

Before the fix: Q1/Q4/Q5 → NONE, Q2 → PDF but 0 evidence, Q3 flaky. After the fix: all 5
recover the expected answer (the safety net runs retrieval before declaring out-of-scope).
See docs/routing-bug-investigation.md and docs/root-cause-analysis.md.
"""
from __future__ import annotations

import sys
from pathlib import Path

from app.config import ROOT
from app.engine import get_engine

# (question, expected-substring-in-answer)
CASES = [
    ("Who was this proposal prepared for?", "Vincent Ochs"),
    ("Who prepared the IMM valuation document?", "Apoorv Pandey"),
    ("What is the proposed valuation amount?", "$450"),
    ("What is Apoorv Pandey's email address?", "apoorv.pandey.23cse@bmu.edu.in"),
    ("What university is Apoorv currently attending?", "BML Munjal University"),
]


def _find_pdfs() -> list[Path]:
    """Locate the two incident PDFs (uploaded copy first, then repo root)."""
    wanted = [
        ["IMM_Prototype_Scope_and_Valuation.pdf"],
        ["Apoorv-Pandey-B.Tech.-ComputerScience_Engineering-2026-06-02-07-29-09-289628.pdf",
         "Apoorv-Pandey-B.Tech.-ComputerScience&Engineering-2026-06-02-07-29-09-289628.pdf"],
    ]
    search_dirs = [ROOT / "data" / "uploads" / "pdfs", ROOT]
    out: list[Path] = []
    for names in wanted:
        for d in search_dirs:
            hit = next((d / n for n in names if (d / n).exists()), None)
            if hit:
                out.append(hit)
                break
    return out


def main() -> int:
    eng = get_engine()
    s = eng.settings
    print(f"\nprovider={s.llm_provider} router={s.model_router} gen={s.model_generation} "
          f"use_live_llm={s.use_live_llm} embeddings={eng.document_source.index.embedder.backend}\n")

    pdfs = _find_pdfs()
    if len(pdfs) < 2:
        print("ERROR: could not locate both incident PDFs (IMM + resume).")
        return 2
    for p in pdfs:
        info = eng.add_pdf(p.name, p)
        print(f"  uploaded {info.name}  status={info.status} chunks={info.chunks_indexed}")

    print("\n" + "=" * 96)
    print("END-TO-END (router → retrieve → generate) — the path the API uses")
    print("=" * 96)
    passed = 0
    for q, expected in CASES:
        resp = eng.ask(q)
        rd = resp.trace.route
        route_call = next((c for c in resp.trace.llm_calls if c.purpose == "routing"), None)
        ok = (expected.lower() in resp.answer.lower()) and not resp.insufficient
        passed += ok
        print(f"\n[{'PASS' if ok else 'FAIL'}] {q}")
        print(f"   route={rd.route if rd else '?'} conf={rd.confidence if rd else '?'} "
              f"mode={route_call.mode if route_call else '?'} "
              f"evidence={len(resp.trace.evidence)} insufficient={resp.insufficient}")
        print(f"   expected: {expected!r}")
        print(f"   answer:   {resp.answer[:200]}")

    print("\n" + "=" * 96)
    print("RETRIEVAL PROBE (router BYPASSED — raw question straight to retrieval)")
    print("=" * 96)
    for q, expected in CASES:
        ev, tr = eng.document_source.retrieve(q)
        rank = next((i for i, e in enumerate(ev, 1) if expected.lower() in e.content.lower()), None)
        print(f"   ev={len(ev):>2} intent={tr.intent:<8} answer-chunk-rank={rank}  :: {q}")

    print("\n" + "-" * 96)
    print(f"{passed}/{len(CASES)} end-to-end cases pass\n")
    return 0 if passed == len(CASES) else 1


if __name__ == "__main__":
    sys.exit(main())
