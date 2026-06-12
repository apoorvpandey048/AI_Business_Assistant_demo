"""API routes: /health, /config, /sources, /inventory, /ask, ingestion."""
from __future__ import annotations

import logging
import re
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.config import (clear_runtime_provider, get_settings, provider_override_state,
                        set_runtime_provider)
from app.engine import get_engine
from app.llm.providers import PROVIDER_CATALOG
from app.models import (AskRequest, AskResponse, IngestResult, Inventory,
                        ProviderOption, ProviderStatus, ProvidersResponse,
                        ProviderSwitchRequest, ProviderValidation, RouteDecision,
                        SourceInfo, Trace)

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


def _current_provider_status() -> ProviderStatus:
    """The live status of the *applied* provider, with the engine's real embedding backend
    and the informational deployment label stamped in. Shared by /config and /providers."""
    eng = get_engine()
    embedding_backend = eng.document_source.index.embedder.backend
    from app.llm.client import get_llm
    status = get_llm().provider_status()
    status.embedding_model = embedding_backend          # provider doesn't own embeddings
    status.deployment_mode = PROVIDER_CATALOG.get(status.provider, {}).get("deployment_mode", "")
    return status


def _provider_options() -> list[ProviderOption]:
    return [
        ProviderOption(name=name, label=meta["label"], transport=meta["transport"],
                       deployment_mode=meta["deployment_mode"], description=meta["description"])
        for name, meta in PROVIDER_CATALOG.items()
    ]


def _providers_response() -> ProvidersResponse:
    st = provider_override_state()
    return ProvidersResponse(
        applied=st["applied"], default=st["default"], source=st["source"],
        overridden=st["overridden"], status=_current_provider_status(),
        options=_provider_options(),
    )


@router.get("/config")
def config() -> dict:
    s = get_settings()
    eng = get_engine()
    embedding_backend = eng.document_source.index.embedder.backend

    # Live provider diagnostics (sprint §13, Task C). The embedding backend is the engine's
    # actual one (the provider doesn't own embeddings — they are decoupled), so we stamp it in.
    status = _current_provider_status()

    return {
        "mode": "live" if s.use_live_llm else "offline",
        "provider": s.resolved_provider,
        "models": {
            "generation": s.model_generation,
            "router": s.model_router,
            "sql": s.model_sql,
        },
        "embedding_backend": embedding_backend,
        "vector_backend": eng.document_source.index.store.backend,
        "reranker_backend": (
            eng.document_source.index.reranker.backend
            if eng.document_source.index.reranker else "disabled"
        ),
        "has_api_key": s.has_api_key,
        "provider_status": status.model_dump(),
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


# -- provider selection (sprint §14) -----------------------------------------

@router.get("/providers", response_model=ProvidersResponse)
def providers() -> ProvidersResponse:
    """The provider selector's full state: applied vs. server default, live status, options."""
    return _providers_response()


@router.post("/provider", response_model=ProvidersResponse)
def switch_provider(req: ProviderSwitchRequest) -> ProvidersResponse:
    """Switch the active inference provider at runtime (persisted, reload-safe).

    Only the LLM client is rebuilt — the engine, the hybrid index, the embeddings, and the
    uploaded workspace are provider-independent and are preserved across the switch."""
    from app.llm.client import reset_llm
    try:
        set_runtime_provider(req.provider)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception:
        log.exception("provider switch failed for %r", req.provider)
        raise HTTPException(500, "Could not switch provider. Please try again.")
    reset_llm()
    return _providers_response()


@router.post("/provider/default", response_model=ProvidersResponse)
def use_default_provider() -> ProvidersResponse:
    """Drop any UI override and revert to the server-configured (env/`ABA_PROVIDER`) default."""
    from app.llm.client import reset_llm
    clear_runtime_provider()
    reset_llm()
    return _providers_response()


@router.post("/provider/validate", response_model=ProviderValidation)
def validate_active_provider() -> ProviderValidation:
    """Validate the active provider end to end (health + routing + generation + embeddings).
    Never raises and never leaks a stack trace — failures come back as clean checks + fixes."""
    from app.llm.validate import validate_provider
    return validate_provider()
