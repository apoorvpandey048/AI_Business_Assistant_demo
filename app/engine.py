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
import logging
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

logger = logging.getLogger("aba.engine")

# Stable per-row key for entity indexing — prefers a human-meaningful reference column,
# falls back to the table's surrogate id. Mirrors structured_source._row_key intent.
_ROW_KEY_COLS = ("invoice_ref", "contract_ref", "project_ref", "sla_ref", "name",
                 "customer", "title")


def _row_key_for(row: dict) -> str:
    for c in _ROW_KEY_COLS:
        if row.get(c) is not None:
            return str(row[c])
    return str(row.get("id", "?"))


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

        # Cross-source entity graph: feed the DB rows + document-owner links into the
        # document index so structured (CRM) facts and cross-source identities
        # participate in entity / graph retrieval (Zero-Loss Phase 3).
        self._index_relational_into_graph(index, self.relational_source)

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

    def _index_relational_into_graph(self, index, relational) -> None:
        """Feed every row of the relational source into the document index's entity
        index + knowledge graph, plus a document→owner map from rows that reference a
        file. This is what brings the SQLite 'CRM' under the same no-loss guarantee:
        DB-only facts become entities, and an entity present in BOTH a PDF and a row
        becomes a cross-source bridge. Best-effort and fully offline — any failure
        leaves document-only retrieval working unchanged."""
        if not getattr(index.s, "enable_entity_graph", False):
            return
        try:
            import sqlite3

            owner_map: dict[str, str] = {}
            conn = sqlite3.connect(relational.db_path)
            conn.row_factory = sqlite3.Row
            try:
                for table in relational.schema.table_names():
                    try:
                        rows = [dict(r) for r in conn.execute(f"SELECT * FROM {table}")]
                    except Exception:
                        continue
                    if not rows:
                        continue
                    index.index_rows(table, rows, key_for=_row_key_for)
                    for r in rows:
                        doc = r.get("pdf_file") or r.get("doc_file")
                        owner = r.get("name") or r.get("customer") or r.get("title")
                        if doc and owner:
                            owner_map.setdefault(str(doc), str(owner))
            finally:
                conn.close()
            index.set_owner_map(owner_map)
            index.refresh_graph()
        except Exception:
            logger.warning("entity-graph relational indexing skipped", exc_info=True)

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
                # Bring the newly-merged rows under the cross-source entity graph.
                self._index_relational_into_graph(
                    self.document_source.index, self.relational_source)
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
        """The client-facing source list (Settings → Connected sources).

        Built from the live workspace inventory — only what the user actually
        uploaded counts as connected; the bundled sample corpus is an evaluation
        artifact and must never display as a connected source. The router keeps
        using each source object's full ``describe()`` internally; this changes
        only what the client sees.
        """
        with self._lock:
            docs = [d for d in self._documents
                    if d.origin == "uploaded" and d.status == "indexed"]
            dbs = [d for d in self._databases
                   if d.origin == "uploaded" and d.status == "indexed"]
            return [
                _workspace_documents_info(docs),
                _workspace_database_info(dbs),
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


# -- client-facing source descriptions ---------------------------------------

def _workspace_documents_info(docs: list[IngestedDocumentInfo]) -> SourceInfo:
    names = [d.name for d in docs]
    shown = ", ".join(names[:12]) + (" …" if len(names) > 12 else "")
    if docs:
        description = (
            f"{len(docs)} uploaded document(s) whose full text is searchable: {shown}."
        )
    else:
        description = ("No documents uploaded yet. Add PDFs under Sources to make "
                       "their full text searchable.")
    languages = sorted({lg for d in docs for lg in d.languages})
    return SourceInfo(
        name="documents", kind="documents",
        title="Documents (PDF)",
        description=description,
        capabilities=[
            "full-text search across every uploaded PDF — names, dates, amounts, "
            "clauses, and narrative content",
            f"documents: {shown or 'none'}",
        ],
        status="active" if docs else "empty",
        details={
            "documents": names,
            "languages": languages,
            "chunks": sum(d.chunks_indexed for d in docs),
        },
    )


def _workspace_database_info(dbs: list[IngestedDatabaseInfo]) -> SourceInfo:
    tables = [t for d in dbs for t in d.tables]
    if dbs:
        table_lines = []
        for t in tables[:12]:
            cols = ", ".join(t.columns[:8]) + ("" if len(t.columns) <= 8 else ", …")
            table_lines.append(f"{t.name}({cols})")
        summary = "; ".join(table_lines) + (" …" if len(tables) > 12 else "")
        description = (
            f"{len(dbs)} uploaded database(s) with {len(tables)} registered "
            f"table(s): {summary}."
        )
    else:
        description = ("No database uploaded yet. Add a SQLite file under Sources "
                       "to query its tables.")
    return SourceInfo(
        name="database", kind="relational",
        title="Database (SQLite)",
        description=description,
        capabilities=[
            "counts, sums, averages, filters, ranking and aggregation over the "
            "registered tables",
            f"available tables: {', '.join(t.name for t in tables) or 'none'}",
        ],
        status="active" if dbs else "empty",
        details={
            "databases": [d.name for d in dbs],
            "tables": [t.name for t in tables],
            "total_rows": sum(d.total_rows for d in dbs),
        },
    )


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
