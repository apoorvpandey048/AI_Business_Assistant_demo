import type {
  AppConfig, AskResponse, IngestResult, Inventory, ProvidersResponse,
  ProviderValidation, SourceInfo,
} from "./types";

// All API calls go through the UI's own origin at /api/*, which the Next server proxies
// to the backend (see next.config.js rewrites). One origin → works on localhost, a LAN
// IP, or behind a single public URL (Cloudflare tunnel) with no CORS and no extra port.
function apiBase(): string {
  return "/api";
}

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${apiBase()}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`GET ${path} → ${res.status}`);
  return res.json();
}

export async function fetchConfig(): Promise<AppConfig> {
  return getJSON<AppConfig>("/config");
}

export async function fetchSources(): Promise<SourceInfo[]> {
  return getJSON<SourceInfo[]>("/sources");
}

export async function fetchInventory(): Promise<Inventory> {
  return getJSON<Inventory>("/inventory");
}

// "workspace" answers only from the user's uploaded sources; "all" additionally
// includes the bundled evaluation corpus (diagnostics only — never used by the UI).
export type AskScope = "workspace" | "all";

export async function ask(
  question: string, scope: AskScope = "workspace",
  roleInstructions?: string, caseInstructions?: string,
): Promise<AskResponse> {
  const role = (roleInstructions || "").trim();
  const cases = (caseInstructions || "").trim();
  const res = await fetch(`${apiBase()}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question, scope,
      ...(role ? { role_instructions: role } : {}),
      ...(cases ? { case_instructions: cases } : {}),
    }),
  });
  if (!res.ok) throw new Error(`ask → ${res.status}`);
  return res.json();
}

/* ---------------- streaming ask (Phase 7) ----------------
 * Consumes the SSE /ask/stream endpoint. Calls onStage as the pipeline advances,
 * onToken as the (already server-verified) answer is progressively revealed, and
 * resolves with the final complete AskResponse. The caller should fall back to the
 * non-streaming ask() on any rejection (offline / no-live-LLM / network). */
export interface StreamHandlers {
  onStage?: (stage: string) => void;
  onToken?: (text: string) => void;
}

export async function askStream(
  question: string, scope: AskScope = "workspace",
  roleInstructions: string | undefined, caseInstructions: string | undefined,
  handlers: StreamHandlers = {}, signal?: AbortSignal,
): Promise<AskResponse> {
  const role = (roleInstructions || "").trim();
  const cases = (caseInstructions || "").trim();
  const res = await fetch(`${apiBase()}/ask/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question, scope,
      ...(role ? { role_instructions: role } : {}),
      ...(cases ? { case_instructions: cases } : {}),
    }),
    signal,
  });
  if (!res.ok || !res.body) throw new Error(`ask/stream → ${res.status}`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let final: AskResponse | null = null;
  let errorDetail: string | null = null;

  // Parse the SSE byte stream into event/data frames separated by a blank line.
  const handleFrame = (frame: string) => {
    let event = "message";
    const dataLines: string[] = [];
    for (const line of frame.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
    }
    if (!dataLines.length) return;
    let data: any;
    try { data = JSON.parse(dataLines.join("\n")); } catch { return; }
    if (event === "stage") handlers.onStage?.(data.stage);
    else if (event === "token") handlers.onToken?.(data.text ?? "");
    else if (event === "final") final = data as AskResponse;
    else if (event === "error") errorDetail = data.detail || "stream error";
  };

  // eslint-disable-next-line no-constant-condition
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      handleFrame(frame);
    }
  }
  if (buffer.trim()) handleFrame(buffer);

  if (errorDetail) throw new Error(errorDetail);
  if (!final) throw new Error("stream ended without a final answer");
  return final;
}

async function postFiles(path: string, files: File[]): Promise<IngestResult> {
  const form = new FormData();
  for (const f of files) form.append("files", f, f.name);
  const res = await fetch(`${apiBase()}${path}`, { method: "POST", body: form });
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      const j = await res.json();
      if (j?.detail) detail = j.detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json();
}

export async function ingestPdf(files: File[]): Promise<IngestResult> {
  return postFiles("/ingest/pdf", files);
}

export async function ingestSqlite(files: File[]): Promise<IngestResult> {
  return postFiles("/ingest/sqlite", files);
}

export async function resetWorkspace(): Promise<Inventory> {
  const res = await fetch(`${apiBase()}/reset`, { method: "POST" });
  if (!res.ok) throw new Error(`reset → ${res.status}`);
  return res.json();
}

/* ---------------- provider selection (sprint §14) ---------------- */

export async function fetchProviders(): Promise<ProvidersResponse> {
  return getJSON<ProvidersResponse>("/providers");
}

async function postJSON<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${apiBase()}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      const j = await res.json();
      if (j?.detail) detail = j.detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json();
}

// Switch the active inference provider (persisted server-side, reload-safe).
export async function switchProvider(provider: string): Promise<ProvidersResponse> {
  return postJSON<ProvidersResponse>("/provider", { provider });
}

// Revert to the server-configured (env/ABA_PROVIDER) default.
export async function useDefaultProvider(): Promise<ProvidersResponse> {
  return postJSON<ProvidersResponse>("/provider/default");
}

// Validate the active provider end to end (health / routing / generation / embeddings).
export async function validateProvider(): Promise<ProviderValidation> {
  return postJSON<ProviderValidation>("/provider/validate");
}
