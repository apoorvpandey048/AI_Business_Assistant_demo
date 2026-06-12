"""Tiny retrieval/routing eval + smoke test.

Runs the scripted regression questions through the full engine and checks:
- the route matches the expected route,
- answerable questions retrieve evidence and pass citation verification,
- the out-of-scope question is correctly flagged 'insufficient'.

Works fully offline (deterministic fallbacks). With an API key configured, it
exercises the live model path instead.

The questions target the bundled sample corpus (data/pdfs + data/business.db),
which exists for evaluation and regression testing; the product UI never surfaces
it. The reference date is pinned to the seed-data anchor so date-window questions
("expiring in the next 90 days") stay deterministic.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

os.environ.setdefault("ABA_REFERENCE_DATE", "2026-06-08")  # seed-data anchor

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.engine import get_engine


@dataclass(frozen=True)
class EvalQuestion:
    label: str
    question: str
    route: str          # expected route: PDF | SQL | HYBRID | NONE
    why: str
    language: str = "en"


QUESTIONS = [
    EvalQuestion(
        label="Pure SQL", route="SQL",
        question="What is the total outstanding invoice amount per customer?",
        why="Aggregation over the database; clean generated SQL with table/row citations."),
    EvalQuestion(
        label="Pure document", route="PDF",
        question="What do our contracts say about service suspension?",
        why="Hybrid retrieval (dense + BM25) over the PDFs with page-level citations."),
    EvalQuestion(
        label="Keyword beats vector", route="PDF",
        question="Which contract clauses mention SLA-2025?",
        why="BM25 finds the exact identifier 'SLA-2025' that pure embeddings miss."),
    EvalQuestion(
        label="Hybrid (agentic)", route="HYBRID",
        question="Which customers have overdue invoices, and what do their agreements say about service suspension?",
        why="SQL finds overdue customers → those customers' contracts are retrieved → grounded combined answer."),
    EvalQuestion(
        label="Hybrid (date + clause)", route="HYBRID",
        question="What contracts expire in the next 90 days, and what penalties do they define?",
        why="Date filter in SQL + penalty clauses from the documents — impossible with vector search alone."),
    EvalQuestion(
        label="Hybrid (projects + risks)", route="HYBRID",
        question="Show all active projects and summarize the risks in their documentation.",
        why="SQL lists active projects; project briefs supply the risk narrative, grouped per project."),
    EvalQuestion(
        label="Hebrew", route="PDF", language="he",
        question="מה אומר ההסכם של תבור מערכות על השעיית שירות וקנסות?",
        why="Bilingual retrieval over a Hebrew contract with right-to-left citations."),
    EvalQuestion(
        label="Honest grounding", route="NONE",
        question="What is our employee headcount in Berlin?",
        why="No source can answer → the system says 'insufficient evidence' instead of guessing."),
]


def main() -> int:
    eng = get_engine()
    cfg_mode = "live" if eng.settings.use_live_llm else "offline"
    print(f"\nMode: {cfg_mode} | embeddings: {eng.document_source.index.embedder.backend} | "
          f"vector: {eng.document_source.index.store.backend}\n")
    print(f"{'expect':>7} {'got':>7}  ok   ev  cite  question")
    print("-" * 100)

    passed = 0
    for ex in QUESTIONS:
        resp = eng.ask(ex.question)
        route = resp.trace.route.route if resp.trace.route else "?"
        route_ok = route == ex.route
        ev = len(resp.trace.evidence)
        cited = resp.trace.citation_check.verified if resp.trace.citation_check else False

        if ex.route == "NONE":
            ok = route_ok and resp.insufficient
        else:
            ok = route_ok and ev > 0 and cited and not resp.insufficient
        passed += ok
        flag = "✓" if ok else "✗"
        print(f"{ex.route:>7} {route:>7}  {flag:>2}  {ev:>3}  {str(cited):>5}  {ex.question[:64]}")

    total = len(QUESTIONS)

    # Keyword-precision regression: a "which document mentions <exact id>" lookup must
    # return ONLY passages from the document that literally contains the id — never
    # semantically-similar-but-irrelevant chunks from other documents.
    probe = "Which document mentions INI-MSA-2024?"
    resp = eng.ask(probe)
    docs = {e.document for e in resp.trace.evidence}
    intent = resp.trace.document_retrieval.intent if resp.trace.document_retrieval else "?"
    precise = bool(resp.trace.evidence) and docs == {"INITECH_Agreement.pdf"}
    passed += precise
    total += 1
    print(f"{'PDF':>7} {resp.trace.route.route:>7}  {'✓' if precise else '✗':>2}  "
          f"{len(resp.trace.evidence):>3}  {intent:>5}  {probe[:64]}")

    print("-" * 100)
    print(f"{passed}/{total} passed\n")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
