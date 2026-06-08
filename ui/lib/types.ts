// Mirrors the backend Pydantic models (app/models.py).

export type Route = "PDF" | "SQL" | "HYBRID" | "NONE";
export type SourceKind = "documents" | "relational" | "api";

export interface Evidence {
  id: string;
  source_name: string;
  source_kind: SourceKind;
  content: string;
  citation_label: string;
  score?: number | null;
  language?: string | null;
  document?: string | null;
  page?: number | null;
  chunk_id?: string | null;
  section?: string | null;
  table?: string | null;
  row_ids?: unknown[] | null;
  sql?: string | null;
  columns?: string[] | null;
}

export interface RetrievalCandidate {
  chunk_id: string;
  document: string;
  page?: number | null;
  section?: string | null;
  language?: string | null;
  snippet: string;
  dense_rank?: number | null;
  dense_score?: number | null;
  bm25_rank?: number | null;
  bm25_score?: number | null;
  rrf_score?: number | null;
  rerank_score?: number | null;
  final_rank?: number | null;
  selected: boolean;
}

export interface DocumentRetrievalTrace {
  query: string;
  filters: Record<string, unknown>;
  embedding_backend: string;
  reranker_backend: string;
  params: Record<string, unknown>;
  candidates: RetrievalCandidate[];
}

export interface SqlExecutionTrace {
  purpose: string;
  natural_language: string;
  generated_sql: string;
  validated_sql?: string | null;
  valid: boolean;
  validation_error?: string | null;
  columns: string[];
  rows: Record<string, unknown>[];
  row_count: number;
  tables: string[];
  duration_ms: number;
}

export interface RouteDecision {
  route: Route;
  reasoning: string;
  confidence: number;
  languages: string[];
  document_subquery?: string | null;
  sql_subquery?: string | null;
  entity_hint?: string | null;
  agentic: boolean;
  strategy_note?: string | null;
}

export interface LLMCall {
  purpose: string;
  model: string;
  mode: "live" | "cached" | "stub";
  input_tokens?: number | null;
  output_tokens?: number | null;
  cost_usd?: number | null;
  duration_ms: number;
}

export interface CostSummary {
  input_tokens: number;
  output_tokens: number;
  total_usd: number;
  live_calls: number;
  note: string;
}

export interface CitationCheck {
  verified: boolean;
  cited_ids: string[];
  unknown_ids: string[];
  note: string;
}

export interface Trace {
  question: string;
  languages: string[];
  route?: RouteDecision | null;
  notes: string[];
  document_retrieval?: DocumentRetrievalTrace | null;
  sql_executions: SqlExecutionTrace[];
  evidence: Evidence[];
  generation: Record<string, unknown>;
  citation_check?: CitationCheck | null;
  llm_calls: LLMCall[];
  cost?: CostSummary | null;
  timings: { name: string; duration_ms: number }[];
  mode: string;
}

export interface AskResponse {
  question: string;
  answer: string;
  insufficient: boolean;
  citations: Evidence[];
  trace: Trace;
}

export interface ExampleQuestion {
  label: string;
  question: string;
  route: Route;
  why: string;
  language: string;
}

export interface SourceInfo {
  name: string;
  kind: SourceKind;
  title: string;
  description: string;
  capabilities: string[];
  status: "active" | "future";
  details: Record<string, unknown>;
}

export interface AppConfig {
  mode: string;
  models: { generation: string; router: string; sql: string };
  embedding_backend: string;
  vector_backend: string;
  reranker_backend: string;
  has_api_key: boolean;
}
