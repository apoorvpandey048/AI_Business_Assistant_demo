"""API routes: /health, /config, /sources, /inventory, /ask, ingestion."""
from __future__ import annotations

import logging
import re
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.config import get_settings
from app.engine import get_engine
from app.models import (AskRequest, AskResponse, IngestResult,
                        Inventory, RouteDecision, SourceInfo, Trace)

router = APIRouter()
log = logging.getLogger("aba.api")

_MAX_PDF_BYTES = 30 * 1024 * 1024      # 30 MB per PDF
_MAX_DB_BYTES = 100 * 1024 * 1024      # 100 MB per SQLite file
_SAFE_NAME = re.compile(r"[^0-9A-Za-z._-]+")


def _safe_filename(name: str, fallback: str) -> str:
    base = Path(name or "").name
    base = _SAFE_NAME.sub("_", base).strip("._") or fallback
    return base


@router.get("/health")
def health() -> dict:
    eng = get_engine()
    return {
        "status": "ok",
        "documents": len(eng.document_source.documents),
        "chunks": eng.document_source.index.n_chunks,
        "tables": eng.relational_source.schema.table_names(),
    }


@router.get("/config")
def config() -> dict:
    s = get_settings()
    eng = get_engine()
    return {
        "mode": "live" if s.use_live_llm else "offline",
        "provider": s.llm_provider,
        "models": {
            "generation": s.model_generation,
            "router": s.model_router,
            "sql": s.model_sql,
        },
        "embedding_backend": eng.document_source.index.embedder.backend,
        "vector_backend": eng.document_source.index.store.backend,
        "reranker_backend": (
            eng.document_source.index.reranker.backend
            if eng.document_source.index.reranker else "disabled"
        ),
        "has_api_key": s.has_api_key,
    }


@router.get("/sources", response_model=list[SourceInfo])
def sources() -> list[SourceInfo]:
    return get_engine().sources


@router.get("/inventory", response_model=Inventory)
def inventory() -> Inventory:
    return get_engine().inventory()


@router.post("/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    question = (req.question or "").strip()
    if not question:
        raise HTTPException(400, "Please enter a question.")
    role = (req.role_instructions or "").strip() or None
    try:
        return get_engine().ask(question, scope=req.scope, role_instructions=role)
    except Exception:  # never leak a stack trace — fail gracefully and honestly
        log.exception("ask() failed for question=%r", question)
        return AskResponse(
            question=question,
            answer="We hit an unexpected error while processing this question. "
                   "Please try rephrasing it, or try again in a moment.",
            insufficient=True,
            citations=[],
            trace=Trace(
                question=question,
                route=RouteDecision(route="NONE", reasoning="Engine error.", confidence=0.0),
                notes=["The engine encountered an unexpected error; no answer was grounded."],
                mode="error",
            ),
        )


# -- ingestion ---------------------------------------------------------------

@router.post("/ingest/pdf", response_model=IngestResult)
async def ingest_pdf_endpoint(files: list[UploadFile] = File(...)) -> IngestResult:
    eng = get_engine()
    dest_dir = get_settings().data_path / "uploads" / "pdfs"
    dest_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for i, f in enumerate(files):
        name = _safe_filename(f.filename or "", f"upload_{i}.pdf")
        if not name.lower().endswith(".pdf"):
            name += ".pdf"
        data = await f.read()
        if len(data) > _MAX_PDF_BYTES:
            raise HTTPException(413, f"“{name}” exceeds the {_MAX_PDF_BYTES // (1024*1024)} MB per-file limit.")
        if not data:
            raise HTTPException(400, f"“{name}” is empty — nothing to ingest.")
        if data[:5] != b"%PDF-":
            raise HTTPException(400, f"“{name}” is not a valid PDF file.")
        dest = dest_dir / name
        dest.write_bytes(data)
        results.append(eng.add_pdf(name, dest))
    return IngestResult(
        ok=all(r.status == "indexed" for r in results),
        documents=results, inventory=eng.inventory(),
        message=f"Indexed {sum(r.chunks_indexed for r in results)} chunk(s) "
                f"from {len(results)} PDF(s).",
    )


@router.post("/ingest/sqlite", response_model=IngestResult)
async def ingest_sqlite_endpoint(files: list[UploadFile] = File(...)) -> IngestResult:
    eng = get_engine()
    dest_dir = get_settings().data_path / "uploads" / "db"
    dest_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for i, f in enumerate(files):
        name = _safe_filename(f.filename or "", f"upload_{i}.db")
        data = await f.read()
        if len(data) > _MAX_DB_BYTES:
            raise HTTPException(413, f"“{name}” exceeds the {_MAX_DB_BYTES // (1024*1024)} MB per-file limit.")
        if not data:
            raise HTTPException(400, f"“{name}” is empty — nothing to register.")
        if data[:16] != b"SQLite format 3\x00":
            raise HTTPException(400, f"Unsupported SQLite format — “{name}” is not a valid SQLite database.")
        dest = dest_dir / name
        dest.write_bytes(data)
        results.append(eng.add_database(name, dest))
    total_tables = sum(len(r.tables) for r in results)
    return IngestResult(
        ok=all(r.status == "indexed" for r in results),
        databases=results, inventory=eng.inventory(),
        message=f"Registered {total_tables} table(s) from {len(results)} database(s).",
    )


@router.post("/reset", response_model=Inventory)
def reset() -> Inventory:
    eng = get_engine()
    eng.reset()
    return eng.inventory()
