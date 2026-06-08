"""API routes: /health, /config, /examples, /sources, /ask."""
from __future__ import annotations

from fastapi import APIRouter

from app.config import get_settings
from app.engine import get_engine
from app.models import AskRequest, AskResponse, ExampleQuestion, SourceInfo

router = APIRouter()


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


@router.get("/examples", response_model=list[ExampleQuestion])
def examples() -> list[ExampleQuestion]:
    return get_engine().examples


@router.get("/sources", response_model=list[SourceInfo])
def sources() -> list[SourceInfo]:
    return get_engine().sources


@router.post("/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    return get_engine().ask(req.question)
