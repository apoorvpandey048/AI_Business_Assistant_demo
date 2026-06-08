"use client";
import React from "react";
import { ask, fetchConfig, fetchExamples, fetchSources } from "@/lib/api";
import type { AppConfig, AskResponse, ExampleQuestion, SourceInfo } from "@/lib/types";
import Result from "@/components/Result";
import { Card, Pill, RouteBadge, cn, isRTL } from "@/components/ui";

export default function Page() {
  const [config, setConfig] = React.useState<AppConfig | null>(null);
  const [examples, setExamples] = React.useState<ExampleQuestion[]>([]);
  const [sources, setSources] = React.useState<SourceInfo[]>([]);
  const [question, setQuestion] = React.useState("");
  const [resp, setResp] = React.useState<AskResponse | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    fetchConfig().then(setConfig).catch(() => setError("Backend not reachable — is the API running on :8000?"));
    fetchExamples().then(setExamples).catch(() => {});
    fetchSources().then(setSources).catch(() => {});
  }, []);

  const run = async (q: string) => {
    const query = q.trim();
    if (!query) return;
    setQuestion(query);
    setLoading(true);
    setError(null);
    setResp(null);
    try {
      const r = await ask(query);
      setResp(r);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      {/* header */}
      <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-white">
            AI Business Knowledge Assistant
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            Multi-source retrieval &amp; orchestration — query routing · hybrid retrieval · grounded
            answers · full traceability.{" "}
            <span className="text-slate-500">Not a PDF chatbot.</span>
          </p>
        </div>
        {config && (
          <div className="flex flex-wrap items-center gap-2">
            <Pill tone={config.mode === "live" ? "emerald" : "amber"}>
              {config.mode === "live" ? `● live (${config.provider})` : "● offline demo"}
            </Pill>
            <Pill tone="indigo">gen: {config.models.generation}</Pill>
            <Pill tone="sky">router: {config.models.router}</Pill>
            <Pill>embed: {config.embedding_backend.split(":").pop()}</Pill>
            <Pill>vector: {config.vector_backend}</Pill>
          </div>
        )}
      </header>

      <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
        {/* left: examples + sources */}
        <aside className="space-y-4">
          <Card className="p-4">
            <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-400">
              Try a question
            </h2>
            <div className="space-y-2">
              {examples.map((ex) => (
                <button
                  key={ex.question}
                  onClick={() => run(ex.question)}
                  className="group w-full rounded-lg border border-slate-800 bg-slate-950/40 p-2.5 text-left transition hover:border-indigo-500/50 hover:bg-slate-900"
                >
                  <div className="mb-1 flex items-center justify-between gap-2">
                    <span className="text-[11px] font-medium text-slate-300">{ex.label}</span>
                    <RouteBadge route={ex.route} small />
                  </div>
                  <div
                    dir={isRTL(ex.question) ? "rtl" : "ltr"}
                    className={cn(
                      "text-[12px] text-slate-400 group-hover:text-slate-200",
                      isRTL(ex.question) && "text-right"
                    )}
                  >
                    {ex.question}
                  </div>
                </button>
              ))}
            </div>
          </Card>

          <Card className="p-4">
            <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-400">
              Registered sources
            </h2>
            <div className="space-y-2">
              {sources.map((s) => (
                <div key={s.name} className="rounded-lg border border-slate-800 bg-slate-950/40 p-2.5">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[12px] font-medium text-slate-200">{s.title}</span>
                    <Pill tone={s.status === "active" ? "emerald" : "slate"}>
                      {s.status === "active" ? s.kind : "future"}
                    </Pill>
                  </div>
                  <p className="mt-1 text-[11px] text-slate-500">{s.description}</p>
                </div>
              ))}
            </div>
            <p className="mt-3 text-[11px] text-slate-600">
              New sources (CRM, email, cloud storage) implement one interface — the router and
              pipeline need no changes.
            </p>
          </Card>
        </aside>

        {/* right: ask + result */}
        <main className="space-y-4">
          <Card className="p-3">
            <div className="flex items-end gap-2">
              <textarea
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) run(question);
                }}
                rows={2}
                dir={isRTL(question) ? "rtl" : "ltr"}
                placeholder="Ask across contracts (PDF) and the business database (SQLite)…  (⌘/Ctrl+Enter)"
                className="min-h-[52px] flex-1 resize-y rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-600 focus:border-indigo-500/60 focus:outline-none"
              />
              <button
                onClick={() => run(question)}
                disabled={loading || !question.trim()}
                className="h-[52px] shrink-0 rounded-lg bg-indigo-500 px-5 text-sm font-semibold text-white transition hover:bg-indigo-400 disabled:opacity-40"
              >
                {loading ? "Routing…" : "Ask"}
              </button>
            </div>
          </Card>

          {error && (
            <Card className="border-rose-500/40 p-4 text-sm text-rose-300">{error}</Card>
          )}

          {loading && (
            <Card className="p-8 text-center text-sm text-slate-400">
              <div className="mx-auto mb-3 h-6 w-6 animate-spin rounded-full border-2 border-slate-700 border-t-indigo-400" />
              Routing → retrieving → grounding…
            </Card>
          )}

          {!resp && !loading && !error && (
            <Card className="p-8 text-center text-sm text-slate-500">
              Pick an example on the left, or ask your own question. Every answer shows the full
              pipeline: <span className="text-slate-300">route → retrieval → evidence → grounded
              answer → verified citations</span>.
            </Card>
          )}

          {resp && !loading && <Result resp={resp} />}
        </main>
      </div>

      <footer className="mt-10 border-t border-slate-800 pt-4 text-center text-[11px] text-slate-600">
        PDF + SQLite · query routing · hybrid retrieval (dense + BM25 + RRF + rerank) · grounded
        generation · citation verification · designed for CRM / email / cloud-storage extensibility.
      </footer>
    </div>
  );
}
