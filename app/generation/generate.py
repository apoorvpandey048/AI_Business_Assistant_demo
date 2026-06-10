"""Grounded generation.

The model is instructed to answer ONLY from the supplied evidence and to cite each
claim with an evidence id like [e1]. If the evidence is insufficient it must say so
rather than guess. Offline, a deterministic extractive generator composes a grounded,
cited answer directly from the evidence — so the grounding/citation behaviour is
demonstrable even with no API key.
"""
from __future__ import annotations

import re
from typing import Any

from app.config import get_settings
from app.llm.client import get_llm
from app.models import Evidence

_ANSWER_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "answer": {"type": "string"},
        "citations": {"type": "array", "items": {"type": "string"}},
        "insufficient": {"type": "boolean"},
    },
    "required": ["answer", "citations", "insufficient"],
}

_SYSTEM = (
    "You are a grounded business analyst. Today's date is 2026-06-08. Answer the question "
    "using ONLY the evidence provided — never use outside knowledge or assumptions. Cite "
    "every factual claim inline with the evidence id(s), e.g. [e1] or [e2][e5].\n"
    "Database rows in the evidence have already been filtered to satisfy the question's "
    "constraints (e.g. a date range or status filter) — treat them as authoritative and do "
    "NOT re-derive or second-guess them (e.g. if rows were returned for 'expiring in 90 days', "
    "those ARE the expiring contracts).\n"
    "If the question asks WHICH or WHAT document contains, mentions, or references a term, "
    "answer in a complete sentence that names the document and the page(s) where it appears — "
    "e.g. 'The keyword \"X\" appears in Acme_MSA_2025.pdf (page 4) [e1].' NEVER answer with a "
    "bare filename alone.\n"
    "If the evidence genuinely does not contain enough to answer, set insufficient=true and "
    "briefly say what is missing — do NOT fabricate.\n"
    "Write the answer in the language of the QUESTION (Hebrew only if the question itself is "
    "in Hebrew), regardless of the language of any evidence. Be concise and specific. "
    "'citations' must list the evidence ids you actually used. Return JSON only."
)


def _clean_row(content: str) -> str:
    """Drop internal id columns from a 'k=v; k=v' row for a more readable offline answer."""
    fields = [f.strip() for f in content.split(";")]
    kept = [f for f in fields if f and not re.match(r"^\w*_?id=", f, re.I)]
    return "; ".join(kept) or content


def _evidence_block(evidence: list[Evidence]) -> str:
    lines = []
    for e in evidence:
        prov = e.citation_label
        lines.append(f"{e.id} {prov}\n{e.content}")
    return "\n\n".join(lines)


def _humanize_doc(name: str) -> str:
    """A cleaner display name for a document — strips an upload timestamp/hash suffix
    and the extension, without inventing a title."""
    base = re.sub(r"\.(pdf|txt)$", "", name, flags=re.I)
    # drop a trailing "-2026-06-02-07-29-09-289628" style upload stamp
    base = re.sub(r"[-_](?:\d{2,4})(?:[-_]\d{1,6}){2,}$", "", base)
    base = base.replace("_", " ").replace("-", " ").strip()
    return base or name


def _keyword_answer(terms: list[str], evidence: list[Evidence]) -> dict[str, Any]:
    """Deterministic, professional answer for a 'which document contains X' lookup."""
    docs: dict[str, list[Evidence]] = {}
    for e in evidence:
        docs.setdefault(e.document or e.source_name, []).append(e)
    term_str = ", ".join(f'"{t}"' for t in terms) if terms else "the term"
    lead = "keyword" if len(terms) <= 1 else "keywords"
    parts = []
    for doc, evs in docs.items():
        pages = sorted({e.page for e in evs if e.page is not None})
        cites = "".join(f"[{e.id}]" for e in evs)
        page_str = (
            f" (page {pages[0]})" if len(pages) == 1
            else f" (pages {', '.join(map(str, pages))})" if pages else ""
        )
        parts.append(f"{_humanize_doc(doc)} — {doc}{page_str} {cites}".strip())
    if len(parts) == 1:
        answer = f"The {lead} {term_str} appears in {parts[0]}."
    else:
        answer = (f"The {lead} {term_str} appears in {len(parts)} documents: "
                  + "; ".join(parts) + ".")
    return {"answer": answer, "citations": [e.id for e in evidence], "insufficient": False}


def _extractive_fallback(
    question: str, evidence: list[Evidence], keyword_terms: list[str] | None = None
) -> dict[str, Any]:
    if not evidence:
        return {
            "answer": "Insufficient evidence: no relevant records or document passages were "
                      "retrieved from the available sources to answer this question.",
            "citations": [], "insufficient": True,
        }
    if keyword_terms and all(e.source_kind == "documents" for e in evidence):
        return _keyword_answer(keyword_terms, evidence)
    rel = [e for e in evidence if e.source_kind == "relational"]
    doc = [e for e in evidence if e.source_kind == "documents"]
    parts: list[str] = []
    if rel:
        rows = "; ".join(f"{_clean_row(e.content)} {e.id}" for e in rel[:6])
        parts.append(f"From the business database — {rows}.")
    if doc:
        for e in doc[:3]:
            snippet = " ".join(e.content.split())
            snippet = snippet[:260] + ("…" if len(snippet) > 260 else "")
            parts.append(f"From {e.document} (p.{e.page}): \"{snippet}\" {e.id}.")
    answer = " ".join(parts)
    return {"answer": answer, "citations": [e.id for e in evidence], "insufficient": False}


def generate_answer(question: str, evidence: list[Evidence],
                    keyword_terms: list[str] | None = None):
    s = get_settings()
    llm = get_llm()
    if not evidence:
        data = _extractive_fallback(question, evidence)
        return data["answer"], data["citations"], True, None

    # Keyword document lookups ("which document contains X") are a deterministic
    # identification task — answer them directly from the matched evidence. This
    # guarantees a professional, fully-grounded sentence with the exact document and
    # page(s), with zero LLM variance and no possibility of a bare-filename or
    # hallucinated response.
    if keyword_terms and all(e.source_kind == "documents" for e in evidence):
        data = _keyword_answer(keyword_terms, evidence)
        return data["answer"], data["citations"], data["insufficient"], None

    user = f"Question: {question}\n\nEvidence:\n{_evidence_block(evidence)}"
    data, call = llm.structured(
        purpose="generation", model=s.model_generation, system=_SYSTEM, user=user,
        schema=_ANSWER_SCHEMA,
        fallback=lambda: _extractive_fallback(question, evidence, keyword_terms),
        max_tokens=1500,
    )
    answer = (data.get("answer", "") or "").replace("\\n", "\n").strip()
    return (
        answer,
        list(data.get("citations", [])),
        bool(data.get("insufficient", False)),
        call,
    )
