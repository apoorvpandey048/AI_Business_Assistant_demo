"""Deterministic cross-source conflict detection.

The client's question — "what if the PDF and the database disagree?" — gets an
explicit, engineered answer here. Every answer's evidence set is scanned for
attributed claims (payment status, entity status, end/expiry dates, penalty and
late-fee percentages, monetary amounts) that reference the same entity (invoice
ref, contract ref, project ref, or customer name) with different values. Detected
conflicts land on the trace (``trace.conflicts``) and are injected into generation
so the answer reports BOTH sides with citations instead of silently picking one.

Design rules (see docs/conflict-resolution.md):
- deterministic — no LLM involved; runs identically offline and live;
- conservative — every claim needs an entity anchor; conditional contract
  boilerplate ("Provider *may* suspend … *if* any invoice remains unpaid") is
  never treated as a status claim; the clean sample corpus must produce ZERO
  conflicts (regression-gated by tests/test_contradictions.py);
- explicit — a conflict is never resolved automatically. Precedence is a
  documented *reporting* policy, not a hidden heuristic.
"""
from __future__ import annotations

import itertools
import re
from dataclasses import dataclass, field

from app.models import Conflict, ConflictSide, Evidence

MAX_CONFLICTS = 5            # report the most important few, never a wall of noise

# -- entity anchors -----------------------------------------------------------
# Business refs: INV-1187, ACM-MSA-2025, TVR-MSA-2025, PRJ-ATLAS …
_REF = re.compile(r"\b[A-Z]{2,5}-(?:[A-Z]{1,5}-)?\d{2,5}\b")
_PRJ = re.compile(r"\bPRJ-[A-Z]{2,}\b")
# Shared labels that look like refs but identify SCHEDULES shared by many entities
# (every sample contract references SLA-2025) — never use them as an entity anchor.
_REF_BLACKLIST_PREFIX = ("SLA",)

_DATE = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")
_YEAR = re.compile(r"\b(20\d{2})\b")
_PCT = re.compile(r"\b(\d{1,2}(?:\.\d+)?)\s*%")
_MONEY = re.compile(r"(?:\$|USD\s?)\s?([\d][\d,]*(?:\.\d+)?)\b")

_PAY_BUCKET = {
    "paid": "paid", "settled": "paid",
    "unpaid": "unpaid", "overdue": "unpaid", "outstanding": "unpaid",
    "pending": "unpaid",  # "pending" = not yet paid; conflicts with "paid", not "unpaid"
}
_ENTITY_BUCKET = {
    "active": "active", "suspended": "suspended", "terminated": "terminated",
    "cancelled": "terminated", "canceled": "terminated",
    "on_hold": "on hold", "on hold": "on hold", "paused": "on hold",
    "completed": "completed", "expired": "expired",
}

_END_DATE_COLS = ("end_date", "expiry_date", "expires", "expiration_date",
                  "valid_until", "expires_on", "expiry")
_PENALTY_COLS = ("penalty_pct", "penalty_percent", "penalty", "exit_penalty",
                 "termination_penalty")
_LATE_FEE_COLS = ("late_fee_pct", "late_fee_percent", "late_fee")
_NAME_COLS = ("customer", "name", "customer_name", "client", "company")

# Words that mark a sentence as conditional/boilerplate rather than a statement of
# fact about a specific entity ("Provider may suspend … if any invoice remains unpaid").
_CONDITIONAL = (" if ", "may ", "unless", "in the event", "would ", "should ",
                "רשאי", "אלא אם", "במקרה ש")

_END_DATE_KW = ("expir", "valid until", "in effect until", "terminates on",
                "end date", "ends on", "תוקף", "יפוג", "יסתיים")
_LATE_FEE_KW = ("late fee", "late payment", "per month", "לחודש", "פיגורים")
_PENALTY_KW = ("penalt", "termination fee", "קנס")

