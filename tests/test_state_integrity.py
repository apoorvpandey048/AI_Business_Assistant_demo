"""Regression tests — UX state integrity over long sessions (plan §12, WS6).

The UI promises the user that what they see is what is actually active:
- the source list (`engine.sources` → Settings → Connected sources) reflects the live
  workspace inventory — the bundled sample corpus NEVER displays as connected;
- the persona is per-request and stateless server-side — no stale persona can leak
  from one question to the next;
- workspace-scoped answers draw evidence only from uploads — never stale sample data;
- reset returns every UI-facing view (inventory, sources, scope) to the fresh state,
  and repeated upload→reset cycles do not leak state across cycles.

Run:  .venv/bin/python -m pytest tests/test_state_integrity.py -q
"""
from __future__ import annotations

import shutil

import pytest

from app.config import ROOT


@pytest.fixture()
def workspace_engine(tmp_path, monkeypatch):
    """A fresh engine over an isolated copy of the seed corpus, so uploads and
    reset() touch only this test's directory — never the repo's data/uploads."""
    from app.config import get_settings

    data = tmp_path / "data"
    (data / "pdfs").mkdir(parents=True)
    for p in sorted((ROOT / "data" / "pdfs").glob("*.pdf")):
        shutil.copy(p, data / "pdfs" / p.name)
    shutil.copy(ROOT / "data" / "business.db", data / "business.db")

    monkeypatch.setenv("ABA_DATA_DIR", str(data))
    get_settings.cache_clear()
    from app.engine import Engine
    eng = Engine()
    yield eng, data
    get_settings.cache_clear()  # let later tests rebuild settings from the real env


def _statuses(eng) -> dict[str, str]:
    return {s.name: s.status for s in eng.sources}


def _upload_pdf(eng, data, name="Uploaded_Client_Brief.pdf"):
    src = sorted((ROOT / "data" / "pdfs").glob("*.pdf"))[0]
    dest = data / "uploads" / "pdfs" / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(src, dest)
    return eng.add_pdf(name, dest)


def _upload_db(eng, data, name="customer_upload.db"):
    dest = data / "uploads" / "db" / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(ROOT / "data" / "business.db", dest)
    return eng.add_database(name, dest)


# --- the source list reflects the actual workspace --------------------------------

def test_fresh_workspace_shows_no_connected_sources(workspace_engine):
    eng, _ = workspace_engine
    assert _statuses(eng) == {"documents": "empty", "database": "empty", "crm": "future"}
    docs = next(s for s in eng.sources if s.name == "documents")
    db = next(s for s in eng.sources if s.name == "database")
    # empty states must guide, not just report
    assert "Add PDFs under Sources" in docs.description
    assert "Add a SQLite file under Sources" in db.description
    assert docs.details["documents"] == [] and db.details["tables"] == []


def test_sample_corpus_never_appears_in_source_list(workspace_engine):
    eng, data = workspace_engine
    _upload_pdf(eng, data)
    blob = " ".join(s.model_dump_json() for s in eng.sources)
    for sample in ("ACME_MSA_2025", "GLOBEX", "PRJ_ATLAS", "business.db (sample)"):
        assert sample not in blob, f"sample inventory leaked into /sources: {sample}"


def test_uploads_connect_and_describe_real_content(workspace_engine):
    eng, data = workspace_engine
    info = _upload_pdf(eng, data)
    assert info.status == "indexed"
    docs = next(s for s in eng.sources if s.name == "documents")
    assert docs.status == "active"
    assert "Uploaded_Client_Brief.pdf" in docs.description
    assert next(s for s in eng.sources if s.name == "database").status == "empty"

    db_info = _upload_db(eng, data)
    assert db_info.status == "indexed" and db_info.tables
    db = next(s for s in eng.sources if s.name == "database")
    assert db.status == "active"
    assert "customer_upload.db" in db.details["databases"]


# --- long session: 50+ questions, persona churn, uploads, reset -------------------

def test_long_session_no_stale_state(workspace_engine):
    eng, data = workspace_engine

    # empty workspace declines honestly
    r = eng.ask("What is the penalty clause?", scope="workspace")
    assert r.insufficient and r.trace.route.route == "NONE"

    _upload_pdf(eng, data)

    personas = [None, "Act as a lawyer reviewing these contracts",
                "Analyze as a compliance officer", None,
                "You are a financial auditor"]
    questions = [
        "What is the termination clause?",
        "What penalties apply for late delivery?",
        "Who are the parties to the agreement?",
        "What is the payment schedule?",
        "Summarize the service level commitments.",
    ]
    for i in range(52):
        role = personas[i % len(personas)]
        q = questions[i % len(questions)]
        resp = eng.ask(q, scope="workspace", role_instructions=role)
        # persona is per-request — the trace must reflect THIS request's role, so a
        # role from question N can never silently apply to question N+1
        if resp.trace.generation:
            assert bool(resp.trace.generation.get("role_applied")) == bool(role), \
                f"stale persona at question {i}: sent {role!r}"
        # workspace scope must never surface stale sample evidence
        for e in resp.trace.evidence:
            assert e.origin == "uploaded", \
                f"sample evidence leaked into workspace answer at question {i}: {e.id}"

    # add a database mid-session — the source list updates immediately
    _upload_db(eng, data)
    assert _statuses(eng)["database"] == "active"

    # reset returns every UI-facing view to the fresh state
    eng.reset()
    assert _statuses(eng) == {"documents": "empty", "database": "empty", "crm": "future"}
    inv = eng.inventory()
    assert [d for d in inv.documents if d.origin == "uploaded"] == []
    assert [d for d in inv.databases if d.origin == "uploaded"] == []
    assert not (data / "uploads").exists(), "uploaded files must be deleted on reset"
    r = eng.ask("What is the penalty clause?", scope="workspace")
    assert r.insufficient and r.trace.route.route == "NONE"


def test_repeated_upload_reset_cycles_do_not_leak(workspace_engine):
    eng, data = workspace_engine
    baseline_chunks = eng.document_source.index.n_chunks
    baseline_tables = set(eng.relational_source.schema.table_names())

    for cycle in range(3):
        _upload_pdf(eng, data, name=f"cycle_{cycle}.pdf")
        _upload_db(eng, data, name=f"cycle_{cycle}.db")
        assert _statuses(eng)["documents"] == "active"
        assert _statuses(eng)["database"] == "active"
        eng.reset()
        assert eng.document_source.index.n_chunks == baseline_chunks, \
            f"chunk leak after cycle {cycle}"
        assert set(eng.relational_source.schema.table_names()) == baseline_tables, \
            f"table leak after cycle {cycle}"
        assert _statuses(eng) == {"documents": "empty", "database": "empty", "crm": "future"}
