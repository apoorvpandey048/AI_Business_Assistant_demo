"""Tests — structured presentation (tables + timeline).

Contract:
- extract_tables_from_answer: deterministic; a Markdown/ASCII pipe table in the answer is
  parsed into an AnswerTable (columns + rows), inheriting the answer's citations; no table
  → []; the answer text is never modified;
- build_timeline: a chronology cue + grounded dated events → TimelineEvents; no cue → ([], None)
  with zero LLM cost; events whose evidence_ids don't resolve are dropped.

Run:  .venv/bin/python -m pytest tests/test_structured_output.py -q
"""
from __future__ import annotations

from app.generation.structured import (_build_events, _has_timeline_cue, build_timeline,
                                        extract_tables_from_answer)
from app.models import Evidence


def _ev(id, content, kind="documents", document=None):
    return Evidence(
        id=id, source_name="contracts_pdf" if kind == "documents" else "business_db",
        source_kind=kind, content=content, citation_label=f"[{id}]", document=document,
    )


# --- table extraction (deterministic) -----------------------------------------

def test_extracts_basic_markdown_table():
    answer = (
        "Here are the invoices [e1]:\n\n"
        "| Invoice | Amount | Status |\n"
        "| --- | --- | --- |\n"
        "| INV-1187 | $12,000 | overdue |\n"
        "| INV-1190 | $3,500 | paid |\n\n"
        "Two invoices were found."
    )
    tables = extract_tables_from_answer(answer, ["e1", "e2"])
    assert len(tables) == 1
    t = tables[0]
    assert t.columns == ["Invoice", "Amount", "Status"]
    assert t.rows == [["INV-1187", "$12,000", "overdue"],
                      ["INV-1190", "$3,500", "paid"]]
    assert t.evidence_ids == ["e1", "e2"]          # inherits the answer's citations


def test_table_with_alignment_separators():
    answer = (
        "| Name | Role |\n"
        "|:---|---:|\n"
        "| Alice | Eng |\n"
    )
    tables = extract_tables_from_answer(answer, [])
    assert len(tables) == 1
    assert tables[0].columns == ["Name", "Role"]
    assert tables[0].rows == [["Alice", "Eng"]]


def test_no_table_returns_empty():
    assert extract_tables_from_answer("A plain prose answer with no table [e1].", ["e1"]) == []
    # a stray pipe without a separator row is NOT a table
    assert extract_tables_from_answer("a | b but no separator", []) == []


def test_ragged_rows_normalized_to_header_width():
    answer = (
        "| A | B | C |\n"
        "| - | - | - |\n"
        "| 1 | 2 |\n"            # short row
        "| 4 | 5 | 6 | 7 |\n"    # long row
    )
    tables = extract_tables_from_answer(answer, [])
    assert tables[0].rows == [["1", "2", ""], ["4", "5", "6"]]


def test_answer_text_not_modified():
    answer = "| A |\n| - |\n| x |\n"
    before = answer
    extract_tables_from_answer(answer, [])
    assert answer == before


def test_two_tables_in_one_answer():
    answer = (
        "| A | B |\n| - | - |\n| 1 | 2 |\n\n"
        "some prose\n\n"
        "| C | D |\n| - | - |\n| 3 | 4 |\n"
    )
    tables = extract_tables_from_answer(answer, [])
    assert len(tables) == 2
    assert tables[1].columns == ["C", "D"]


# --- timeline cues ------------------------------------------------------------

def test_cue_detection():
    assert _has_timeline_cue("Give me a timeline of the case")
    assert _has_timeline_cue("What happened with the contract?")
    assert _has_timeline_cue("Show the sequence of events")
    assert _has_timeline_cue("תן לי ציר זמן של התיק")
    assert not _has_timeline_cue("What is the total amount due?")


def test_no_cue_returns_empty_no_call():
    ev = [_ev("e1", "On 2025-01-01 the contract was signed.")]
    events, call = build_timeline("What is the amount due?", ev, "en")
    assert events == []
    assert call is None                            # zero cost when not cued


def test_cued_but_no_evidence_returns_empty():
    events, call = build_timeline("Give me a timeline", [], "en")
    assert events == []
    assert call is None


# --- event grounding (unit) ---------------------------------------------------

def test_events_dropped_when_ids_unresolved():
    ev = [_ev("e1", "On 2025-01-01 the contract was signed.")]
    data = {"events": [
        {"date": "2025-01-01", "title": "Signed", "evidence_ids": ["e1"]},
        {"date": "2025-06-01", "title": "Invented", "evidence_ids": ["e9"]},
        {"date": "", "title": "No date", "evidence_ids": ["e1"]},          # missing date
        {"date": "2025-07-01", "title": "", "evidence_ids": ["e1"]},       # missing title
    ]}
    events = _build_events(data, ev)
    assert len(events) == 1
    assert events[0].title == "Signed"
    assert events[0].evidence_ids == ["e1"]


# --- timeline live extraction (simulated model) -------------------------------

def test_live_timeline_extraction(sample_engine, monkeypatch):
    import app.llm.client as client_mod
    real = client_mod.LLMClient.structured

    def fake(self, *, purpose, model, system, user, schema, fallback=None,
             max_tokens=None, accept=None):
        if purpose == "timeline":
            from app.models import LLMCall
            return ({"events": [
                {"date": "2025-01-01", "title": "Contract signed",
                 "detail": "Initial agreement", "evidence_ids": ["e1"]},
                {"date": "2025-03-15", "title": "Amendment",
                 "evidence_ids": ["e2"]},
            ]}, LLMCall(purpose=purpose, model=model, mode="live"))
        return real(self, purpose=purpose, model=model, system=system, user=user,
                    schema=schema, fallback=fallback, max_tokens=max_tokens, accept=accept)

    monkeypatch.setattr(client_mod.LLMClient, "structured", fake)
    ev = [_ev("e1", "On 2025-01-01 the contract was signed."),
          _ev("e2", "An amendment was filed on 2025-03-15.")]
    events, call = build_timeline("Give me a timeline of the contract", ev, "en")
    assert call is not None
    assert [e.title for e in events] == ["Contract signed", "Amendment"]
    assert events[0].date == "2025-01-01"


# --- end-to-end: tables surface on the response -------------------------------

def test_tables_surface_on_response(sample_engine, monkeypatch):
    import app.llm.client as client_mod
    real = client_mod.LLMClient.structured

    def fake(self, *, purpose, model, system, user, schema, fallback=None,
             max_tokens=None, accept=None):
        if purpose == "generation":
            from app.models import LLMCall
            return ({
                "answer": "Service may be suspended [e1].\n\n"
                          "| Clause | Effect |\n| --- | --- |\n"
                          "| 7.2 | suspension |\n",
                "citations": ["e1"], "insufficient": False,
            }, LLMCall(purpose=purpose, model=model, mode="live"))
        return real(self, purpose=purpose, model=model, system=system, user=user,
                    schema=schema, fallback=fallback, max_tokens=max_tokens, accept=accept)

    monkeypatch.setattr(client_mod.LLMClient, "structured", fake)
    resp = sample_engine.ask(
        "What do our contracts say about service suspension?", scope="all")
    assert len(resp.tables) == 1
    assert resp.tables[0].columns == ["Clause", "Effect"]
    # inherits the verified citations
    assert "e1" in resp.tables[0].evidence_ids