ATTR_EN = {
    "payment_status": "payment status",
    "entity_status": "status",
    "end_date": "the end/expiry date",
    "penalty_percent": "the termination penalty",
    "late_fee_percent": "the late-fee rate",
    "amount": "the amount",
    "contract_value": "the contract value",
}
ATTR_HE = {
    "payment_status": "סטטוס התשלום",
    "entity_status": "הסטטוס",
    "end_date": "תאריך הסיום/התפוגה",
    "penalty_percent": "קנס היציאה",
    "late_fee_percent": "שיעור ריבית הפיגורים",
    "amount": "הסכום",
    "contract_value": "שווי ההסכם",
}


@dataclass
class _Claim:
    evidence: Evidence
    attribute: str
    value: object                 # normalized comparable value
    display: str                  # raw observed value, for the report
    excerpt: str = ""
    entities: set[str] = field(default_factory=set)


# -- helpers ------------------------------------------------------------------

def _refs(text: str) -> set[str]:
    found = {m.group(0) for m in _REF.finditer(text)} | {m.group(0) for m in _PRJ.finditer(text)}
    return {r.lower() for r in found
            if not any(r.upper().startswith(p) for p in _REF_BLACKLIST_PREFIX)}


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text or "") if s.strip()]


def _is_conditional(sentence: str) -> bool:
    s = f" {sentence.lower()} "
    return s.strip().startswith("if ") or any(w in s for w in _CONDITIONAL)


def _parse_fields(content: str) -> dict[str, str]:
    """Parse the 'k=v; k=v' row text produced by StructuredSource."""
    fields: dict[str, str] = {}
    for part in content.split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            fields[k.strip().lower()] = v.strip()
    return fields


def _date_value(text: str):
    """Normalize a date mention: (year, full_iso_or_None)."""
    m = _DATE.search(text)
    if m:
        return (int(m.group(1)), m.group(0))
    y = _YEAR.search(text)
    if y:
        return (int(y.group(1)), None)
    return None


def _num(text: str) -> float | None:
    try:
        return float(text.replace(",", "").replace("%", "").replace("$", "").strip())
    except (ValueError, AttributeError):
        return None


def _pay_bucket_doc(sentence_lower: str) -> str | None:
    """Payment-status bucket for a document sentence, negation-aware."""
    if ("unpaid" in sentence_lower or "not been paid" in sentence_lower
            or "not paid" in sentence_lower or "overdue" in sentence_lower
            or "outstanding" in sentence_lower or "לא שולמ" in sentence_lower):
        return "unpaid"
    if re.search(r"\bpaid\b", sentence_lower) or "settled" in sentence_lower \
            or "שולמ" in sentence_lower:
        return "paid"
    return None


# -- claim extraction ---------------------------------------------------------

def _sql_claims(e: Evidence) -> list[_Claim]:
    fields = _parse_fields(e.content or "")
    if not fields:
        return []
    refs = _refs(e.content or "")
    inv_ref = (fields.get("invoice_ref") or "").lower() or None
    contract_ref = (fields.get("contract_ref") or "").lower() or None
    names = {v.lower() for k, v in fields.items()
             if k in _NAME_COLS and v and any(c.isalpha() for c in v)}
    claims: list[_Claim] = []

    status = (fields.get("status") or "").strip().lower()
    if status:
        if inv_ref and status in _PAY_BUCKET:
            claims.append(_Claim(e, "payment_status", _PAY_BUCKET[status], status,
                                 e.content[:120], {inv_ref}))
        elif status in _ENTITY_BUCKET:
            ents = ({contract_ref} if contract_ref else set()) | names
            if ents:
                claims.append(_Claim(e, "entity_status", _ENTITY_BUCKET[status], status,
                                     e.content[:120], ents))
        # NOTE: a paid/unpaid status WITHOUT an invoice_ref is deliberately not
        # claimed — keying payment status by customer name would falsely conflict
        # two different invoices of the same customer.

    for col in _END_DATE_COLS:
        v = fields.get(col)
        if v:
            d = _date_value(v)
            ents = ({contract_ref} if contract_ref else set()) | names | refs
            if d and ents:
                claims.append(_Claim(e, "end_date", d, v, e.content[:120], ents))
            break

    for col in _PENALTY_COLS:
        v = _num(fields.get(col, ""))
        if v is not None:
            ents = ({contract_ref} if contract_ref else set()) | names | refs
            if ents:
                claims.append(_Claim(e, "penalty_percent", v, f"{fields.get(col)}%",
                                     e.content[:120], ents))
            break

    for col in _LATE_FEE_COLS:
        v = _num(fields.get(col, ""))
        if v is not None:
            ents = ({contract_ref} if contract_ref else set()) | names | refs
            if ents:
                claims.append(_Claim(e, "late_fee_percent", v, f"{fields.get(col)}%",
                                     e.content[:120], ents))
            break

    amount = _num(fields.get("amount_usd", "") or fields.get("amount", ""))
    if amount is not None and inv_ref:
        claims.append(_Claim(e, "amount", amount, f"${amount:,.0f}",
                             e.content[:120], {inv_ref}))

    value = _num(fields.get("value_usd", ""))
    if value is not None:
        ents = ({contract_ref} if contract_ref else set()) | names
        if ents:
            claims.append(_Claim(e, "contract_value", value, f"${value:,.0f}",
                                 e.content[:120], ents))
    return claims


