"""Query-intent detection for document retrieval.

Separates a *keyword lookup* ("which document mentions X", "find the file containing
Y", "search for Z") from a *semantic question* ("what risks are mentioned",
"summarize the project issues"). Keyword lookups are answered BM25-first with exact
term matching, so an exact identifier — a person's name, a code like ``SLA-2025`` — is
found precisely and semantically-similar-but-irrelevant chunks never dominate.

This is fully deterministic, offline, and embedding-independent: the trustworthy floor
beneath the LLM router. Whatever embedding backend the client ends up running
(OpenAI / local / hashing), an exact keyword lookup behaves identically.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Content tokens we extract from the query. ASCII-oriented: Hebrew/RTL queries are
# treated as semantic (they are clause questions in this corpus), which is correct.
_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-_/.]*")

# A query is a "lookup" (find a file) rather than a "question" (read its contents)
# when it carries one of these cues.
_CONTAINER_CUE = re.compile(
    r"\b(contain|contains|containing|mention|mentions|mentioning|reference|references|"
    r"referencing|named|called|keyword|keywords|titled|including|includes)\b|search\s+for",
    re.I,
)
_LOOKUP_VERB = re.compile(
    r"\b(find|search|locate|look\s*up|which|what|where|show|list|identify|return)\b", re.I
)
# The thing a lookup targets. Deliberately excludes "agreement" — "what does the X
# agreement say" is a semantic clause question, not a file lookup.
_TARGET_NOUN = re.compile(
    r"\b(document|documents|doc|docs|file|files|pdf|pdfs|paper|papers|"
    r"contract|contracts|brief|briefs|report|reports|record|records)\b",
    re.I,
)

# Stop / instruction words that are never useful as search terms.
_STOP = {
    "a", "an", "the", "this", "that", "these", "those", "is", "are", "was", "were",
    "be", "been", "do", "does", "did", "of", "in", "on", "at", "to", "for", "from",
    "with", "by", "about", "as", "and", "or", "any", "all", "me", "us", "our", "your",
    "my", "it", "its", "their", "they", "we", "you", "i", "please", "kindly", "can",
    "could", "would", "should", "will", "shall", "have", "has", "had", "which", "what",
    "where", "who", "whom", "whose", "when", "how", "find", "search", "locate", "look",
    "lookup", "up", "show", "list", "identify", "return", "give", "get", "tell",
    "document", "documents", "doc", "docs", "file", "files", "pdf", "pdfs", "paper",
    "papers", "contains", "contain", "containing", "mention", "mentions", "mentioning",
    "reference", "references", "referencing", "keyword", "keywords", "named", "called",
    "titled", "including", "includes", "include", "word", "term", "string", "text",
    "mentioned", "referenced", "named", "if", "there", "some",
}


@dataclass
class QueryIntent:
    """The classified intent of a document query."""

    mode: str = "semantic"               # "keyword" | "semantic"
    terms: list[str] = field(default_factory=list)        # drives BM25 / dense search
    gate_terms: list[str] = field(default_factory=list)   # exact-match hard gate
    search_query: str = ""               # query handed to the retrievers
    reason: str = ""                     # plain-English explanation for the trace


def _dedup(seq: list[str]) -> list[str]:
    seen, out = set(), []
    for s in seq:
        k = s.lower()
        if k and k not in seen:
            seen.add(k)
            out.append(s)
    return out


def _drop_substrings(terms: list[str]) -> list[str]:
    """Drop a term that is a case-insensitive substring of a longer retained term, so
    'SLA' / 'SLA-' collapse into the more specific 'SLA-2025'."""
    kept: list[str] = []
    for t in sorted(terms, key=len, reverse=True):
        tl = t.lower()
        if not any(tl in k.lower() and tl != k.lower() for k in kept):
            kept.append(t)
    # restore original order
    order = {t.lower(): i for i, t in enumerate(terms)}
    return sorted(kept, key=lambda t: order.get(t.lower(), 0))


def _distinctive_terms(query: str) -> list[str]:
    """Quoted spans, identifier-like tokens, and proper nouns — terms specific enough
    to anchor an exact-match lookup."""
    terms: list[str] = []

    # 1) quoted spans — the user told us exactly what to search for
    for dq, sq in re.findall(r'"([^"]+)"|\'([^\']+)\'', query):
        s = (dq or sq).strip()
        if s:
            terms.append(s)

    # 2) identifier-like tokens: a structured code (SLA-2025, INI_MSA, A/B) or an
    #    alphanumeric id (SLA2025) — specific enough to anchor an exact-match gate. A
    #    BARE INTEGER ("90", "2024") is deliberately NOT identifier-like: it is almost
    #    never a real identifier and appears incidentally ("the next 90 days", "top 5"),
    #    where a hard exact-match gate would wrongly zero out an otherwise-good semantic
    #    search (the "90 days" trap that derailed the agentic HYBRID document step). The
    #    number still participates in BM25 ranking — it just no longer hard-gates.
    for tok in _WORD.findall(query):
        t = tok.strip("-_/.'\"")
        has_sep = "-" in t or "_" in t or "/" in t
        has_digit = any(c.isdigit() for c in t)
        has_alpha = any(c.isalpha() for c in t)
        if len(t) > 1 and t.lower() not in _STOP and (has_sep or (has_digit and has_alpha)):
            terms.append(t)

    # 3) proper nouns: a token whose first letter is uppercase, not a stop/instruction
    #    word (those are already filtered). Instruction verbs ("Find", "Which") are in
    #    _STOP, so a capitalized sentence-initial verb is excluded.
    for tok in re.findall(r"[A-Za-z][A-Za-z\-'/]*", query):
        t = tok.strip("-_/.'")
        if len(t) > 1 and t[0].isupper() and t.lower() not in _STOP:
            terms.append(t)

    return _drop_substrings(_dedup(terms))


def _content_tokens(query: str) -> list[str]:
    return [t for t in (w.strip("-_/.") for w in _WORD.findall(query.lower()))
            if len(t) > 1 and t not in _STOP]


def content_terms(query: str) -> list[str]:
    """Public: the non-stopword content tokens of a query. Used by the orchestrator's
    document safety net to check whether a recovered passage is lexically on-topic for
    the question (a deterministic relevance gate that works with or without an LLM)."""
    return _content_tokens(query)


def detect_intent(query: str) -> QueryIntent:
    """Classify a document query as a keyword lookup or a semantic question."""
    q = query or ""
    gate = _distinctive_terms(q)
    content = _content_tokens(q)

    has_container = bool(_CONTAINER_CUE.search(q))
    has_lookup = bool(_LOOKUP_VERB.search(q)) and bool(_TARGET_NOUN.search(q))
    has_quote = '"' in q or "'" in q
    # The query is essentially just the term(s) — e.g. a bare "Apoorv" or "SLA-2025".
    term_dominated = bool(gate) and len(content) <= len(gate) + 1

    is_keyword = bool(gate) and (has_container or has_lookup or has_quote or term_dominated)

    if not is_keyword:
        return QueryIntent(
            mode="semantic", terms=content, gate_terms=[],
            search_query=q,
            reason="Semantic question — hybrid retrieval (dense + BM25 → RRF).",
        )

    # keyword lookup: search on the extracted terms, not the instruction sentence
    terms = _dedup(gate + content)
    label = ", ".join(repr(t) for t in gate)
    return QueryIntent(
        mode="keyword", terms=terms, gate_terms=gate,
        search_query=" ".join(terms) or q,
        reason=f"Keyword lookup for {label} — BM25-first with exact-match filtering.",
    )


def is_document_lookup(query: str) -> bool:
    """True when the query is a document-IDENTIFICATION request ("which document
    mentions X", "find the file containing Y") rather than a fact-EXTRACTION question
    that merely contains a distinctive term ("what is Apoorv's email?"). Only the former
    should be answered with the deterministic "the keyword appears in document Z" style;
    the latter wants the fact extracted, even though both retrieve keyword-first."""
    q = query or ""
    has_container = bool(_CONTAINER_CUE.search(q))
    has_lookup = bool(_LOOKUP_VERB.search(q)) and bool(_TARGET_NOUN.search(q))
    return has_container or has_lookup


def text_hits(text: str, gate_terms: list[str]) -> bool:
    """True if the chunk text literally contains any gate term (case-insensitive)."""
    if not gate_terms:
        return False
    low = (text or "").lower()
    return any(t.lower() in low for t in gate_terms)
