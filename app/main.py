"""FastAPI application entrypoint."""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.engine import get_engine

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("aba")

app = FastAPI(
    title="AI Business Knowledge Assistant",
    description="Multi-source retrieval & orchestration engine (PDF + SQLite) with "
                "query routing, hybrid retrieval, grounded generation, and full traceability.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.on_event("startup")
def _warm() -> None:
    eng = get_engine()
    log.info(
        "Engine ready: %d documents, %d chunks, tables=%s, embeddings=%s",
        len(eng.document_source.documents),
        eng.document_source.index.n_chunks,
        eng.relational_source.schema.table_names(),
        eng.document_source.index.embedder.backend,
    )


@app.get("/")
def root() -> dict:
    return {"service": "ai-business-knowledge-assistant", "docs": "/docs", "health": "/health"}
