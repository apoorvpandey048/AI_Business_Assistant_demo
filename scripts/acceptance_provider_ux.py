"""Provider UX acceptance harness (sprint §14, Workstreams 5/8/9).

Drives the REAL API route handlers in-process (no uvicorn — the repo lives on a slow
Windows mount where server startup buffers) against the configured live provider, proving
the productized provider workflow end to end:

  A. list providers → validate the active provider live → ask a cited answer
  B. upload a PDF + SQLite, then SWITCH provider — assert the workspace is preserved
  C. switch to a DOWN provider → validation surfaces actionable diagnostics (no crash);
     the engine keeps answering via the deterministic offline fallback
  D. revert to the server default → validation healthy again

Run (live, with a configured key):
    ABA_EMBEDDING_BACKEND=hashing ABA_ENABLE_RERANK=false ABA_REFERENCE_DATE=2026-06-08 \
        .venv/bin/python scripts/acceptance_provider_ux.py
"""
from __future__ import annotations

import shutil
from pathlib import Path

from app import config as C
from app.config import ROOT, get_settings
from app.llm.client import reset_llm

# the real route handlers — exercise the actual HTTP contract
from app.api import routes
from app.models import AskRequest, ProviderSwitchRequest


def hr(title: str) -> None:
    print("\n" + "=" * 78 + f"\n{title}\n" + "=" * 78)


def show_validation(v) -> None:
    print(f"  → ok={v.ok} | {v.summary}")
    for c in v.checks:
        fix = f"  [fix: {c.fix}]" if c.fix else ""
        print(f"     {c.name:11s} {c.status:8s} {c.detail[:78]}{fix}")


def main() -> None:
    C.clear_runtime_provider()
    reset_llm()
    eng = routes.get_engine()
    s = get_settings()
    print(f"Configured provider (env default): {s.resolved_provider} | live={s.use_live_llm} "
          f"| gen={s.model_generation}")

    # -- A. discover + validate + ask -------------------------------------
    hr("A · Discover providers, validate the active provider (LIVE), ask a cited answer")
    pr = routes.providers()
    print(f"applied={pr.applied} default={pr.default} source={pr.source} "
          f"options={[o.name for o in pr.options]}")
    print(f"deployment labels: " +
          ", ".join(f"{o.name}={o.deployment_mode}" for o in pr.options))
    print(f"status: health={pr.status.health} connection={pr.status.connection} "
          f"model={pr.status.generation_model} embed={pr.status.embedding_model}")

    print("\nrunning live validation…")
    v = routes.validate_active_provider()
    show_validation(v)

    print("\nasking a SQL-routed question (scope=all over the sample tables):")
    q = "What is the total amount of all invoices in the database?"
    resp = routes.ask(AskRequest(question=q, scope="all"))
    print(f"  Q: {q}")
    print(f"  route={resp.trace.route.route if resp.trace.route else '?'} "
          f"mode={resp.trace.mode} insufficient={resp.insufficient} "
          f"citations={len(resp.citations)}")
    print(f"  A: {resp.answer[:300]}")
    live_calls = [lc for lc in resp.trace.llm_calls if lc.mode == 'live']
    print(f"  live LLM calls in this answer: {len(live_calls)} "
          f"({', '.join(sorted({lc.model for lc in live_calls})) or 'none'})")

    # -- B. workspace preservation across a switch ------------------------
    hr("B · Upload PDF + SQLite, then SWITCH provider — workspace must be preserved")
    up = Path(get_settings().data_path) / "uploads"
    pdf_src = sorted((ROOT / "data" / "pdfs").glob("*.pdf"))[0]
    pdf_dest = up / "pdfs" / "Jenny_Contract.pdf"
    pdf_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(pdf_src, pdf_dest)
    db_dest = up / "db" / "jenny_books.db"
    db_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(ROOT / "data" / "business.db", db_dest)
    di = eng.add_pdf("Jenny_Contract.pdf", pdf_dest)
    dbi = eng.add_database("jenny_books.db", db_dest)
    inv0 = eng.inventory()
    print(f"uploaded: pdf chunks={di.chunks_indexed} | db tables={len(dbi.tables)}")
    print(f"inventory before switch: docs={[d.name for d in inv0.documents if d.origin=='uploaded']} "
          f"dbs={[d.name for d in inv0.databases if d.origin=='uploaded']} chunks={inv0.total_chunks}")
    sources0 = {x.name: x.status for x in eng.sources}

    print("\nswitching provider → ollama (via POST /provider)…")
    pr2 = routes.switch_provider(ProviderSwitchRequest(provider="ollama"))
    print(f"applied={pr2.applied} source={pr2.source} overridden={pr2.overridden} "
          f"model={pr2.status.generation_model}")
    assert get_settings().resolved_provider == "ollama"

    inv1 = eng.inventory()
    sources1 = {x.name: x.status for x in eng.sources}
    preserved = (
        inv1.total_chunks == inv0.total_chunks
        and [d.name for d in inv1.documents] == [d.name for d in inv0.documents]
        and [d.name for d in inv1.databases] == [d.name for d in inv0.databases]
        and sources1 == sources0
    )
    print(f"inventory after switch:  chunks={inv1.total_chunks} | sources={sources1}")
    print(f"WORKSPACE PRESERVED ACROSS SWITCH: {preserved}")
    assert preserved, "workspace changed across a provider switch!"

    # -- C. down-provider diagnostics + graceful answer -------------------
    hr("C · Provider DOWN (ollama not running) — actionable diagnostics, no crash")
    v2 = routes.validate_active_provider()
    show_validation(v2)
    print("\nasking under the down provider (must still answer via offline fallback):")
    resp2 = routes.ask(AskRequest(question="How many invoices are overdue?", scope="all"))
    print(f"  route={resp2.trace.route.route if resp2.trace.route else '?'} "
          f"mode={resp2.trace.mode} answer={resp2.answer[:140]!r}")
    print(f"  ENGINE STILL ANSWERED (no crash): {bool(resp2.answer)}")

    # -- D. revert to default ---------------------------------------------
    hr("D · Revert to the server default (POST /provider/default)")
    pr3 = routes.use_default_provider()
    print(f"applied={pr3.applied} source={pr3.source} overridden={pr3.overridden}")
    v3 = routes.validate_active_provider()
    show_validation(v3)

    # cleanup: leave no override + drop the test uploads
    C.clear_runtime_provider()
    reset_llm()
    eng.reset()
    print("\n" + "=" * 78 + "\nACCEPTANCE COMPLETE — override cleared, workspace reset.\n" + "=" * 78)


if __name__ == "__main__":
    main()
