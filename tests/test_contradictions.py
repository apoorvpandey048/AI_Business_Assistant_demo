"""Contradiction test suite (Trust & Evaluation Sprint, WS6).

Proves the three contractual behaviors of conflict handling:
1. the system DETECTS contradictions between sources (trace.conflicts),
2. the system EXPLAINS them in the answer (both values, both citations),
3. the system does NOT hallucinate a resolution (neither value silently wins).

Plus the equally important inverse: the CLEAN sample corpus produces ZERO
conflicts — the detector must not cry wolf.

Fixtures come from data/eval/contradictions/ (scripts/make_contradiction_fixtures.py):
- CONTRA_Amendment_2026.pdf contradicts the sample database on invoice INV-1187's
  payment status, contract ACM-MSA-2025's end date, and invoice INV-1201's amount.
- vortex.db + VORTEX_Agreement.pdf disagree on every attribute of a synthetic
  customer (used for detector unit tests).
"""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "data" / "eval" / "contradictions"
AMENDMENT = FIXTURES / "CONTRA_Amendment_2026.pdf"


@pytest.fixture(scope="module")
def contra_engine():
    """A fresh engine with the contradicting amendment ingested next to the samples."""
    from app.config import get_settings
    from app.engine import Engine

    if not AMENDMENT.exists():
        pytest.skip("contradiction fixtures missing — run "
                    "scripts/make_contradiction_fixtures.py")
    get_settings.cache_clear()
    eng = Engine()
    info = eng.add_pdf(AMENDMENT.name, AMENDMENT)
    assert info.status == "indexed", info.error
    return eng


# --- detector unit tests (no engine; synthetic evidence) ---------------------

def _ev(id, kind, content, document=None, source_name=None, label=None, extra=None):
    from app.models import Evidence
    return Evidence(
        id=id, source_name=source_name or ("business_db" if kind == "relational"
                                           else "contracts_pdf"),
        source_kind=kind, content=content,
        citation_label=label or f"[{id}]", document=document, extra=extra or {},
    )


def test_detects_paid_vs_unpaid():
    from app.generation.conflicts import detect_conflicts
    conflicts = detect_conflicts([
        _ev("e1", "relational",
            "invoice_ref=INV-9001; customer=Vortex Analytics; amount_usd=18000.0; "
            "status=paid; due_date=2026-04-30"),
        _ev("e2", "documents",
            "Invoice INV-9001 in the amount of $18,500 remains unpaid as of June 2026.",
            document="VORTEX_Agreement.pdf"),
    ])
    attrs = {c.attribute for c in conflicts}
    assert "payment_status" in attrs
    assert "amount" in attrs            # 18,000 vs 18,500 keyed to the same invoice
    pay = next(c for c in conflicts if c.attribute == "payment_status")
    assert {s.value for s in pay.sides} == {"paid", "unpaid"}
    assert {s.evidence_id for s in pay.sides} == {"e1", "e2"}


def test_detects_expiry_year_conflict():
    from app.generation.conflicts import detect_conflicts
    conflicts = detect_conflicts([
        _ev("e1", "relational",
            "contract_ref=VTX-MSA-2026; customer=Vortex Analytics; "
            "end_date=2028-03-15; status=active"),
        _ev("e2", "documents",
            "The Agreement VTX-MSA-2026 expires on 2027-03-15 and does not renew "
            "automatically.", document="VORTEX_Agreement.pdf"),
    ])
    assert any(c.attribute == "end_date" for c in conflicts)


def test_detects_penalty_percent_conflict():
    from app.generation.conflicts import detect_conflicts
    conflicts = detect_conflicts([
        _ev("e1", "relational",
            "contract_ref=VTX-MSA-2026; customer=Vortex Analytics; penalty_pct=10.0"),
        _ev("e2", "documents",
            "Early termination by the Customer incurs a penalty equal to 15% of the "
            "remaining contract value under VTX-MSA-2026.",
            document="VORTEX_Agreement.pdf"),
    ])
    assert any(c.attribute == "penalty_percent" for c in conflicts)


def test_detects_entity_status_conflict():
    from app.generation.conflicts import detect_conflicts
    conflicts = detect_conflicts([
        _ev("e1", "relational",
            "name=Vortex Analytics; status=active; country=USA"),
        _ev("e2", "documents",
            "Following repeated non-payment, the account of Vortex Analytics is "
            "suspended until all outstanding amounts are settled.",
            document="VORTEX_Agreement.pdf"),
    ])
    status = [c for c in conflicts if c.attribute == "entity_status"]
    assert status and {s.value for s in status[0].sides} == {"active", "suspended"}


