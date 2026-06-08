import type { AppConfig, AskResponse, ExampleQuestion, SourceInfo } from "./types";

const BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") || "http://localhost:8000";

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`GET ${path} → ${res.status}`);
  return res.json();
}

export async function fetchConfig(): Promise<AppConfig> {
  return getJSON<AppConfig>("/config");
}

export async function fetchExamples(): Promise<ExampleQuestion[]> {
  return getJSON<ExampleQuestion[]>("/examples");
}

export async function fetchSources(): Promise<SourceInfo[]> {
  return getJSON<SourceInfo[]>("/sources");
}

export async function ask(question: string): Promise<AskResponse> {
  const res = await fetch(`${BASE}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
  if (!res.ok) throw new Error(`ask → ${res.status}`);
  return res.json();
}
