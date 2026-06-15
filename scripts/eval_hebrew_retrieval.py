"""Sprint 15 — Phase 3: multilingual retrieval measurement harness.

Measures recall@k of each available embedding backend on the Hebrew + cross-language
eval set (data/eval/hebrew_retrieval.jsonl), against the real PDF corpus ingested into
an ISOLATED index (no sidecars, no production data touched).

For each backend we:
  1. ingest the labelled docs → chunks (real ingestion, post Phase-2 fixes),
  2. embed all chunks + each query with that backend,
  3. cosine-rank chunks, check whether a chunk containing the gold substring appears
     in the top-k.

Recall@k is reported per language bucket (he / en / cross-language) and overall.
Backends with missing deps (sentence-transformers) or missing key (OpenAI) are skipped
with a printed note — never a silent omission.

Run:
  PYTHONPATH=. .venv/bin/python scripts/eval_hebrew_retrieval.py
  PYTHONPATH=. .venv/bin/python scripts/eval_hebrew_retrieval.py --k 5
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np


def _norm_ws(s: str) -> str:
    """Collapse whitespace so a gold substring matches regardless of pypdf's double
    spaces / newline padding."""
    return re.sub(r"\s+", " ", s or "")


def _gold_hit(chunk_text: str, gold: str) -> bool:
    return _norm_ws(gold) in _norm_ws(chunk_text)

from app.config import get_settings
from app.ingestion.pdf import ingest_pdf
from app.llm.embeddings import (
    _HashingEmbedder,
    _OpenAIEmbedder,
    _SentenceTransformerEmbedder,
)

EVAL = Path("data/eval/hebrew_retrieval.jsonl")
PDF_DIR = Path("data/uploads/pdfs")
LOCAL_MODELS = ["intfloat/multilingual-e5-large", "BAAI/bge-m3"]


def _load_eval() -> list[dict]:
    return [json.loads(l) for l in EVAL.read_text("utf-8").splitlines() if l.strip()]


def _corpus(docs: list[str]) -> list[dict]:
    chunks: list[dict] = []
    for name in docs:
        doc = ingest_pdf(PDF_DIR / name)
        for c in doc.chunks:
            chunks.append({"doc": name, "chunk_id": c.chunk_id, "text": c.text})
    return chunks


def _make_backends() -> list:
    s = get_settings()
    out = []
    # hashing — always available (the production baseline today)
    out.append(("hashing", _HashingEmbedder()))
    # OpenAI — only if key present
    if s.openai_key:
        try:
            out.append(("openai:" + s.openai_embed_model, _OpenAIEmbedder(s)))
        except Exception as e:  # pragma: no cover
            print(f"  [skip] OpenAI backend unavailable: {e}", file=sys.stderr)
    else:
        print("  [skip] OpenAI backend: no key", file=sys.stderr)
    # local multilingual — only if sentence-transformers importable
    for model in LOCAL_MODELS:
        try:
            out.append(("local:" + model, _SentenceTransformerEmbedder(model, "cpu")))
        except Exception as e:
            print(f"  [skip] local '{model}': {e}", file=sys.stderr)
    return out


def _recall(backend, chunks: list[dict], evals: list[dict], k: int) -> dict:
    texts = [c["text"] for c in chunks]
    mat = backend.encode(texts)  # (N, d), L2-normalized
    buckets: dict[str, list[bool]] = {}
    rows = []
    for ex in evals:
        # restrict candidate chunks to the target doc (recall of the right passage)
        idxs = [i for i, c in enumerate(chunks) if c["doc"] == ex["doc"]]
        q = backend.encode([ex["query"]])[0]
        sims = mat[idxs] @ q
        order = np.argsort(-sims)[:k]
        topk = [chunks[idxs[j]] for j in order]
        hit = any(_gold_hit(c["text"], ex["gold_substr"]) for c in topk)
        buckets.setdefault(ex["lang"], []).append(hit)
        rows.append((ex["id"], ex["lang"], hit))
    return {"rows": rows, "buckets": buckets}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=5)
    args = ap.parse_args()

    evals = _load_eval()
    docs = sorted({ex["doc"] for ex in evals})
    chunks = _corpus(docs)
    print(f"corpus: {len(chunks)} chunks from {docs}")
    print(f"eval: {len(evals)} queries, k={args.k}\n")

    backends = _make_backends()
    summary = {}
    for name, be in backends:
        try:
            res = _recall(be, chunks, evals, args.k)
        except Exception as e:
            print(f"=== {name} ===\n   [error] backend failed at runtime: {e}\n",
                  file=sys.stderr)
            summary[name] = ({}, f"ERROR: {type(e).__name__}")
            continue
        line = {}
        allhits = []
        for lang, hits in sorted(res["buckets"].items()):
            line[lang] = f"{sum(hits)}/{len(hits)}"
            allhits += hits
        overall = f"{sum(allhits)}/{len(allhits)} ({100*sum(allhits)/len(allhits):.0f}%)"
        summary[name] = (line, overall)
        print(f"=== {name} ===")
        for lang, frac in line.items():
            print(f"   {lang:10} {frac}")
        print(f"   {'OVERALL':10} {overall}")
        # show misses
        misses = [r for r in res["rows"] if not r[2]]
        if misses:
            print("   misses:", ", ".join(m[0] for m in misses))
        print()

    print("=" * 60)
    print(f"{'backend':40} overall recall@{args.k}")
    for name, (_, overall) in summary.items():
        print(f"{name:40} {overall}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