def test_doc_vs_doc_penalty_conflict():
    from app.generation.conflicts import detect_conflicts
    conflicts = detect_conflicts([
        _ev("e1", "documents",
            "If Customer terminates for convenience, Customer shall pay an early "
            "termination penalty equal to 15% of the remaining contract value under "
            "ACM-MSA-2025.", document="ACME_MSA_2025.pdf"),
        _ev("e2", "documents",
            "The early termination penalty under ACM-MSA-2025 is revised to 20% of "
            "the remaining contract value.", document="CONTRA_Amendment_2026.pdf"),
    ])
    assert any(c.attribute == "penalty_percent" for c in conflicts)


def test_conditional_boilerplate_is_not_a_status_claim():
    """'Provider may suspend ... if any invoice remains unpaid' must NOT conflict
    with a paid invoice row — it is a conditional clause, not a status statement."""
    from app.generation.conflicts import detect_conflicts
    conflicts = detect_conflicts([
        _ev("e1", "relational",
            "invoice_ref=INV-1090; customer=Acme Corporation; amount_usd=40000.0; "
            "status=paid"),
        _ev("e2", "documents",
            "Provider may suspend the Services, in whole or in part, if any undisputed "
            "invoice INV-1090 remains unpaid for more than 30 days after its due date.",
            document="ACME_MSA_2025.pdf"),
    ])
    assert conflicts == []


def test_late_fee_does_not_conflict_with_termination_penalty():
    """1.5%/month late fee and a 12% exit penalty are DIFFERENT attributes."""
    from app.generation.conflicts import detect_conflicts
    conflicts = detect_conflicts([
        _ev("e1", "documents",
            "(From Tavor Systems's agreement) על סכומים באיחור ייווסף קנס פיגורים "
            "בשיעור 1.5% לחודש.", document="TAVOR_Contract_HE.pdf",
            extra={"owner": "Tavor Systems"}),
        _ev("e2", "relational",
            "contract_ref=TVR-MSA-2025; customer=Tavor Systems; penalty_pct=12.0"),
    ])
    assert not any(c.attribute == "penalty_percent" for c in conflicts)


# --- end-to-end: sample corpus + contradicting amendment ---------------------

def test_e2e_paid_vs_overdue_reported(contra_engine):
    resp = contra_engine.ask("Has invoice INV-1187 been paid?", scope="all")
    t = resp.trace
    assert not resp.insufficient
    pay = [c for c in t.conflicts if c.attribute == "payment_status"]
    assert pay, f"expected a payment_status conflict, got {t.conflicts}"
    # both values present, explicit disagreement, no silent winner
    a = resp.answer.lower()
    assert "paid" in a and ("overdue" in a or "unpaid" in a)
    assert any(w in a for w in ("conflict", "disagree", "סתירה"))
    cited_kinds = {e.source_kind for e in resp.citations}
    assert {"relational", "documents"} <= cited_kinds


def test_e2e_expiry_conflict_reported(contra_engine):
    resp = contra_engine.ask("When does contract ACM-MSA-2025 expire?", scope="all")
    t = resp.trace
    dates = [c for c in t.conflicts if c.attribute == "end_date"]
    assert dates, f"expected an end_date conflict, got {t.conflicts}"
    a = resp.answer
    assert "2026-08-20" in a and "2027-08-20" in a
    assert any(w in a.lower() for w in ("conflict", "disagree"))


def test_e2e_amount_conflict_reported(contra_engine):
    resp = contra_engine.ask("How much is invoice INV-1201?", scope="all")
    t = resp.trace
    amounts = [c for c in t.conflicts if c.attribute == "amount"]
    assert amounts, f"expected an amount conflict, got {t.conflicts}"
    a = resp.answer.replace(",", "")
    assert "18000" in a or "18,000" in resp.answer
    assert "19500" in a or "19,500" in resp.answer


def test_e2e_no_hallucinated_resolution(contra_engine):
    """The answer must not assert one value as THE answer while omitting the other."""
    resp = contra_engine.ask("Has invoice INV-1187 been paid?", scope="all")
    a = resp.answer.lower()
    # if it mentions paid at all it must also surface the overdue record
    assert ("overdue" in a or "unpaid" in a) and "paid" in a


# --- the inverse gate: clean corpus stays silent -----------------------------

CLEAN_QUESTIONS = [
    "Which customers have overdue invoices, and what do their agreements say about service suspension?",
    "What is the total outstanding invoice amount per customer?",
    "What do our contracts say about service suspension?",
    "What contracts expire in the next 90 days, and what penalties do they define?",
    "Show all active projects and summarize the risks in their documentation.",
    "Has invoice INV-1187 been paid?",
    "מה אומר ההסכם של תבור מערכות על השעיית שירות וקנסות?",
]


@pytest.mark.parametrize("q", CLEAN_QUESTIONS)
def test_clean_corpus_produces_zero_conflicts(sample_engine, q):
    resp = sample_engine.ask(q, scope="all")
    assert resp.trace.conflicts == [], (
        f"false-positive conflict on clean data: {[c.note for c in resp.trace.conflicts]}"
    )