def _doc_claims(e: Evidence, name_lexicon: set[str]) -> list[_Claim]:
    text = e.content or ""
    text_lower = text.lower()
    chunk_refs = _refs(text)
    chunk_names = {n for n in name_lexicon if n in text_lower}
    owner = ((e.extra or {}).get("owner") or "").lower()
    base = chunk_refs | chunk_names | ({owner} if owner else set())
    claims: list[_Claim] = []

    for sent in _sentences(text):
        s_lower = sent.lower()
        s_refs = _refs(sent)
        s_names = {n for n in name_lexicon if n in s_lower}
        anchor = (s_refs | s_names) or base
        conditional = _is_conditional(sent)

        # payment status — only ever about a specific invoice named IN the sentence
        inv_refs = {r for r in s_refs if r.startswith("inv-")}
        if inv_refs and not conditional:
            bucket = _pay_bucket_doc(s_lower)
            if bucket:
                raw = "unpaid" if bucket == "unpaid" else "paid"
                claims.append(_Claim(e, "payment_status", bucket, raw, sent[:160], inv_refs))

        # amount — a money figure tied to an invoice named in the sentence
        if inv_refs:
            m = _MONEY.search(sent)
            if m:
                v = _num(m.group(1))
                if v is not None:
                    claims.append(_Claim(e, "amount", v, f"${v:,.0f}", sent[:160], inv_refs))

        # end/expiry date
        if any(k in s_lower for k in _END_DATE_KW) and anchor:
            d = _date_value(sent)
            if d:
                claims.append(_Claim(e, "end_date", d, d[1] or str(d[0]), sent[:160], anchor))

        # percentages — late fee vs termination penalty are different attributes
        if anchor:
            pcts = _PCT.findall(sent)
            if pcts:
                if any(k in s_lower for k in _LATE_FEE_KW):
                    v = _num(pcts[0])
                    if v is not None:
                        claims.append(_Claim(e, "late_fee_percent", v, f"{pcts[0]}%",
                                             sent[:160], anchor))
                elif any(k in s_lower for k in _PENALTY_KW):
                    v = _num(pcts[0])
                    if v is not None:
                        claims.append(_Claim(e, "penalty_percent", v, f"{pcts[0]}%",
                                             sent[:160], anchor))

        # entity status — needs a non-conditional sentence AND an in-sentence anchor
        if not conditional and (s_refs or s_names):
            for word, bucket in _ENTITY_BUCKET.items():
                if re.search(rf"\b{re.escape(word)}\b", s_lower):
                    claims.append(_Claim(e, "entity_status", bucket, word,
                                         sent[:160], s_refs | s_names))
                    break
    return claims


# -- comparison ---------------------------------------------------------------

def _differ(attr: str, a: _Claim, b: _Claim) -> bool:
    if attr == "end_date":
        (ya, fa), (yb, fb) = a.value, b.value
        if fa and fb:
            return fa != fb
        return ya != yb
    if attr in ("penalty_percent", "late_fee_percent", "amount", "contract_value"):
        return abs(float(a.value) - float(b.value)) > 0.01
    return a.value != b.value


