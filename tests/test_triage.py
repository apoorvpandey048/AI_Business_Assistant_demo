"""Tests — user-defined triage (the "Cases prompt").

Contract:
- no Cases prompt → TriagePanel(defined=False), zero LLM cost, response shape unchanged;
- a Cases prompt + evidence with named entities → items bucketed with grounded evidence_ids;
- an ungrounded triage row (empty or unknown evidence_id) is dropped (never surfaced);
- offline (no live model) NEVER fabricates buckets — empty panel with an explanatory note;
- levels are coerced/validated to red|green|blue; unknown levels are dropped.

Run:  .venv/bin/python -m pytest tests/test_triage.py -q
"""
from __future__ import annotations

from app.generation.triage import (_CASE_MAX_CHARS, _build_panel, _sanitize_case,
                                    classify_triage)
from app.models import Evidence


def _ev(id, content, kind="documents", document=None):
    return Evidence(
        id=id, source_name="contracts_pdf" if kind == "documents" else "business_db",
        source_kind=kind, content=content, citation_label=f"[{id}]", document=document,
    )


# --- no Cases prompt: zero cost, undefined panel ------------------------------

def test_no_case_instructions_returns_undefined_panel():
    ev = [_ev("e1", "Mohammed Ben is on life support.")]
    panel, call = classify_triage("Who needs urgent care?", ev, None, "en")
    assert panel.defined is False
    assert call is None
    assert panel.items == []


def test_blank_case_instructions_returns_undefined_panel():
    ev = [_ev("e1", "Mohammed Ben is on life support.")]
    panel, call = classify_triage("Who?", ev, "   \n  ", "en")
    assert panel.defined is False
    assert call is None


# --- sanitize + cap -----------------------------------------------------------

def test_case_sanitized_and_capped():
    messy = "  life support\n\n→  red  " + "x" * 5000
    s = _sanitize_case(messy)
    assert s.startswith("life support → red")
    assert "\n" not in s and "  " not in s
    assert len(s) <= _CASE_MAX_CHARS


# --- offline never fabricates -------------------------------------------------

def test_offline_returns_empty_panel_with_note(sample_engine):
    """Under hermetic offline mode (conftest) the triage call hits the deterministic
    fallback, which must NOT fabricate buckets."""
    ev = [_ev("e1", "Mohammed Ben is on life support in the ICU.")]
    panel, call = classify_triage(
        "Classify the patients.", ev,
        "patients on life support → red, with fever → green, stable → blue", "en",
    )
    assert panel.defined is True
    assert panel.items == []                       # nothing invented offline
    assert "live model" in panel.note.lower()


def test_empty_evidence_classifies_nothing():
    panel, call = classify_triage(
        "Classify.", [], "life support → red", "en",
    )
    assert panel.defined is True
    assert panel.items == []
    assert call is None                            # no evidence → no LLM call


# --- grounded bucketing (live model simulated) --------------------------------

def test_live_buckets_entities_with_grounded_ids(sample_engine, monkeypatch):
    import app.llm.client as client_mod
    real = client_mod.LLMClient.structured

    def fake(self, *, purpose, model, system, user, schema, fallback=None,
             max_tokens=None, accept=None):
        if purpose == "triage":
            from app.models import LLMCall
            return ({
                "legend": {"red": "on life support", "blue": "stable"},
                "items": [
                    {"label": "Mohammed Ben", "level": "red",
                     "summary": "On life support in the ICU.",
                     "evidence_ids": ["e1"], "rule": "life support → red"},
                    {"label": "Jane Doe", "level": "blue",
                     "summary": "Stable and discharged.",
                     "evidence_ids": ["e2"]},
                ],
            }, LLMCall(purpose=purpose, model=model, mode="live"))
        return real(self, purpose=purpose, model=model, system=system, user=user,
                    schema=schema, fallback=fallback, max_tokens=max_tokens, accept=accept)

    monkeypatch.setattr(client_mod.LLMClient, "structured", fake)
    ev = [_ev("e1", "Mohammed Ben is on life support in the ICU."),
          _ev("e2", "Jane Doe is stable and was discharged.")]
    panel, call = classify_triage(
        "Classify the patients.", ev,
        "life support → red, stable → blue", "en",
    )
    assert panel.defined is True
    assert call is not None
    levels = {i.label: i.level for i in panel.items}
    assert levels == {"Mohammed Ben": "red", "Jane Doe": "blue"}
    assert panel.legend.get("red") == "on life support"
    moh = next(i for i in panel.items if i.label == "Mohammed Ben")
    assert moh.evidence_ids == ["e1"]
    assert moh.rule == "life support → red"


# --- grounding guard (unit) ---------------------------------------------------

def test_ungrounded_row_with_unknown_id_is_dropped():
    ev = [_ev("e1", "Mohammed Ben is on life support.")]
    data = {
        "legend": {"red": "life support"},
        "items": [
            {"label": "Mohammed Ben", "level": "red", "summary": "ICU",
             "evidence_ids": ["e1"]},
            # ungrounded: references e9 which is not in the evidence
            {"label": "Ghost Patient", "level": "red", "summary": "invented",
             "evidence_ids": ["e9"]},
        ],
    }
    panel = _build_panel(data, ev, live=True)
    labels = [i.label for i in panel.items]
    assert labels == ["Mohammed Ben"]
    assert "dropped" in panel.note.lower()


def test_row_with_empty_evidence_ids_is_dropped():
    ev = [_ev("e1", "Mohammed Ben is on life support.")]
    data = {"legend": {}, "items": [
        {"label": "Mohammed Ben", "level": "red", "summary": "x", "evidence_ids": []},
    ]}
    panel = _build_panel(data, ev, live=True)
    assert panel.items == []


def test_unknown_level_is_dropped():
    ev = [_ev("e1", "x")]
    data = {"legend": {}, "items": [
        {"label": "A", "level": "purple", "summary": "x", "evidence_ids": ["e1"]},
        {"label": "B", "level": "green", "summary": "y", "evidence_ids": ["e1"]},
    ]}
    panel = _build_panel(data, ev, live=True)
    assert [i.label for i in panel.items] == ["B"]


def test_legend_only_keeps_valid_colours():
    ev = [_ev("e1", "x")]
    data = {"legend": {"red": "r", "RED": "dup", "magenta": "no", "green": "g"},
            "items": []}
    panel = _build_panel(data, ev, live=True)
    assert set(panel.legend.keys()) == {"red", "green"}


# --- end-to-end plumbing through the engine -----------------------------------

def test_case_instructions_reach_orchestrator(sample_engine, monkeypatch):
    captured: dict = {}
    import app.routing.orchestrator as orch
    real = orch.classify_triage

    def spy(question, evidence, case_instructions, target_language, **kw):
        captured["case"] = case_instructions
        return real(question, evidence, case_instructions, target_language, **kw)

    monkeypatch.setattr(orch, "classify_triage", spy)
    resp = sample_engine.ask(
        "What do our contracts say about service suspension?", scope="all",
        case_instructions="suspendable → red, active → blue",
    )
    assert captured["case"] == "suspendable → red, active → blue"
    assert resp.triage is not None
    assert resp.triage.defined is True


def test_no_case_instructions_leaves_triage_none(sample_engine):
    resp = sample_engine.ask(
        "What do our contracts say about service suspension?", scope="all")
    assert resp.triage is None
    # shape unchanged: timeline/tables default empty
    assert resp.timeline == []
    assert resp.tables == []
