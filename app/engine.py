"""Engine assembly — build the index and wire the sources + orchestrator once at startup,
then allow runtime ingestion of customer-uploaded PDFs and SQLite databases.

The engine is a process-wide singleton. Startup ingests only the deterministic sample
corpus (so it always boots clean). Uploads mutate the live engine under a lock:
PDF chunks are appended to the existing hybrid index, and uploaded SQLite tables are
merged into a working database the relational source is rebound to. The retrieval,
routing, SQL, and generation logic are untouched — only registration is added.
"""
from __future__ import annotations

import threading
import time
from functools import lru_cache
from pathlib import Path

from app.config import get_settings
from app.ingestion.pdf import ingest_pdf, ingest_pdf_dir
from app.ingestion.sqlite_introspect import SchemaInfo, introspect
from app.ingestion.sqlite_register import copy_seed, merge_sqlite
from app.models import (IngestedDatabaseInfo, IngestedDocumentInfo,
                        Inventory, SourceInfo, TableInfo)
from app.retrieval.document_retriever import DocumentIndex
from app.routing.orchestrator import Orchestrator
from app.sources.crm_source import CrmSource
from app.sources.document_source import DocumentSource
from app.sources.structured_source import StructuredSource


class Engine:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._lock = threading.RLock()
        self._build_from_seed()

    # -- assembly ----------------------------------------------------------
    def _build_from_seed(self) -> None:
        s = self.settings
        # documents (sample corpus)
        docs = ingest_pdf_dir(s.pdf_dir)
        chunks = [c.as_dict() for d in docs for c in d.chunks]
        index = DocumentIndex()
        index.build(chunks)
        doc_names = [d.document for d in docs]
        languages = sorted({d.language for d in docs})
        self.document_source = DocumentSource(index, doc_names, languages)

        # relational (sample database) — the relational source starts bound to the seed DB.
        self._seed_db_path: Path = s.db_path
        self._working_db_path: Path | None = None
        schema = introspect(s.db_path)
        self._seed_table_names: set[str] = set(schema.table_names())
        self.relational_source = StructuredSource(s.db_path, schema)

        # per-source inventory (sample data is pre-loaded)
        self._documents: list[IngestedDocumentInfo] = [
            _doc_info_from_ingested(ingest_pdf(p), origin="sample")
            for p in sorted(s.pdf_dir.glob("*.pdf"))
        ]
        self._databases: list[IngestedDatabaseInfo] = [
            _db_info_from_schema("business.db (sample)", schema, origin="sample")
        ]

        self._rebuild_orchestrator()

    def _rebuild_orchestrator(self) -> None:
        self.orchestrator = Orchestrator(self.document_source, self.relational_source)

    # -- runtime ingestion -------------------------------------------------
    def add_pdf(self, filename: str, path: Path) -> IngestedDocumentInfo:
        """Ingest, embed, and index an uploaded PDF, then make it queryable."""
        with self._lock:
            t0 = time.perf_counter()
            try:
                try:
                    doc = ingest_pdf(path)
                except Exception:
                    raise ValueError(
                        "Unable to process PDF — the file may be corrupt, encrypted, "
                        "or not a valid PDF."
                    )
                if not doc.chunks:
                    raise ValueError(
                        "No extractable text found in this PDF. It may be a scanned "
                        "image (OCR is not enabled in this environment)."
                    )
                chunk_dicts = [c.as_dict() for c in doc.chunks]
                added = self.document_source.index.add_chunks(chunk_dicts)
                if doc.document not in self.document_source.documents:
                    self.document_source.documents.append(doc.document)
                langs = sorted({c.language for c in doc.chunks}) or [doc.language]
                for lg in langs:
                    if lg not in self.document_source.languages:
                        self.document_source.languages.append(lg)
                self._rebuild_orchestrator()
                info = IngestedDocumentInfo(
                    name=doc.document, origin="uploaded", status="indexed",
                    chunks_indexed=added, languages=langs,
                    pages=doc.total_pages or max((c.page for c in doc.chunks), default=0),
                    ingestion_ms=round((time.perf_counter() - t0) * 1000, 1),
                    warning=_page_warning(doc),
                )
            except Exception as exc:  # never let a bad upload take down the engine
                info = IngestedDocumentInfo(
                    name=filename, origin="uploaded", status="error",
                    ingestion_ms=round((time.perf_counter() - t0) * 1000, 1),
                    error=str(exc),
                )
            self._documents = [d for d in self._documents if d.name != info.name] + [info]
            return info

    def add_database(self, filename: str, path: Path) -> IngestedDatabaseInfo:
        """Register an uploaded SQLite database with the router by merging its tables
        into a working database and rebinding the relational source."""
        with self._lock:
            t0 = time.perf_counter()
            try:
                if self._working_db_path is None:
                    self._working_db_path = self.settings.data_path / "uploads" / "working.db"
                    copy_seed(self._seed_db_path, self._working_db_path)
                try:
                    merged = merge_sqlite(path, self._working_db_path, source_label=filename)
                except Exception:
                    raise ValueError(
                        "Unable to read this SQLite database — the file may be corrupt or "
                        "use an unsupported format."
                    )
                if not merged:
                    raise ValueError(
                        "No tables found in this SQLite database — nothing to register."
                    )
                schema = introspect(self._working_db_path)
                self.relational_source = StructuredSource(self._working_db_path, schema)
                self._rebuild_orchestrator()

                cols_by_table = {t.name: [c.name for c in t.columns] for t in schema.tables}
                tables = [
                    TableInfo(
                        name=m.effective,
                        original_name=(m.original if m.original != m.effective else None),
                        rows=m.rows, columns=cols_by_table.get(m.effective, []),
                    )
                    for m in merged
                ]
                info = IngestedDatabaseInfo(
                    name=filename, origin="uploaded", status="indexed",
                    tables=tables, total_rows=sum(t.rows for t in tables),
                    ingestion_ms=round((time.perf_counter() - t0) * 1000, 1),
                )
            except Exception as exc:
                info = IngestedDatabaseInfo(
                    name=filename, origin="uploaded", status="error",
                    ingestion_ms=round((time.perf_counter() - t0) * 1000, 1),
                    error=str(exc),
                )
            self._databases = [d for d in self._databases if d.name != info.name] + [info]
            return info

    def reset(self) -> None:
        """Return the workspace to a clean sample state (drops all uploads)."""
        with self._lock:
            # best-effort cleanup of uploaded artifacts on disk
            up = self.settings.data_path / "uploads"
            try:
                import shutil
                if up.exists():
                    shutil.rmtree(up)
            except Exception:
                pass
            self._build_from_seed()

    # -- views -------------------------------------------------------------
    def inventory(self) -> Inventory:
        docs = list(self._documents)
        dbs = list(self._databases)
        return Inventory(
            documents=docs, databases=dbs,
            total_chunks=self.document_source.index.n_chunks,
            total_tables=sum(len(d.tables) for d in dbs),
        )

    @property
    def sources(self) -> list[SourceInfo]:
        return [
            self.document_source.describe(),
            self.relational_source.describe(),
            CrmSource().describe(),
        ]

    def ask(self, question: str, scope: str = "all",
            role_instructions: str | None = None):
        with self._lock:
            allowed_docs, allowed_tables = self._scope_sources(scope)
            if scope == "workspace" and not allowed_docs and not allowed_tables:
                return self._empty_workspace_response(question)
            resp = self.orchestrator.ask(
                question, allowed_docs=allowed_docs, allowed_tables=allowed_tables,
                role_instructions=role_instructions,
            )
            self._stamp_origin(resp.trace.evidence)
            return resp

    def _scope_sources(self, scope: str):
        """Resolve a scope to the document names + table names it may use.
        Returns (allowed_docs, allowed_tables); None means 'no restriction'."""
        if scope == "all":
            return None, None
        want_uploaded = scope == "workspace"
        docs = [d.name for d in self._documents
                if d.status == "indexed" and (d.origin == "uploaded") == want_uploaded]
        tables = [t for t in self.relational_source.schema.table_names()
                  if (t not in self._seed_table_names) == want_uploaded]
        return docs, tables

    def _empty_workspace_response(self, question: str):
        from app.models import AskResponse, RouteDecision, Trace
        msg = ("Your workspace is empty. Add a PDF or SQLite database under Sources to ask "
               "questions about your own data.")
        return AskResponse(
            question=question, answer=msg, insufficient=True, citations=[],
            trace=Trace(
                question=question,
                route=RouteDecision(route="NONE", reasoning="Empty workspace — no uploaded sources yet.",
                                    confidence=0.0),
                notes=["No sources in the workspace. Upload a PDF or database to begin."],
                mode="deterministic",
            ),
        )

    # -- provenance --------------------------------------------------------
    def _table_origin(self) -> dict[str, str]:
        return {
            t.name: ("sample" if t.name in self._seed_table_names else "uploaded")
            for t in self.relational_source.schema.tables
        }

    def _stamp_origin(self, evidence) -> None:
        """Tag every evidence item with its provenance (sample vs uploaded) so the client
        is never left wondering whether an answer came from their upload or bundled data.
        (trace.evidence and citations reference the same objects, so this covers both.)"""
        doc_origin = {d.name: d.origin for d in self._documents}
        tbl_origin = self._table_origin()
        for e in evidence:
            if e.source_kind == "documents" and e.document:
                e.origin = doc_origin.get(e.document)
            elif e.source_kind == "relational" and e.table:
                e.origin = tbl_origin.get(e.table)


