"""Engine assembly — build the index and wire the sources + orchestrator once at startup."""
from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.ingestion.pdf import ingest_pdf_dir
from app.ingestion.sqlite_introspect import introspect
from app.models import ExampleQuestion, SourceInfo
from app.retrieval.document_retriever import DocumentIndex
from app.routing.orchestrator import Orchestrator
from app.sources.crm_source import CrmSource
from app.sources.document_source import DocumentSource
from app.sources.relational_source import RelationalSource

EXAMPLES = [
    ExampleQuestion(
        label="Pure SQL", route="SQL", language="en",
        question="What is the total outstanding invoice amount per customer?",
        why="Aggregation over the database; clean generated SQL with table/row citations."),
    ExampleQuestion(
        label="Pure document", route="PDF", language="en",
        question="What do our contracts say about service suspension?",
        why="Hybrid retrieval (dense + BM25) over the PDFs with page-level citations."),
    ExampleQuestion(
        label="Keyword beats vector", route="PDF", language="en",
        question="Which contract clauses mention SLA-2025?",
        why="BM25 finds the exact identifier 'SLA-2025' that pure embeddings miss."),
    ExampleQuestion(
        label="Hybrid (agentic)", route="HYBRID", language="en",
        question="Which customers have overdue invoices, and what do their agreements say about service suspension?",
        why="SQL finds overdue customers → those customers' contracts are retrieved → grounded combined answer. The flagship."),
    ExampleQuestion(
        label="Hybrid (date + clause)", route="HYBRID", language="en",
        question="What contracts expire in the next 90 days, and what penalties do they define?",
        why="Date filter in SQL + penalty clauses from the documents — impossible with vector search alone."),
    ExampleQuestion(
        label="Hybrid (projects + risks)", route="HYBRID", language="en",
        question="Show all active projects and summarize the risks in their documentation.",
        why="SQL lists active projects; project briefs supply the risk narrative, grouped per project."),
    ExampleQuestion(
        label="Hebrew", route="PDF", language="he",
        question="מה אומר ההסכם של תבור מערכות על השעיית שירות וקנסות?",
        why="Bilingual retrieval over a Hebrew contract with right-to-left citations."),
    ExampleQuestion(
        label="Honest grounding", route="NONE", language="en",
        question="What is our employee headcount in Berlin?",
        why="No source can answer → the system says 'insufficient evidence' instead of guessing."),
]


class Engine:
    def __init__(self) -> None:
        s = get_settings()
        # documents
        docs = ingest_pdf_dir(s.pdf_dir)
        chunks = [c.as_dict() for d in docs for c in d.chunks]
        index = DocumentIndex()
        index.build(chunks)
        doc_names = [d.document for d in docs]
        languages = sorted({d.language for d in docs})
        self.document_source = DocumentSource(index, doc_names, languages)
        # relational
        schema = introspect(s.db_path)
        self.relational_source = RelationalSource(s.db_path, schema)
        # orchestrator + source registry (incl. future CRM stub)
        self.orchestrator = Orchestrator(self.document_source, self.relational_source)
        self.sources: list[SourceInfo] = [
            self.document_source.describe(),
            self.relational_source.describe(),
            CrmSource().describe(),
        ]
        self.examples = EXAMPLES
        self.settings = s

    def ask(self, question: str):
        return self.orchestrator.ask(question)


@lru_cache
def get_engine() -> Engine:
    return Engine()
