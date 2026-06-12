"""The orchestrator — turns a question into a grounded, cited answer plus a complete
inspectable trace. This is where the difference between a PDF chatbot and a retrieval
orchestration engine actually lives.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Optional

from app.generation.conflicts import detect_conflicts
from app.generation.generate import generate_answer
from app.generation.verify import verify_citations
from app.models import (AskResponse, Evidence, LLMCall, RouteDecision, StageTiming,
                        Trace)
from app.pricing import summarize
from app.retrieval.intent import content_terms, is_document_lookup, term_in_text
from app.routing.classify import classify
from app.sources.base import router_capability_brief
from app.sources.document_source import DocumentSource
from app.sources.structured_source import StructuredSource

logger = logging.getLogger("aba.orchestrator")

_HEB_CHARS = re.compile(r"[֐-׿]")


class Orchestrator:
    def __init__(self, documents: DocumentSource, relational: StructuredSource) -> None:
        self.documents = documents
        self.relational = relational
        self.capability_brief = router_capability_brief(
            [documents.describe(), relational.describe()]
        )

    # ----------------------------------------------------------------------
    def ask(self, question: str, allowed_docs: Optional[list[str]] = None,
            allowed_tables: Optional[list[str]] = None,
            role_instructions: Optional[str] = None) -> AskResponse:
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
            evidence += self._sql_branch(
                trace, calls, decision.sql_subquery or question, "sql_main", allowed_tables
            )

        elif decision.route == "PDF":
            evidence += self._doc_branch(
                trace, question, decision.languages, allowed_docs,
                rewrite=decision.document_subquery,
            )

        elif decision.route == "HYBRID":
            evidence += self._hybrid_branch(
                trace, calls, decision, question, allowed_docs, allowed_tables
            )

        else:  # NONE
            trace.notes.append(
                "No uploaded source appears to contain this — insufficient evidence "
                "(declining unless the document safety net recovers a relevant passage)."
            )

        # 2b) DOCUMENT SAFETY NET --------------------------------------------
        # Never declare a question out-of-scope without giving retrieval a real chance.
        # The (small) LLM router sometimes wrongly returns NONE for a document-answerable
        # question, or routes PDF but with a rewritten sub-query that defeats retrieval
        # (e.g. a literal filename → keyword trap). If documents are in scope and the route
        # produced no document evidence, run a plain search on the ORIGINAL question and
        # adopt the result only if it is lexically on-topic — so genuinely out-of-scope
        # questions still honestly decline. See docs/root-cause-analysis.md.
        safety_net_fired = False
        if self._should_try_doc_safety_net(decision.route, evidence, allowed_docs):
            sn_ev = self._doc_safety_net(trace, question, decision, allowed_docs)
            if sn_ev:
                evidence += sn_ev
                safety_net_fired = True
        trace.safety_net = safety_net_fired

        # 2c) CROSS-SOURCE CONFLICT CHECK ------------------------------------
        # "What if the PDF and the database disagree?" — never answer from one
        # source while another in-scope source contradicts it. SQL and HYBRID
        # answers get a cheap document corroboration probe (no LLM call) over ALL
        # in-scope documents; passages that CONFLICT with the existing evidence are
        # adopted so the answer can report the disagreement with citations. HYBRID
        # needs this too: its agentic step filters documents to the DB-linked
        # contracts, which is exactly how a contradicting amendment stays unseen.
        # On clean data nothing is adopted and behavior is unchanged.
        # See docs/conflict-resolution.md.
        if decision.route in ("SQL", "HYBRID") and evidence:
            evidence += self._conflict_probe(trace, question, decision, evidence,
                                             allowed_docs)

        # 3) Re-label evidence e1..eN (single source of truth for citations)
        for i, e in enumerate(evidence, start=1):
            e.id = f"e{i}"
        trace.evidence = evidence

        # 3b) Detect conflicts on the FINAL evidence set (ids are now stable) so the
        # trace and the answer can report them. Detection is deterministic and must
        # stay silent on the clean sample corpus (regression-gated).
        conflicts = detect_conflicts(evidence)
        trace.conflicts = conflicts
        if conflicts:
            trace.notes.append(
                "Conflict detection — the sources disagree and the answer reports it "
                "(no silent resolution): " + "; ".join(c.note for c in conflicts)
            )

        # 4) GENERATE (grounded) + VERIFY
        ts = time.perf_counter()
        kw_terms = None
        dr = trace.document_retrieval
        # Use the deterministic "the keyword appears in document Y" answer ONLY for genuine
        # document-IDENTIFICATION questions ("which document mentions X"). A fact-EXTRACTION
        # question that merely contains a distinctive term ("what is Apoorv's email?") is
        # retrieved keyword-first but must EXTRACT the fact via grounded generation. Likewise
        # a safety-net recovery always extracts (kw_terms=None).
        # Gate on the ORIGINAL question, never the router's rewritten document_subquery —
        # the router often injects a filename or the word "document"/"resume" that would
        # falsely look like an identification request.
        if (not safety_net_fired and dr and dr.intent == "keyword" and dr.search_terms
                and is_document_lookup(question)):
            kw_terms = dr.search_terms
        answer, cited, insufficient, gen_call = generate_answer(
            question, evidence, keyword_terms=kw_terms,
            role_instructions=role_instructions, conflicts=conflicts,
        )
        if not evidence:
            # Nothing was retrieved — give an honest, specific account of what was
            # searched and why no answer could be grounded (never fabricate). The
            # message is written in the question's language (Hebrew gets Hebrew).
            answer = self._no_evidence_answer(decision, trace, question)
            insufficient = True
        if gen_call:
            calls.append(gen_call)
        trace.timings.append(StageTiming(name="generation", duration_ms=_ms(ts)))
        trace.generation = {
            "model": (gen_call.model if gen_call
                      else "deterministic lookup" if (kw_terms and evidence)
                      else "extractive-fallback"),
            "grounded": True,
            "insufficient": insufficient,
            "role_applied": bool(role_instructions),
        }

        check = verify_citations(answer, cited, evidence)
        trace.citation_check = check
        # mark which evidence the final answer actually used (answer-supported)
        cited_ids = set(check.cited_ids)
        for e in evidence:
            e.used = e.id in cited_ids
        if not check.verified and evidence:
            trace.notes.append(f"Citation check: {check.note}")

        # 5) finalize
        trace.llm_calls = calls
        trace.cost = summarize(calls)
        trace.mode = _mode(calls)
        trace.timings.append(StageTiming(name="total", duration_ms=_ms(t0)))

        # Citations = ONLY the evidence the answer verifiably cited. There is no
        # "fall back to everything retrieved" — showing un-cited evidence as a source
        # is exactly the untrustworthy-evidence-panel bug reported by the client.
        cited_set = set(check.cited_ids)
        citations = [e for e in evidence if e.id in cited_set]
        if not citations and evidence and not insufficient:
            trace.notes.append(
                "The answer cited no specific evidence ids; the sources panel is left "
                "empty (the full retrieved set remains visible in the Inspector)."
            )
        return AskResponse(
            question=question, answer=answer, insufficient=insufficient,
            citations=citations, trace=trace,
        )

    def _no_evidence_answer(self, decision: RouteDecision, trace: Trace,
                            question: str = "") -> str:
        """An honest, specific 'insufficient evidence' message: what was searched and why
        nothing could be grounded. Never fabricates an answer. Written in the question's
        language — a Hebrew question gets a Hebrew decline, not an English wall of text."""
        n_docs = len(self.documents.documents)
        n_tables = len(self.relational.schema.tables)
        hebrew = "he" in (decision.languages or []) or bool(_HEB_CHARS.search(question))

        searched: list[str] = []
        if decision.route in ("PDF", "HYBRID"):
            searched.append(f"{n_docs} document(s)")
        if decision.route in ("SQL", "HYBRID"):
            searched.append(f"{n_tables} database table(s)")
        where = " and ".join(searched) if searched else "the connected sources"

        dr = trace.document_retrieval
        if hebrew:
            if dr and dr.intent == "keyword" and dr.search_terms:
                terms = ", ".join(f'"{t}"' for t in dr.search_terms)
                return (f"אין מספיק ראיות: אף מסמך בסביבת העבודה אינו מכיל את {terms}. "
                        f"חיפשנו בטקסט המלא של {n_docs} המסמכים ולא נמצאה פסקה תואמת.")
            if decision.route == "SQL":
                return ("אין מספיק ראיות: שאילתת מסד הנתונים לא החזירה רשומות התואמות "
                        "לשאלה זו.")
            return (f"אין מספיק ראיות: חיפשנו ב-{n_docs} המסמכים וב-{n_tables} טבלאות "
                    "מסד הנתונים שהועלו, ולא נמצאו רשומות או פסקאות רלוונטיות מספיק "
                    "כדי לבסס תשובה.")
        if dr and dr.intent == "keyword" and dr.search_terms:
            terms = ", ".join(f'"{t}"' for t in dr.search_terms)
            return (f"Insufficient evidence: no document in the workspace contains {terms}. "
                    f"Searched the full text of {where} and found no matching passage.")
        if decision.route == "NONE":
            return ("Insufficient evidence: none of the uploaded sources — the "
                    f"{n_docs} document(s) and the {n_tables} database table(s) — appear to "
                    "contain what this question asks for, so it cannot be grounded in them.")
        if decision.route == "SQL":
            return (f"Insufficient evidence: the database query returned no rows. Searched "
                    f"{where} and found no records matching this question.")
        return (f"Insufficient evidence: searched {where} but found no records or document "
                f"passages relevant enough to ground an answer.")

    # -- document safety net -----------------------------------------------
    def _should_try_doc_safety_net(
        self, route: str, evidence: list[Evidence], allowed_docs: Optional[list[str]]
    ) -> bool:
        """Fire the safety net when documents are in scope but the route produced no
        document evidence — i.e. the router declined (NONE), routed PDF/HYBRID but
        retrieval came back empty, or mis-routed a doc question to SQL with no rows.
        Never fires when a SQL route already returned rows, or when documents are out
        of scope."""
        if allowed_docs is not None and len(allowed_docs) == 0:
            return False                       # no documents in scope
        if any(e.source_kind == "documents" for e in evidence):
            return False                       # documents already answered
        if route == "SQL" and evidence:
            return False                       # working SQL answer — leave it alone
        return True

    def _doc_safety_net(self, trace: Trace, question: str, decision: RouteDecision,
                        allowed_docs: Optional[list[str]]) -> list[Evidence]:
        """Search the in-scope documents on the ORIGINAL question (never the router's
        possibly-mangled document_subquery) and adopt the result only if it is lexically
        on-topic. Returns adopted evidence (possibly empty)."""
        filters: dict = {}
        if decision.languages:
            filters["languages"] = decision.languages
        if allowed_docs:
            filters["documents"] = allowed_docs
        ev, dtrace = self.documents.retrieve(question, filters=filters)
        trace.document_retrieval = dtrace      # show the recovery attempt in the inspector
        n_docs = len(allowed_docs) if allowed_docs else len(self.documents.documents)

        if not ev:
            trace.notes.append(
                f"Safety net — router yielded no document evidence; a direct search of "
                f"{n_docs} in-scope document(s) on the original question also found nothing."
            )
            return []
        if not _on_topic(question, ev):
            trace.notes.append(
                "Safety net — a direct document search returned only off-topic passages "
                "(no shared keyword with the question); declining to ground an answer."
            )
            return []

        trace.notes.append(
            f"Safety net — router returned no document evidence (route {decision.route}), but "
            f"a direct search of {n_docs} in-scope document(s) on the original question "
            f"recovered {len(ev)} relevant passage(s). Answering from documents."
        )
        logger.info("doc safety-net recovered %d passage(s) for route=%s question=%r",
                    len(ev), decision.route, question)
        return ev

    # -- cross-source conflict probe -----------------------------------------
    def _conflict_probe(self, trace: Trace, question: str, decision: RouteDecision,
                        evidence: list[Evidence],
                        allowed_docs: Optional[list[str]]) -> list[Evidence]:
        """A SQL answer is only trustworthy if no in-scope document contradicts it.
        Run a plain document search on the original question and adopt ONLY the
        passages that the conflict detector says disagree with the SQL rows. No
        conflict → nothing is adopted → identical behavior to before this check."""
        if allowed_docs is not None and len(allowed_docs) == 0:
            return []
        filters: dict = {}
        if decision.languages:
            filters["languages"] = decision.languages
        if allowed_docs:
            filters["documents"] = allowed_docs
        probe_ev, probe_trace = self.documents.retrieve(question, filters=filters)
        if not probe_ev:
            return []
        conflicts = detect_conflicts(evidence + probe_ev)
        if not conflicts:
            return []
        existing_ids = {e.id for e in evidence}
        adopt: list[Evidence] = []
        for c in conflicts:
            side_ids = {s.evidence_id for s in c.sides}
            if not (side_ids & existing_ids):
                continue                       # conflict among probe passages only
            for e in probe_ev:
                if e.id in side_ids and e.id not in existing_ids and e not in adopt:
                    adopt.append(e)            # never re-adopt an already-present chunk
        if adopt:
            if trace.document_retrieval is None:   # keep the HYBRID step-3 trace visible
                trace.document_retrieval = probe_trace
            trace.notes.append(
                f"Cross-source conflict check — the database result disagrees with "
                f"{len(adopt)} document passage(s); adopting them as evidence and "
                f"reporting the conflict instead of silently preferring one source."
            )
            logger.info("conflict probe adopted %d passage(s) for question=%r",
                        len(adopt), question)
        return adopt

    # -- branches ----------------------------------------------------------
    def _doc_branch(self, trace: Trace, query: str, languages: list[str] | None = None,
                    allowed_docs: Optional[list[str]] = None,
                    rewrite: Optional[str] = None) -> list[Evidence]:
        if allowed_docs is not None and len(allowed_docs) == 0:
            trace.notes.append("No documents in scope — skipping document retrieval.")
            return []
        filters: dict = {}
        if languages:
            filters["languages"] = languages
        if allowed_docs:
            filters["documents"] = allowed_docs
        # The user's question is the PRIMARY search; the router's rewritten sub-query
        # joins the fusion as an auxiliary phrasing. A rewrite ("look for the recipient
        # of the proposal in the documents") adds recall but can never out-vote or
        # crowd out the question itself (question-anchor guarantee in the retriever).
        extra = [rewrite] if rewrite and rewrite.strip() != query.strip() else None
        ev, dtrace = self.documents.retrieve(query, filters=filters, extra_queries=extra)
        trace.document_retrieval = dtrace
        trace.notes.append(
            f"Document retrieval ({dtrace.embedding_backend} + BM25 → RRF → "
            f"{dtrace.reranker_backend}) selected {len(ev)} passage(s)."
        )
        return ev

    def _sql_branch(self, trace: Trace, calls, query: str, purpose: str,
                    allowed_tables: Optional[list[str]] = None) -> list[Evidence]:
        if allowed_tables is not None and len(allowed_tables) == 0:
            trace.notes.append("No database tables in scope — skipping the structured lookup.")
            return []
        ev, strace, call = self.relational.run(query, purpose=purpose, allowed_tables=allowed_tables)
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

    def _hybrid_branch(self, trace: Trace, calls, decision: RouteDecision, question: str,
                       allowed_docs: Optional[list[str]] = None,
                       allowed_tables: Optional[list[str]] = None) -> list[Evidence]:
        evidence: list[Evidence] = []
        linked_docs: Optional[list[str]] = None     # documents discovered via SQL→entity link
        cust_map: dict[str, str] = {}

        # Step 1: structured lookup (scoped to the tables in scope)
        if allowed_tables is not None and len(allowed_tables) == 0:
            trace.notes.append("Step 1 — no database tables in scope; skipping the structured lookup.")
        else:
            sql_q = decision.sql_subquery or question
            sql_ev, strace, call = self.relational.run(
                sql_q, purpose="sql_step", allowed_tables=allowed_tables
            )
            if call:
                calls.append(call)
            trace.sql_executions.append(strace)
            evidence += sql_ev
            trace.notes.append(
                f"Step 1 — SQL returned {strace.row_count} row(s)" if strace.valid
                else f"Step 1 — SQL failed: {strace.validation_error}"
            )
            cust_map = _pdf_owner_map(strace.rows)  # pdf/doc file -> owning entity name

            # Step 2: agentic linking — SQL results constrain document retrieval. Either the
            # rows already carry a document reference (pdf_file/doc_file), or we map the
            # customers they reference to their contract documents via a linking query.
            if decision.agentic and strace.valid and strace.rows:
                direct = _documents_from_rows(strace.rows)
                if direct:
                    linked_docs = direct
                    trace.notes.append(
                        f"Step 2 — linked {strace.row_count} row(s) directly to {len(direct)} "
                        f"document(s) {direct}."
                    )
                else:
                    ids = self.relational.extract_customer_ids(strace.rows)
                    if ids:
                        pdfs, names, link_trace = self.relational.link_customers_to_documents(ids)
                        trace.sql_executions.append(link_trace)
                        if pdfs:
                            linked_docs = pdfs
                            cust_map.update(_pdf_owner_map(link_trace.rows))
                            trace.notes.append(
                                f"Step 2 — linked {len(names)} customer(s) {names} → "
                                f"{len(pdfs)} contract document(s)."
                            )

        # Step 3: document retrieval. The document set = the agentic link ∩ the scope.
        if allowed_docs is not None and len(allowed_docs) == 0:
            trace.notes.append("Step 3 — no documents in scope; skipping document retrieval.")
            return evidence

        if linked_docs is not None and allowed_docs is not None:
            docs_list: Optional[list[str]] = [d for d in linked_docs if d in set(allowed_docs)]
        elif linked_docs is not None:
            docs_list = linked_docs
        else:
            docs_list = allowed_docs  # may be None (no restriction)

        doc_filter: dict = {}
        if docs_list is not None:
            if len(docs_list) == 0:
                trace.notes.append("Step 3 — linked documents are out of scope; no document evidence.")
                return evidence
            doc_filter["documents"] = docs_list
        if decision.languages:
            doc_filter["languages"] = decision.languages

        # primary = the user's question; the router's focused sub-query joins the
        # fusion as an auxiliary phrasing (same rationale as _doc_branch)
        sub = decision.document_subquery
        extra = [sub] if sub and sub.strip() != question.strip() else None
        doc_ev, dtrace = self.documents.retrieve(question, filters=doc_filter,
                                                 extra_queries=extra)
        trace.document_retrieval = dtrace
        # Stamp the owning entity onto each passage so the model can't misattribute a
        # generic clause (e.g. "Provider may suspend…") to the wrong customer.
        for e in doc_ev:
            owner = cust_map.get(e.document)
            if owner:
                e.extra["owner"] = owner
                e.content = f"(From {owner}'s agreement) {e.content}"
        evidence += doc_ev
        n_docs = len(doc_filter.get("documents", []))
        trace.notes.append(
            "Step 3 — document retrieval"
            + (f" (filtered to {n_docs} doc(s))" if n_docs else "")
            + f" selected {len(doc_ev)} passage(s)."
        )
        return evidence


def _on_topic(question: str, evidence: list[Evidence]) -> bool:
    """Deterministic relevance gate for the safety net: a top recovered passage must
    share at least one content word (non-stopword token) with the question. Keeps the
    'honest grounding' guarantee — genuinely out-of-scope questions whose corpus has no
    lexical overlap are still declined, even offline with no LLM to judge relevance.
    Checks the top 3 passages (not just #1) and matches Hebrew tokens prefix-tolerantly
    (ה/ו/ב/ל/מ/ש/כ), so multilingual recoveries aren't wrongly discarded."""
    terms = content_terms(question)
    if not terms:
        return True                            # nothing distinctive to gate on; trust generation
    for e in evidence[:3]:
        text = e.content or ""
        if any(term_in_text(t, text) for t in terms):
            return True
    return False


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
    if "live" in modes:
        return "live" if modes == {"live"} else "mixed"
    if modes == {"cached"}:
        return "cached"          # replay of a previously-generated live answer
    if "cached" in modes:
        return "cached"
    return "offline"             # deterministic fallbacks only
