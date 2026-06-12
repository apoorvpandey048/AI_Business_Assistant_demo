"""Retrieval / citation diagnostics CLI — the bug-reproduction harness.

Runs ONE question through the full engine and prints every pipeline layer
(routing → retrieval → ranking → evidence → generation → citations), so any
failure can be attributed to a specific layer in seconds.

Usage:
    .venv/bin/python scripts/diagnose.py "What penalties do the contracts define?"
    .venv/bin/python scripts/diagnose.py --scope all --role "Act as a lawyer" "..."
    .venv/bin/python scripts/diagnose.py --json "..."          # machine-readable dump
    .venv/bin/python scripts/diagnose.py --expect-doc TAVOR_Contract_HE.pdf "..."

With --expect-doc / --expect-text, the script also prints the FAILURE LAYER:
    routing   — the router declined and the safety net found nothing
    retrieval — the expected document never entered the candidate set
    ranking   — it was a candidate but was not selected as evidence
    generation— it was evidence but the expected text is missing from the answer
    ok        — everything checks out

Offline by default (deterministic). Set ANTHROPIC_API_KEY to exercise live calls.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _failure_layer(resp, expect_doc: str | None, expect_text: str | None) -> str:
    t = resp.trace
    ev_docs = {e.document for e in t.evidence if e.document}
    cand_docs = ({c.document for c in t.document_retrieval.candidates}
                 if t.document_retrieval else set())
    answer = (resp.answer or "").lower()
    ev_text = " ".join(e.content for e in t.evidence).lower()

    if expect_doc:
        if expect_doc in ev_docs:
            if expect_text and expect_text.lower() not in answer and expect_text.lower() not in ev_text:
                return "generation (doc retrieved, fact missing from evidence/answer)"
            return "ok"
        if expect_doc in cand_docs:
            return "ranking (candidate but not selected as evidence)"
        if t.route and t.route.route in ("NONE", "SQL") and not t.safety_net:
            return "routing (never reached document retrieval)"
        return "retrieval (expected document not in candidates)"
    if expect_text:
        if expect_text.lower() in answer:
            return "ok"
        if expect_text.lower() in ev_text:
            return "generation (fact in evidence, missing from answer)"
        return "retrieval (fact not present in any evidence)"
    return "n/a (no expectation provided)"


def main() -> int:
    ap = argparse.ArgumentParser(description="Pipeline diagnostics for one question")
    ap.add_argument("question")
    ap.add_argument("--scope", default="all", choices=["all", "workspace"])
    ap.add_argument("--role", default=None, help="optional persona/role instructions")
    ap.add_argument("--expect-doc", default=None, help="document expected in evidence")
    ap.add_argument("--expect-text", default=None, help="text expected in answer/evidence")
    ap.add_argument("--json", action="store_true", help="dump the full trace as JSON")
    args = ap.parse_args()

    from app.engine import get_engine
    eng = get_engine()
    resp = eng.ask(args.question, scope=args.scope, role_instructions=args.role)
    t = resp.trace

    if args.json:
        print(resp.model_dump_json(indent=2))
        return 0

    print(f"\nQUESTION   {resp.question}")
    print(f"MODE       {t.mode} | embeddings: {eng.document_source.index.embedder.backend}")
    if t.route:
        print(f"ROUTE      {t.route.route} (conf {t.route.confidence:.2f}, "
              f"agentic={t.route.agentic}, langs={t.route.languages})")
        print(f"           {t.route.reasoning}")
        if t.route.document_subquery:
            print(f"           doc sub-query: {t.route.document_subquery}")
        if t.route.sql_subquery:
            print(f"           sql sub-query: {t.route.sql_subquery}")

    dr = t.document_retrieval
    if dr:
        print(f"\nRETRIEVAL  intent={dr.intent} terms={dr.search_terms} "
              f"exact_hits={dr.exact_hits}")
        print(f"           {dr.strategy}")
        print(f"           {len(dr.candidates)} candidate(s):")
        for c in dr.candidates[:12]:
            mark = "→" if c.selected else " "
            print(f"  {mark} #{c.final_rank:<3} {c.document:<42} p.{str(c.page):<4}"
                  f" dense#{str(c.dense_rank):<4} bm25#{str(c.bm25_rank):<4}"
                  f" rrf={c.rrf_score} rerank={c.rerank_score}"
                  f"{' [exact]' if c.keyword_hit else ''}")
    for s in t.sql_executions:
        print(f"\nSQL        [{s.purpose}] valid={s.valid} rows={s.row_count} "
              f"tables={s.tables}")
        print(f"           {s.validated_sql or s.generated_sql}")
        if s.validation_error:
            print(f"           error: {s.validation_error}")

    print(f"\nSAFETY NET {'FIRED — evidence recovered by direct search' if t.safety_net else 'not fired'}")
    print(f"\nEVIDENCE   {len(t.evidence)} item(s):")
    for e in t.evidence:
        used = "USED" if e.used else "    "
        print(f"  [{e.id}] {used} {e.citation_label}  score={e.score}")
        print(f"         {' '.join(e.content.split())[:140]}")

    print(f"\nANSWER     insufficient={resp.insufficient} | "
          f"generation={t.generation.get('model')} | "
          f"role_applied={t.generation.get('role_applied', False)}")
    print(f"  {resp.answer}\n")
    if t.citation_check:
        print(f"CITATIONS  verified={t.citation_check.verified} "
              f"cited={t.citation_check.cited_ids} unknown={t.citation_check.unknown_ids}")
    print("\nORCHESTRATOR TRACE")
    for i, n in enumerate(t.notes, 1):
        print(f"  {i}. {n}")

    if args.expect_doc or args.expect_text:
        layer = _failure_layer(resp, args.expect_doc, args.expect_text)
        print(f"\nFAILURE LAYER: {layer}")
        return 0 if layer.startswith("ok") else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
