"""FastAPI application entrypoint."""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

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


# --- error handling: clients never see a stack trace, only a clean message ---
@app.exception_handler(StarletteHTTPException)
async def _http_exc(request: Request, exc: StarletteHTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(RequestValidationError)
async def _validation_exc(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=400, content={"detail": "The request was malformed."})


@app.exception_handler(Exception)
async def _unhandled_exc(request: Request, exc: Exception):
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Something went wrong on our side. Please try again."},
    )


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
