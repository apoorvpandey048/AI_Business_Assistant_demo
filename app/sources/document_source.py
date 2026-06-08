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
        return SourceInfo(
            name=self.name, kind="documents",
            title="Contracts & project documentation (PDF)",
            description=(
                "Unstructured business documents — master service agreements, service "
                "agreements, and project briefs."
            ),
            capabilities=[
                "contract clauses (penalties, service suspension, SLA, termination)",
                "project risks and mitigations",
                "anything stated in the text of a contract or brief",
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
