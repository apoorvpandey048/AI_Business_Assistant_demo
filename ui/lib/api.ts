import type {
  AppConfig, AskResponse, IngestResult, Inventory, SourceInfo,
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
  question: string, scope: AskScope = "workspace", roleInstructions?: string,
): Promise<AskResponse> {
  const role = (roleInstructions || "").trim();
  const res = await fetch(`${apiBase()}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, scope, ...(role ? { role_instructions: role } : {}) }),
  });
  if (!res.ok) throw new Error(`ask → ${res.status}`);
  return res.json();
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