def detect_conflicts(evidence: list[Evidence]) -> list[Conflict]:
    """Scan an evidence set for cross-source disagreements. Deterministic; returns
    at most MAX_CONFLICTS, deduplicated by (attribute, entity, value pair)."""
    name_lexicon: set[str] = set()
    for e in evidence:
        if e.source_kind == "relational":
            for k, v in _parse_fields(e.content or "").items():
                if k in _NAME_COLS and v and any(c.isalpha() for c in v):
                    name_lexicon.add(v.lower())
        owner = ((e.extra or {}).get("owner") or "").lower()
        if owner:
            name_lexicon.add(owner)

    claims: list[_Claim] = []
    for e in evidence:
        if e.source_kind == "relational":
            claims += _sql_claims(e)
        elif e.source_kind == "documents":
            claims += _doc_claims(e, name_lexicon)

    conflicts: list[Conflict] = []
    seen: set[tuple] = set()
    for a, b in itertools.combinations(claims, 2):
        if a.attribute != b.attribute or a.evidence.id == b.evidence.id:
            continue
        # two chunks of the SAME document are overlapping context, not two sources
        if (a.evidence.source_kind == b.evidence.source_kind == "documents"
                and a.evidence.document == b.evidence.document):
            continue
        shared = a.entities & b.entities
        if not shared or not _differ(a.attribute, a, b):
            continue
        entity = sorted(shared)[0].upper() if sorted(shared)[0].startswith(
            ("inv-", "prj-")) or "-" in sorted(shared)[0] else sorted(shared)[0].title()
        key = (a.attribute, frozenset(shared), frozenset({a.display, b.display}))
        if key in seen:
            continue
        seen.add(key)
        conflicts.append(Conflict(
            entity=entity, attribute=a.attribute,
            sides=[
                ConflictSide(evidence_id=a.evidence.id, source_name=a.evidence.source_name,
                             citation_label=a.evidence.citation_label,
                             value=a.display, excerpt=a.excerpt),
                ConflictSide(evidence_id=b.evidence.id, source_name=b.evidence.source_name,
                             citation_label=b.evidence.citation_label,
                             value=b.display, excerpt=b.excerpt),
            ],
            note=(f"{ATTR_EN[a.attribute]} for {entity}: "
                  f"{a.display} per {a.evidence.citation_label} "
                  f"vs {b.display} per {b.evidence.citation_label}"),
        ))
        if len(conflicts) >= MAX_CONFLICTS:
            break
    return conflicts


# -- reporting ----------------------------------------------------------------

def conflict_statements(conflicts: list[Conflict], hebrew: bool = False) -> list[str]:
    """Deterministic answer templates — both sides cited, uncertainty stated,
    no winner chosen. Used as the offline answer text and as a live-mode backstop."""
    out: list[str] = []
    for c in conflicts:
        s1, s2 = c.sides[0], c.sides[1]
        if hebrew:
            out.append(
                f"⚠ סתירה בין המקורות לגבי {ATTR_HE.get(c.attribute, c.attribute)} של "
                f"{c.entity}: {s1.citation_label} מציין {s1.value} [{s1.evidence_id}], "
                f"בעוד {s2.citation_label} מציין {s2.value} [{s2.evidence_id}]. "
                f"המקורות אינם תואמים — יש לאמת איזה מהם עדכני לפני הסתמכות על אחד הערכים."
            )
        else:
            out.append(
                f"⚠ Conflicting evidence on {ATTR_EN.get(c.attribute, c.attribute)} for "
                f"{c.entity}: {s1.citation_label} reports {s1.value} [{s1.evidence_id}], "
                f"while {s2.citation_label} reports {s2.value} [{s2.evidence_id}]. "
                f"The sources disagree — verify which is current before relying on "
                f"either value."
            )
    return out


def conflict_reported(answer: str, conflict: Conflict) -> bool:
    """Did the answer already surface this conflict? Requires BOTH values present
    plus an explicit disagreement marker."""
    a = (answer or "").lower()
    markers = ("conflict", "disagree", "inconsisten", "contradict", "differ",
               "סתירה", "אינם תואמים", "סותר")
    both = all(s.value.lower().strip("%$ ") in a for s in conflict.sides)
    return both and any(m in a for m in markers)
