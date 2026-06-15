"""Core data models — the spine of traceability.

Everything the engine produces is one of these objects. The answer, the citation
list, and the inspector panel all reference the SAME ``Evidence`` objects, so there
is exactly one source of truth from retrieval through to the rendered citation.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

SourceKind = Literal["documents", "relational", "api"]
Route = Literal["PDF", "SQL", "HYBRID", "NONE"]


class Evidence(BaseModel):
    """A single, fully-attributed piece of evidence used to ground the answer."""

    id: str                                   # "e1", "e2", … — stable citation handle
    source_name: str                          # "contracts_pdf" | "business_db" | …
    source_kind: SourceKind
    content: str                              # exact text/row handed to the LLM
    citation_label: str                       # "[ACME_MSA_2025.pdf p.4]" / "[invoices #1187]"
    score: Optional[float] = None             # retrieval / rerank score (documents)
    language: Optional[str] = None            # "en" | "he"
    origin: Optional[str] = None              # "sample" | "uploaded" — provenance for trust
    used: bool = False                        # did the final answer actually cite this?

    # document provenance
    document: Optional[str] = None
    page: Optional[int] = None
    chunk_id: Optional[str] = None
    section: Optional[str] = None

    # relational provenance
    table: Optional[str] = None
    row_ids: Optional[list[Any]] = None
    sql: Optional[str] = None
    columns: Optional[list[str]] = None

    extra: dict[str, Any] = Field(default_factory=dict)


class RetrievalCandidate(BaseModel):
    """One document chunk as it moves through the hybrid pipeline — for the inspector."""

    chunk_id: str
    document: str
    page: Optional[int] = None
    section: Optional[str] = None
    language: Optional[str] = None
    snippet: str

    dense_rank: Optional[int] = None
    dense_score: Optional[float] = None
    bm25_rank: Optional[int] = None
    bm25_score: Optional[float] = None
    rrf_score: Optional[float] = None
    rerank_score: Optional[float] = None
    final_rank: Optional[int] = None
    selected: bool = False
    keyword_hit: bool = False                 # chunk literally contains a searched term


class DocumentRetrievalTrace(BaseModel):
    query: str
    rewritten_queries: list[str] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    embedding_backend: str = "unknown"
    reranker_backend: str = "none"
    params: dict[str, Any] = Field(default_factory=dict)
    candidates: list[RetrievalCandidate] = Field(default_factory=list)
    # intent-aware retrieval (set by DocumentIndex.retrieve)
    intent: str = "semantic"                  # "keyword" | "semantic"
    search_terms: list[str] = Field(default_factory=list)
    exact_hits: int = 0                       # chunks literally containing a term
    strategy: str = ""                        # plain-English summary for the inspector
    # coverage-complete retrieval (Zero-Loss sprint, Phase 2)
    enumeration: bool = False                 # question asked for ALL instances
    completeness_gaps: list[str] = Field(default_factory=list)  # terms recovered by fill


class SqlExecutionTrace(BaseModel):
    purpose: str                              # what this query was for
    natural_language: str
    generated_sql: str
    validated_sql: Optional[str] = None
    valid: bool = False
    validation_error: Optional[str] = None
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0
    tables: list[str] = Field(default_factory=list)
    duration_ms: float = 0.0


class RouteDecision(BaseModel):
    route: Route
    reasoning: str
    confidence: float = 0.0
    languages: list[str] = Field(default_factory=lambda: ["en"])
    document_subquery: Optional[str] = None   # what to ask the documents
    sql_subquery: Optional[str] = None        # what to ask the database
    entity_hint: Optional[str] = None         # e.g. "customers with overdue invoices"
    agentic: bool = False                     # does this need SQL → entities → docs?
    strategy_note: Optional[str] = None


class LLMCall(BaseModel):
    purpose: str
    model: str
    mode: Literal["live", "cached", "stub"]
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cost_usd: Optional[float] = None
    duration_ms: float = 0.0


class CostSummary(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    total_usd: float = 0.0
    live_calls: int = 0
    note: str = ""


class ProviderStatus(BaseModel):
    """Live diagnostics for the configured inference provider (sprint §13, Task C).

    Surfaced read-only in Settings. `connection`/`health` reflect reality: for the local
    Ollama provider they come from an actual reachability + model-presence probe; for
    hosted providers they reflect whether credentials are configured (true liveness is
    confirmed on the first answer, where the inspector shows mode=live)."""
    provider: str                       # openai | ollama | anthropic
    transport: str = ""                 # anthropic | openai-compatible
    generation_model: str = ""
    router_model: str = ""
    sql_model: str = ""
    embedding_model: str = ""           # active embedding backend label
    base_url: Optional[str] = None
    connection: Literal["connected", "disconnected", "unknown"] = "unknown"
    health: Literal["healthy", "degraded", "unavailable"] = "unavailable"
    detail: str = ""                    # one-line human-readable status
    fix: Optional[str] = None           # exact remediation command when not healthy
    offline: bool = False               # engine is in deterministic offline mode
    deployment_mode: str = ""           # informational label (Production Recommended / …)


class ProviderOption(BaseModel):
    """A selectable inference provider for the Settings selector (sprint §14)."""
    name: str                           # openai | ollama | anthropic
    label: str                          # display name
    transport: str = ""                 # anthropic | openai-compatible
    deployment_mode: str = ""           # Production Recommended / Private Local / Advanced
    description: str = ""               # one-line "what this is / when to use it"


class ProvidersResponse(BaseModel):
    """`GET /providers` — the selector's full state: what's applied vs. the env default,
    the live status of the applied provider, and the catalog of selectable options."""
    applied: str                        # the provider calls actually use right now
    default: str                        # the env/`ABA_PROVIDER` default (server-configured)
    source: Literal["override", "env"] = "env"   # is `applied` a UI override or the env default?
    overridden: bool = False
    status: ProviderStatus
    options: list[ProviderOption] = Field(default_factory=list)


class ProviderSwitchRequest(BaseModel):
    """`POST /provider` body — switch the active inference provider at runtime."""
    provider: str                       # openai | ollama | anthropic


class ProviderCheck(BaseModel):
    """One post-switch validation probe (sprint §14, Workstream 5)."""
    name: Literal["health", "routing", "generation", "embeddings"]
    status: Literal["pass", "fail", "skipped"]
    detail: str = ""
    fix: Optional[str] = None
    duration_ms: float = 0.0


class ProviderValidation(BaseModel):
    """Result of validating the active provider end-to-end: health + routing + generation +
    embeddings. `ok` is true when no check FAILED (skipped/offline checks don't fail)."""
    provider: str
    ok: bool = True
    summary: str = ""
    checks: list[ProviderCheck] = Field(default_factory=list)


class StageTiming(BaseModel):
    name: str
    duration_ms: float


class ConflictSide(BaseModel):
    """One side of a cross-source disagreement — a value, where it came from, and the
    evidence id so the conflict is fully citable."""

    evidence_id: str
    source_name: str
    citation_label: str
    value: str                                # display value, e.g. "overdue" / "2027-08-20" / "15%"
    excerpt: str = ""                         # short supporting excerpt


class Conflict(BaseModel):
    """A detected disagreement between evidence items about the same entity/attribute.
    Conflicts are REPORTED, never silently resolved — see docs/conflict-resolution.md."""

    entity: str                               # "INV-1187" / "ACM-MSA-2025" / "Acme Corporation"
    attribute: str                            # payment_status | entity_status | end_date |
                                              # penalty_percent | late_fee_percent | amount | contract_value
    sides: list[ConflictSide] = Field(default_factory=list)
    note: str = ""                            # human-readable one-liner for the trace


class CitationCheck(BaseModel):
    verified: bool
    cited_ids: list[str] = Field(default_factory=list)
    unknown_ids: list[str] = Field(default_factory=list)
    note: str = ""


class Trace(BaseModel):
    """The complete, inspectable record of how an answer was produced."""

    question: str
    languages: list[str] = Field(default_factory=lambda: ["en"])
    route: Optional[RouteDecision] = None
    notes: list[str] = Field(default_factory=list)            # orchestrator narration
    document_retrieval: Optional[DocumentRetrievalTrace] = None
    sql_executions: list[SqlExecutionTrace] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    conflicts: list[Conflict] = Field(default_factory=list)  # cross-source disagreements
    generation: dict[str, Any] = Field(default_factory=dict)
    citation_check: Optional[CitationCheck] = None
    llm_calls: list[LLMCall] = Field(default_factory=list)
    cost: Optional["CostSummary"] = None
    timings: list[StageTiming] = Field(default_factory=list)
    mode: str = "live"                                        # live | offline-cache | mixed
    safety_net: bool = False                  # did the document safety net supply evidence?


# --- Triage / structured presentation (Features sprint, items 1, 2, 5) -------
#
# Two independent user prompts shape an answer:
#   • role_instructions  — the Role/MVP prompt (persona; tone & emphasis only)
#   • case_instructions  — the Cases prompt: a user-defined ruleset that sorts the
#                          entities in an answer into three colour buckets
#                          (red/green/blue). The MEANING of each colour is whatever
#                          the user wrote — e.g. "life support → red, fever → green,
#                          stable → blue". Nothing about severity is hardcoded.
#
# Every triage row, timeline event, and table is grounded: it carries the evidence
# ids that justify it, referencing the SAME Evidence objects as the answer's
# citations. Ungrounded rows are dropped in generation — never surfaced.

TriageLevel = Literal["red", "green", "blue"]


class TriageItem(BaseModel):
    """One classified entity in the triage view, fully attributed to evidence."""

    label: str                                # entity name as grounded, e.g. "Mohammed Ben"
    level: TriageLevel                        # red | green | blue — meaning set by the Cases prompt
    summary: str                              # one-line grounded reason for the bucket
    evidence_ids: list[str] = Field(default_factory=list)   # [eN] that justify this row
    rule: Optional[str] = None                # which Cases-prompt rule matched (model's words)


class TriagePanel(BaseModel):
    """The triage view for one answer. ``defined`` is false when no Cases prompt was
    supplied (the UI then hides the panels entirely). ``legend`` echoes what each
    colour means per the user's Cases prompt so columns can be labelled truthfully."""

    defined: bool = False
    legend: dict[str, str] = Field(default_factory=dict)    # {"red": "...", "green": "...", "blue": "..."}
    items: list[TriageItem] = Field(default_factory=list)
    note: str = ""                            # e.g. "2 entities could not be classified from the evidence"


class TimelineEvent(BaseModel):
    """One dated, grounded event for the timeline visualization."""

    date: str                                 # display string exactly as grounded in the evidence
    title: str
    detail: str = ""
    evidence_ids: list[str] = Field(default_factory=list)


class AnswerTable(BaseModel):
    """A structured table extracted alongside the answer so the UI renders a real
    HTML table instead of ASCII pipes-and-dashes."""

    title: str = ""
    columns: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class AskRequest(BaseModel):
    question: str
    developer_mode: bool = True
    # "workspace" → answer only from the user's uploaded sources (a clean, isolated
    # workspace). "all" → also include the bundled sample corpus (used by the
    # evaluation suites and diagnostics, not by the product UI).
    scope: Literal["workspace", "all"] = "workspace"
    # User-configured persona, e.g. "Act as a compliance officer". Free text — roles
    # are never hardcoded. Shapes tone/emphasis/analysis only; it can never override
    # grounding, invent evidence, or bypass citations (enforced in generation).
    role_instructions: Optional[str] = None
    # User-configured triage ruleset (the "Cases prompt"). Free text — e.g. "patients
    # on life support → red, with fever → green, stable → blue". When present, the
    # answer is accompanied by a TriagePanel that sorts the entities into the user's
    # three buckets. Like the role, it can never override grounding or invent evidence.
    case_instructions: Optional[str] = None


class AskResponse(BaseModel):
    question: str
    answer: str
    insufficient: bool = False
    citations: list[Evidence] = Field(default_factory=list)
    trace: Trace
    # Structured, grounded presentation alongside the prose answer. All optional and
    # empty by default, so an answer with no Cases prompt, no dates, and no tabular
    # data is byte-identical to the pre-sprint response.
    triage: Optional[TriagePanel] = None      # populated only when case_instructions is given
    timeline: list[TimelineEvent] = Field(default_factory=list)
    tables: list[AnswerTable] = Field(default_factory=list)


class SourceInfo(BaseModel):
    name: str
    kind: SourceKind
    title: str
    description: str
    capabilities: list[str] = Field(default_factory=list)
    # "active" = connected with user data; "empty" = available but nothing uploaded yet;
    # "future" = roadmap connector shown for extensibility.
    status: Literal["active", "empty", "future"] = "active"
    details: dict[str, Any] = Field(default_factory=dict)


# --- Ingestion & inventory (runtime uploads) --------------------------------

class TableInfo(BaseModel):
    """One table detected in an uploaded (or sample) SQLite database."""

    name: str                                  # effective name (post collision-safe rename)
    original_name: Optional[str] = None        # name in the uploaded file, if renamed
    rows: int = 0
    columns: list[str] = Field(default_factory=list)


class IngestedDocumentInfo(BaseModel):
    """A PDF that has been ingested and indexed at runtime (or pre-loaded sample)."""

    name: str
    type: Literal["pdf"] = "pdf"
    origin: Literal["sample", "uploaded"] = "uploaded"
    status: Literal["indexed", "error"] = "indexed"
    chunks_indexed: int = 0
    languages: list[str] = Field(default_factory=list)
    pages: Optional[int] = None
    ingestion_ms: float = 0.0
    error: Optional[str] = None
    # Non-fatal quality note, e.g. "3 of 12 pages contained no extractable text
    # (possibly scanned images)". The document still indexes; the client is warned.
    warning: Optional[str] = None


class IngestedDatabaseInfo(BaseModel):
    """A SQLite database registered with the router (sample or uploaded)."""

    name: str
    type: Literal["sqlite"] = "sqlite"
    origin: Literal["sample", "uploaded"] = "uploaded"
    status: Literal["indexed", "error"] = "indexed"
    tables: list[TableInfo] = Field(default_factory=list)
    total_rows: int = 0
    ingestion_ms: float = 0.0
    error: Optional[str] = None


class Inventory(BaseModel):
    """Everything currently indexed — drives the Workspace source inventory."""

    documents: list[IngestedDocumentInfo] = Field(default_factory=list)
    databases: list[IngestedDatabaseInfo] = Field(default_factory=list)
    total_chunks: int = 0
    total_tables: int = 0


class IngestResult(BaseModel):
    """Response for an upload: what was ingested this request + the full inventory."""

    ok: bool = True
    documents: list[IngestedDocumentInfo] = Field(default_factory=list)
    databases: list[IngestedDatabaseInfo] = Field(default_factory=list)
    inventory: Inventory
    message: str = ""
