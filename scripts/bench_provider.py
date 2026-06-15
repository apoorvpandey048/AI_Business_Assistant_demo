"""Provider performance benchmark (sprint §13.9).

Measures — does NOT estimate — answer/routing/generation/SQL latency, embedding latency,
ingestion + indexing time, process memory, and GPU VRAM for whichever provider the
environment selects. Run once per provider with the provider env set:

    ABA_PROVIDER=openai  .venv/bin/python scripts/bench_provider.py --out data/eval/bench_openai.json
    ABA_PROVIDER=ollama  .venv/bin/python scripts/bench_provider.py --out data/eval/bench_ollama.json

Latency comes from the real engine trace (trace.timings + trace.llm_calls), so the numbers
are exactly what a user would experience. VRAM is sampled from nvidia-smi at peak.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from statistics import mean

os.environ.setdefault("ABA_REFERENCE_DATE", "2026-06-08")
os.environ.setdefault("ABA_LLM_CACHE_WRITE", "false")   # never pollute the demo cache
os.environ.setdefault("ABA_CACHE_FIRST", "false")        # force LIVE calls → real latency

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Representative set spanning every route + language + a conflict probe.
QUESTIONS = [
    ("sql",         "What is the total outstanding invoice amount per customer?"),
    ("sql",         "Which customers have overdue invoices?"),
    ("pdf",         "What do our contracts say about service suspension?"),
    ("pdf",         "What penalties are defined in the contracts?"),
    ("hybrid",      "What contracts expire in the next 90 days and what penalties are defined in those contracts?"),
    ("hybrid",      "Which customers have overdue invoices and what does the agreement say about service suspension?"),
    ("hybrid",      "Show all active projects and summarize the risks mentioned in their documentation."),
    ("hebrew",      "מה אומרים החוזים על השעיית שירות?"),
    ("hebrew",      "אילו לקוחות יש להם חשבוניות באיחור?"),
    ("unanswerable","What is our employee headcount in Berlin?"),
    ("unanswerable","What was the weather in Tel Aviv yesterday?"),
    ("keyword",     "Show contracts referencing SLA-2025."),
]


def gpu_mem_used_mib() -> float | None:
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,nounits,nounits"],
            text=True, timeout=8)
        vals = [float(x) for x in out.strip().splitlines()[1:] if x.strip()]
        return max(vals) if vals else None
    except Exception:
        return None


def rss_mib() -> float:
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return round(int(line.split()[1]) / 1024, 1)
    except Exception:
        pass
    return -1.0


def pct(xs: list[float], p: float) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    k = max(0, min(len(s) - 1, int(round((p / 100) * (len(s) - 1)))))
    return round(s[k], 1)


def call_ms(trace, needle: str) -> float:
    return round(sum(c.duration_ms for c in trace.llm_calls if needle in c.purpose), 1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    from app.config import get_settings
    from app.engine import Engine

    get_settings.cache_clear()
    s = get_settings()

    # -- ingestion + indexing time (cold engine build over the sample corpus) ----
    t0 = time.perf_counter()
    eng = Engine()
    build_ms = round((time.perf_counter() - t0) * 1000, 1)

    mode = "live" if s.use_live_llm else "offline"
    embed_backend = eng.document_source.index.embedder.backend

    # -- embedding latency (single query embed, averaged) ------------------------
    embed_samples = []
    for q in ["overdue invoices", "service suspension penalty", "מה אומרים החוזים"]:
        te = time.perf_counter()
        eng.document_source.index.embedder.embed_one(q + " " + str(te))  # uncached
        embed_samples.append(round((time.perf_counter() - te) * 1000, 1))

    # -- per-question latency ----------------------------------------------------
    rows = []
    vram_peak = gpu_mem_used_mib() or 0.0
    for kind, q in QUESTIONS:
        t = time.perf_counter()
        # Resilient at the EVAL layer (not engine logic): a weak local model can emit
        # schema-violating JSON that raises downstream. Record it as an error and continue
        # so one bad model response never aborts the measurement run.
        try:
            resp = eng.ask(q, scope="all")
            total_ms = round((time.perf_counter() - t) * 1000, 1)
            tr = resp.trace
            row = {
                "kind": kind, "q": q,
                "route": tr.route.route if tr.route else "?",
                "mode": (tr.llm_calls[0].mode if tr.llm_calls else "n/a"),
                "total_ms": total_ms,
                "routing_ms": call_ms(tr, "routing"),
                "sql_ms": call_ms(tr, "sql"),
                "generation_ms": call_ms(tr, "generation"),
                "n_llm_calls": len(tr.llm_calls),
                "insufficient": resp.insufficient, "error": None,
            }
            print(f"  [{kind:12}] {row['route']:6} total={total_ms:8.1f}ms "
                  f"route={row['routing_ms']:7.1f} gen={row['generation_ms']:8.1f} mode={row['mode']}")
        except Exception as exc:
            total_ms = round((time.perf_counter() - t) * 1000, 1)
            row = {"kind": kind, "q": q, "route": "ERROR", "mode": "error",
                   "total_ms": total_ms, "routing_ms": 0.0, "sql_ms": 0.0,
                   "generation_ms": 0.0, "n_llm_calls": 0, "insufficient": None,
                   "error": f"{type(exc).__name__}: {exc}"}
            print(f"  [{kind:12}] ERROR after {total_ms:.1f}ms: {type(exc).__name__}: {str(exc)[:80]}")
        rows.append(row)

    ok_rows = [r for r in rows if r["error"] is None]
    errs = [r for r in rows if r["error"] is not None]
    totals = [r["total_ms"] for r in ok_rows] or [0.0]
    gens = [r["generation_ms"] for r in ok_rows if r["generation_ms"] > 0]
    routs = [r["routing_ms"] for r in ok_rows if r["routing_ms"] > 0]
    result = {
        "provider": s.resolved_provider,
        "generation_model": s.model_generation,
        "router_model": s.model_router,
        "embedding_backend": embed_backend,
        "mode": mode,
        "n_questions": len(rows),
        "n_ok": len(ok_rows),
        "n_errors": len(errs),
        "errors": [{"q": r["q"], "error": r["error"]} for r in errs],
        "ingestion_build_ms": build_ms,
        "embedding_ms_avg": round(mean(embed_samples), 1),
        "embedding_ms_samples": embed_samples,
        "latency": {
            "avg_total_ms": round(mean(totals), 1),
            "p50_total_ms": pct(totals, 50),
            "p95_total_ms": pct(totals, 95),
            "max_total_ms": round(max(totals), 1),
            "avg_routing_ms": round(mean(routs), 1) if routs else 0.0,
            "avg_generation_ms": round(mean(gens), 1) if gens else 0.0,
        },
        "vram_peak_mib": round(vram_peak, 1),
        "process_rss_mib": rss_mib(),
        "rows": rows,
    }
    print("\n" + json.dumps({k: v for k, v in result.items() if k != "rows"}, indent=2))
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(result, indent=2), "utf-8")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