# -- inventory helpers -------------------------------------------------------

def _page_warning(doc) -> str | None:
    """A non-fatal quality note when some pages yielded no text (likely scanned)."""
    if not doc.empty_pages or not doc.total_pages:
        return None
    return (f"{len(doc.empty_pages)} of {doc.total_pages} page(s) contained no "
            f"extractable text (possibly scanned images — OCR is not enabled). "
            f"Content on those pages will not be searchable.")


def _doc_info_from_ingested(doc, origin: str) -> IngestedDocumentInfo:
    langs = sorted({c.language for c in doc.chunks}) or [doc.language]
    return IngestedDocumentInfo(
        name=doc.document, origin=origin, status="indexed",
        chunks_indexed=len(doc.chunks), languages=langs,
        pages=doc.total_pages or max((c.page for c in doc.chunks), default=0),
        warning=_page_warning(doc),
    )


def _db_info_from_schema(name: str, schema: SchemaInfo, origin: str) -> IngestedDatabaseInfo:
    tables = [
        TableInfo(name=t.name, rows=t.row_count, columns=[c.name for c in t.columns])
        for t in schema.tables
    ]
    return IngestedDatabaseInfo(
        name=name, origin=origin, status="indexed",
        tables=tables, total_rows=sum(t.rows for t in tables),
    )


@lru_cache
def get_engine() -> Engine:
    return Engine()
