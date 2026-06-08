"""The orchestrator — turns a question into a grounded, cited answer plus a complete
inspectable trace. This is where the difference between a PDF chatbot and a retrieval
orchestration engine actually lives.
"""
from __future__ import annotations

import time
from typing import Optional

from app.generation.generate import generate_answer
from app.generation.verify import verify_citations
from app.models import (AskResponse, Evidence, LLMCall, RouteDecision, StageTiming,
                        Trace)
from app.pricing import summarize
from app.routing.classify import classify
from app.sources.base import router_capability_brief
from app.sources.document_source import DocumentSource
from app.sources.relational_source import RelationalSource


class Orchestrator:
    def __init__(self, documents: DocumentSource, relational: RelationalSource) -> None:
        self.documents = documents
        self.relational = relational
        self.capability_brief = router_capability_brief(
            [documents.describe(), relational.describe()]
        )

    # ----------------------------------------------------------------------
    def ask(self, question: str) -> AskResponse:
        t0 = time.perf_counter()
        trace = Trace(question=question)
        evidence: list[Evidence] = []
        calls: list[LLMCall] = []

        # 1) ROUTE
        ts = time.perf_counter()
        decision, route_call = classify(question, self.capability_brief)
        calls.append(route_call)
        trace.route = decision
        trace.languages = decision.languages
        trace.timings.append(StageTiming(name="routing", duration_ms=_ms(ts)))
        trace.notes.append(
            f"Router → {decision.route}"
            + (" (agentic: SQL → entities → filtered documents)" if decision.agentic else "")
            + f". {decision.reasoning}"
        )

        # 2) RETRIEVE per route
        if decision.route == "SQL":
            evidence += self._sql_branch(trace, calls, decision.sql_subquery or question, "sql_main")

        elif decision.route == "PDF":
            evidence += self._doc_branch(
                trace, decision.document_subquery or question, decision.languages
            )

        elif decision.route == "HYBRID":
            evidence += self._hybrid_branch(trace, calls, decision, question)

        else:  # NONE
            trace.notes.append("No source matched — declining to answer (out of scope).")

        # 3) Re-label evidence e1..eN (single source of truth for citations)
        for i, e in enumerate(evidence, start=1):
            e.id = f"e{i}"
        trace.evidence = evidence

        # 4) GENERATE (grounded) + VERIFY
        ts = time.perf_counter()
        answer, cited, insufficient, gen_call = generate_answer(question, evidence)
        if gen_call:
            calls.append(gen_call)
        trace.timings.append(StageTiming(name="generation", duration_ms=_ms(ts)))
        trace.generation = {
            "model": gen_call.model if gen_call else "extractive-fallback",
            "grounded": True,
            "insufficient": insufficient,
        }

        check = verify_citations(answer, cited, evidence)
        trace.citation_check = check
        if not check.verified and evidence:
            trace.notes.append(f"Citation check: {check.note}")

        # 5) finalize
        trace.llm_calls = calls
        trace.cost = summarize(calls)
        trace.mode = _mode(calls)
        trace.timings.append(StageTiming(name="total", duration_ms=_ms(t0)))

        cited_set = set(check.cited_ids)
        citations = [e for e in evidence if e.id in cited_set] or (
            evidence if not insufficient else []
        )
        return AskResponse(
            question=question, answer=answer, insufficient=insufficient,
            citations=citations, trace=trace,
        )

    # -- branches ----------------------------------------------------------
    def _doc_branch(self, trace: Trace, query: str, languages: list[str] | None = None) -> list[Evidence]:
        filters = {"languages": languages} if languages else {}
        ev, dtrace = self.documents.retrieve(query, filters=filters)
        trace.document_retrieval = dtrace
        trace.notes.append(
            f"Document retrieval ({dtrace.embedding_backend} + BM25 → RRF → "
            f"{dtrace.reranker_backend}) selected {len(ev)} passage(s)."
        )
        return ev

    def _sql_branch(self, trace: Trace, calls, query: str, purpose: str) -> list[Evidence]:
        ev, strace, call = self.relational.run(query, purpose=purpose)
        if call:
            calls.append(call)
        trace.sql_executions.append(strace)
        if strace.valid:
            trace.notes.append(
                f"SQL ({purpose}) validated read-only, returned {strace.row_count} row(s)."
            )
        else:
            trace.notes.append(f"SQL ({purpose}) rejected/failed: {strace.validation_error}")
        return ev

    def _hybrid_branch(self, trace: Trace, calls, decision: RouteDecision, question: str) -> list[Evidence]:
        evidence: list[Evidence] = []

        # Step 1: structured lookup
        sql_q = decision.sql_subquery or question
        sql_ev, strace, call = self.relational.run(sql_q, purpose="sql_step")
        if call:
            calls.append(call)
        trace.sql_executions.append(strace)
        evidence += sql_ev
        trace.notes.append(
            f"Step 1 — SQL returned {strace.row_count} row(s)" if strace.valid
            else f"Step 1 — SQL failed: {strace.validation_error}"
        )

        # Step 2: agentic linking — SQL results constrain document retrieval.
        # Either the rows already carry a document reference (pdf_file/doc_file), or we
        # map the customers they reference to their contract documents via a linking query.
        doc_filter = {}
        cust_map = _pdf_owner_map(strace.rows)  # pdf/doc file -> owning entity name
        if decision.agentic and strace.valid and strace.rows:
            direct = _documents_from_rows(strace.rows)
            if direct:
                doc_filter = {"documents": direct}
                trace.notes.append(
                    f"Step 2 — linked {strace.row_count} row(s) directly to {len(direct)} "
                    f"document(s) {direct}; restricting document retrieval to them."
                )
            else:
                ids = self.relational.extract_customer_ids(strace.rows)
                if ids:
                    pdfs, names, link_trace = self.relational.link_customers_to_documents(ids)
                    trace.sql_executions.append(link_trace)
                    if pdfs:
                        doc_filter = {"documents": pdfs}
                        cust_map.update(_pdf_owner_map(link_trace.rows))
                        trace.notes.append(
                            f"Step 2 — linked {len(names)} customer(s) {names} → "
                            f"{len(pdfs)} contract document(s); restricting document retrieval to them."
                        )

        # Step 3: document retrieval (optionally filtered by linked docs + query language)
        doc_q = decision.document_subquery or question
        if decision.languages:
            doc_filter = {**doc_filter, "languages": decision.languages}
        doc_ev, dtrace = self.documents.retrieve(doc_q, filters=doc_filter)
        trace.document_retrieval = dtrace
        # Stamp the owning entity onto each passage so the model can't misattribute a
        # generic clause (e.g. "Provider may suspend…") to the wrong customer.
        for e in doc_ev:
            owner = cust_map.get(e.document)
            if owner:
                e.extra["owner"] = owner
                e.content = f"(From {owner}'s agreement) {e.content}"
        evidence += doc_ev
        n_docs = len(doc_filter.get("documents", [])) if isinstance(doc_filter, dict) else 0
        trace.notes.append(
            f"Step 3 — document retrieval"
            + (f" (filtered to {n_docs} doc(s))" if n_docs else "")
            + f" selected {len(doc_ev)} passage(s)."
        )
        return evidence


def _documents_from_rows(rows: list[dict]) -> list[str]:
    """Collect document references (pdf_file / doc_file) present in SQL result rows."""
    out: list[str] = []
    for r in rows:
        for col in ("pdf_file", "doc_file"):
            v = r.get(col)
            if v and v not in out:
                out.append(v)
    return out


def _pdf_owner_map(rows: list[dict]) -> dict[str, str]:
    """Map a document file -> its owning entity name, from SQL result rows."""
    m: dict[str, str] = {}
    for r in rows:
        doc = r.get("pdf_file") or r.get("doc_file")
        owner = r.get("customer") or r.get("name") or r.get("project")
        if doc and owner:
            m[doc] = str(owner)
    return m


def _ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 1)


def _mode(calls: list[LLMCall]) -> str:
    modes = {c.mode for c in calls}
    if not modes:
        return "deterministic"
    if modes == {"live"}:
        return "live"
    if "live" not in modes:
        return "offline"
    return "mixed"
