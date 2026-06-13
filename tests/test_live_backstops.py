"""Deterministic backstops for live-model failure shapes (Trust sprint follow-up).

Three live edge cases caught by the trust batteries get engineering guarantees here:
1. A bare COUNT for "has INV-1187 been paid?" hides the entity (and any conflict) —
   the SQL backstop swaps in the rule-library entity lookup.
2. A name-only column set for an overdue question starves generation into a false
   decline — the backstop swaps in the rule-library overdue query.
3. "The documents do not mention X" answered with insufficient=false — the negation
   post-check honors the statement of absence.
"""
from __future__ import annotations

import pytest


# --- the negation post-check (pure function) ---------------------------------

@pytest.mark.parametrize("answer,expected", [
    ("The documents do not mention Wayne Enterprises.", True),
    ("No document mentions Wayne Enterprises.", True),
    ("המסמך אינו מזכיר את וויין אנטרפרייז.", True),
    ("אין אזכור לוויין אנטרפרייז במסמכים.", True),
    # mixed answers with real grounded content must NEVER be flipped
    ("The contract does not mention churn, but it defines a 15% penalty [e2].", False),
    ("The penalty is 15% of the remaining contract value [e1].", False),
    ("", False),
    # long analytical answers stay untouched even if a negation appears
    ("The agreement does not mention early termination explicitly. " + "x" * 300, False),
])
def test_negative_mention_detection(answer, expected):
    from app.generation.generate import _is_negative_mention_answer
    assert _is_negative_mention_answer(answer) is expected


def test_negative_mention_flips_insufficient_and_clears_citations(sample_engine,
                                                                  monkeypatch):
    """A 'not mentioned' generation result must surface as an honest decline."""
    import app.llm.client as client_mod

    real = client_mod.LLMClient.structured

    def fake_structured(self, *, purpose, model, system, user, schema,
                        fallback=None, max_tokens=None, accept=None):
        if purpose == "generation":
            from app.models import LLMCall
            return ({"answer": "The documents do not mention Wayne Enterprises.",
                     "citations": ["e1", "e2"], "insufficient": False},
                    LLMCall(purpose=purpose, model=model, mode="live"))
        return real(self, purpose=purpose, model=model, system=system, user=user,
                    schema=schema, fallback=fallback, max_tokens=max_tokens, accept=accept)

    monkeypatch.setattr(client_mod.LLMClient, "structured", fake_structured)
    resp = sample_engine.ask("What do our contracts say about service suspension?",
                             scope="all")
    assert resp.insufficient
    assert resp.citations == []


# --- the SQL backstop ---------------------------------------------------------

def _strace(sql, columns, rows):
    from app.models import SqlExecutionTrace
    return SqlExecutionTrace(purpose="sql_main", natural_language="q",
                             generated_sql=sql, validated_sql=sql, valid=True,
                             columns=columns, rows=rows, row_count=len(rows))


def test_backstop_fires_on_bare_count_for_entity_question(sample_engine):
    orch = sample_engine.orchestrator
    st = _strace("SELECT COUNT(*) AS payment_count FROM payments",
                 ["payment_count"], [{"payment_count": 0}])
    sql = orch._sql_backstop("Has invoice INV-1187 been paid?", st)
    assert sql and "INV-1187" in sql and "invoice_ref" in sql


def test_backstop_fires_on_nameonly_overdue_result(sample_engine):
    orch = sample_engine.orchestrator
    st = _strace("SELECT customers.name FROM customers", ["name"],
                 [{"name": "Acme Corporation"}])
    sql = orch._sql_backstop("Which customers have overdue invoices?", st)
    assert sql and "overdue" in sql and "invoice_ref" in sql


def test_backstop_silent_when_result_covers_entity(sample_engine):
    orch = sample_engine.orchestrator
    st = _strace("SELECT i.invoice_ref, i.status FROM invoices i",
                 ["invoice_ref", "status"],
                 [{"invoice_ref": "INV-1187", "status": "overdue"}])
    assert orch._sql_backstop("Has invoice INV-1187 been paid?", st) is None


def test_backstop_silent_on_adequate_overdue_result(sample_engine):
    orch = sample_engine.orchestrator
    st = _strace("SELECT c.name, i.invoice_ref, i.amount_usd, i.due_date FROM ...",
                 ["name", "invoice_ref", "amount_usd", "due_date"],
                 [{"name": "Acme Corporation", "invoice_ref": "INV-1187",
                   "amount_usd": 42000.0, "due_date": "2026-05-20"}])
    assert orch._sql_backstop("Which customers have overdue invoices?", st) is None


def test_backstop_end_to_end_count_query(sample_engine, monkeypatch):
    """A COUNT-shaped generated SQL still yields entity rows in the evidence."""
    import app.sources.structured_source as ss

    def fake_generate_sql(nl_query, schema_text, entity_hint=None):
        return ("SELECT COUNT(*) AS payment_count FROM payments", "count", None)

    monkeypatch.setattr(ss, "generate_sql", fake_generate_sql)
    resp = sample_engine.ask("Has invoice INV-1187 been paid?", scope="all")
    rel = [e for e in resp.trace.evidence if e.source_kind == "relational"]
    blob = " ".join(e.content for e in rel)
    assert "INV-1187" in blob, f"backstop did not recover the entity row: {blob[:200]}"
    assert any(s.purpose.endswith("_backstop") for s in resp.trace.sql_executions)
