import type { AppConfig, AskResponse, ExampleQuestion, SourceInfo } from "./types";

// Derive the API base from the host the browser is actually using, so the app works
// whether opened via localhost, the WSL IP, or any machine IP (the API is on :8000).
// Falls back to the build-time env (or localhost) during SSR.
function apiBase(): string {
  if (typeof window !== "undefined" && window.location?.hostname) {
    return `${window.location.protocol}//${window.location.hostname}:8000`;
  }
  return process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") || "http://localhost:8000";
}

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${apiBase()}${path}`, { cache: "no-store" });
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
  const res = await fetch(`${apiBase()}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
  if (!res.ok) throw new Error(`ask → ${res.status}`);
  return res.json();
}
