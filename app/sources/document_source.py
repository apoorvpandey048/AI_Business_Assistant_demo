"""Document (PDF) source — wraps the hybrid DocumentIndex behind the Source interface."""
from __future__ import annotations

from typing import Any, Optional

from app.models import DocumentRetrievalTrace, Evidence, SourceInfo
from app.retrieval.document_retriever import DocumentIndex


class DocumentSource:
    name = "contracts_pdf"
    kind = "documents"

    def __init__(self, index: DocumentIndex, documents: list[str], languages: list[str]) -> None:
        self.index = index
        self.documents = documents
        self.languages = languages

    def describe(self) -> SourceInfo:
        # Data-driven description so the router knows which documents (sample + any
        # uploaded PDFs) are actually searchable right now.
        docs = self.documents
        shown = ", ".join(docs[:12]) + (" …" if len(docs) > 12 else "")
        description = (
            f"Unstructured documents (PDF) — {len(docs)} file(s) whose full text is searchable"
            + (f": {shown}." if docs else ".")
        )
        return SourceInfo(
            name=self.name, kind="documents",
            title="Documents (PDF)",
            description=description,
            capabilities=[
                "ANY information stated anywhere in the text or metadata of these PDFs — "
                "names, parties, authors, recipients, signatories, dates, amounts, "
                "valuations, emails, phone numbers, contact details, organizations, "
                "universities, clauses, penalties, suspension, SLA, termination, "
                "definitions, risks, summaries, findings, and narrative content",
                "qualitative / unstructured details that are not in the database",
                f"documents: {shown or 'none'}",
            ],
            status="active",
            details={
                "documents": self.documents,
                "languages": self.languages,
                "chunks": self.index.n_chunks,
                "embedding_backend": self.index.embedder.backend,
            },
        )

    def retrieve(
        self, query: str, filters: Optional[dict[str, Any]] = None, k: Optional[int] = None
    ) -> tuple[list[Evidence], DocumentRetrievalTrace]:
        return self.index.retrieve(query, filters=filters, final_k=k)
