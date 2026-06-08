"use client";
import React from "react";
import { ask, fetchConfig, fetchExamples, fetchSources } from "@/lib/api";
import type { AppConfig, AskResponse, ExampleQuestion, SourceInfo } from "@/lib/types";
import Result from "@/components/Result";
import { Card, Icons, Pill, RouteBadge, cn, isRTL } from "@/components/ui";

export default function Page() {
  const [config, setConfig] = React.useState<AppConfig | null>(null);
  const [examples, setExamples] = React.useState<ExampleQuestion[]>([]);
  const [sources, setSources] = React.useState<SourceInfo[]>([]);
  const [question, setQuestion] = React.useState("");
  const [resp, setResp] = React.useState<AskResponse | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [connecting, setConnecting] = React.useState(true);

  // Resilient bootstrap: retry until the engine answers (covers container warm-up).
  const bootstrap = React.useCallback(() => {
    let cancelled = false;
    let tries = 0;
    const tick = async () => {
      try {
        const c = await fetchConfig();
        if (cancelled) return;
        setConfig(c);
        setConnecting(false);
        fetchExamples().then(setExamples).catch(() => {});
        fetchSources().then(setSources).catch(() => {});
      } catch {
        if (cancelled) return;
        tries += 1;
        setConnecting(true);
        if (tries < 40) setTimeout(tick, 1500);
      }
    };
    tick();
    return () => { cancelled = true; };
  }, []);

  React.useEffect(() => bootstrap(), [bootstrap]);

  const run = async (q: string) => {
    const query = q.trim();
    if (!query) return;
    setQuestion(query);
    setLoading(true);
    setError(null);
    setResp(null);
    try {
      setResp(await ask(query));
    } catch {
      setError("Could not reach the engine. It may still be starting — retrying automatically…");
      bootstrap();
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mx-auto max-w-6xl px-4 py-7">
      {/* header */}
      <header className="mb-7 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3.5">
          <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500 to-sky-500 shadow-lg shadow-indigo-500/20 ring-1 ring-white/10">
            <Icons.layers className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="text-[22px] font-bold leading-tight tracking-tight">
              <span className="gradient-text">AI Business Knowledge Assistant</span>
            </h1>
            <p className="mt-0.5 text-sm text-slate-400">
              Multi-source retrieval &amp; orchestration · routing · hybrid retrieval · grounded answers ·{" "}
              <span className="text-slate-300">full traceability</span>
            </p>
          </div>
        </div>
        {config && (
          <div className="flex flex-wrap items-center gap-1.5">
            <Pill tone={config.mode === "live" ? "emerald" : "amber"}>
              <span className={cn("h-1.5 w-1.5 rounded-full", config.mode === "live" ? "bg-emerald-400" : "bg-amber-400")} />
              {config.mode === "live" ? `live · ${config.provider}` : "offline demo"}
            </Pill>
            <Pill tone="indigo">{config.models.generation}</Pill>
            <Pill tone="slate">embed: {config.embedding_backend.split(":").pop()}</Pill>
          </div>
        )}
      </header>

      {/* connecting banner */}
      {connecting && (
        <Card className="mb-4 flex items-center gap-3 px-4 py-3 text-sm text-slate-300">
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-600 border-t-indigo-400" />
          Connecting to the engine… (this can take a few seconds while it starts up)
        </Card>
      )}

      <div className="grid gap-6 lg:grid-cols-[330px_1fr]">
        {/* left rail */}
        <aside className="space-y-4">
          <Card className="p-4">
            <h2 className="mb-3 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">
              <Icons.bolt className="h-3.5 w-3.5 text-indigo-400/80" /> Try a question
            </h2>
            <div className="space-y-2">
              {examples.map((ex) => (
                <button key={ex.question} onClick={() => run(ex.question)}
                  className="group relative w-full overflow-hidden rounded-xl border border-white/[0.06] bg-black/20 p-3 pl-3.5 text-left transition hover:-translate-y-px hover:border-indigo-400/40 hover:bg-white/[0.03]">
                  <span className={cn("absolute inset-y-0 left-0 w-[3px] rounded-full",
                    ex.route === "PDF" ? "bg-emerald-400/70" : ex.route === "SQL" ? "bg-sky-400/70" :
                    ex.route === "HYBRID" ? "bg-indigo-400/70" : "bg-slate-500/60")} />
                  <div className="mb-1 flex items-center justify-between gap-2">
                    <span className="text-[11px] font-medium text-slate-300">{ex.label}</span>
                    <RouteBadge route={ex.route} small />
                  </div>
                  <div dir={isRTL(ex.question) ? "rtl" : "ltr"}
                    className={cn("text-[12.5px] leading-snug text-slate-400 group-hover:text-slate-200", isRTL(ex.question) && "text-right")}>
                    {ex.question}
                  </div>
                </button>
              ))}
              {examples.length === 0 && Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="shimmer h-16 rounded-xl border border-white/[0.05] bg-white/[0.02]" />
              ))}
            </div>
          </Card>

          <Card className="p-4">
            <h2 className="mb-3 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">
              <Icons.layers className="h-3.5 w-3.5 text-indigo-400/80" /> Registered sources
            </h2>
            <div className="space-y-2">
              {sources.map((s) => (
                <div key={s.name} className="rounded-xl border border-white/[0.06] bg-black/20 p-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="flex items-center gap-2 text-[12.5px] font-medium text-slate-200">
                      {s.kind === "relational" ? <Icons.db className="h-3.5 w-3.5 text-sky-300" />
                        : s.kind === "documents" ? <Icons.doc className="h-3.5 w-3.5 text-emerald-300" />
                        : <Icons.route className="h-3.5 w-3.5 text-slate-400" />}
                      {s.title}
                    </span>
                    <Pill tone={s.status === "active" ? "emerald" : "slate"}>{s.status === "active" ? s.kind : "future"}</Pill>
                  </div>
                  <p className="mt-1.5 text-[11px] leading-snug text-slate-500">{s.description}</p>
                </div>
              ))}
            </div>
            <p className="mt-3 text-[11px] leading-snug text-slate-600">
              New sources (CRM, email, cloud storage) implement one interface — the router and pipeline need no changes.
            </p>
          </Card>
        </aside>

        {/* main */}
        <main className="space-y-4">
          <Card className="p-3">
            <div className="flex items-end gap-2">
              <textarea value={question} onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) run(question); }}
                rows={2} dir={isRTL(question) ? "rtl" : "ltr"}
                placeholder="Ask across contracts (PDF) and the business database (SQLite)…  ⌘/Ctrl + Enter"
                className="min-h-[54px] flex-1 resize-y rounded-xl border border-white/[0.08] bg-black/30 px-3.5 py-2.5 text-sm text-slate-100 placeholder:text-slate-600 focus:border-indigo-400/50 focus:outline-none focus:ring-2 focus:ring-indigo-400/15" />
              <button onClick={() => run(question)} disabled={loading || !question.trim()}
                className="flex h-[54px] shrink-0 items-center gap-2 rounded-xl bg-gradient-to-br from-indigo-500 to-indigo-600 px-5 text-sm font-semibold text-white shadow-lg shadow-indigo-600/20 transition hover:from-indigo-400 hover:to-indigo-500 disabled:opacity-40">
                {loading ? <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white" /> : <Icons.spark className="h-4 w-4" />}
                {loading ? "Routing…" : "Ask"}
              </button>
            </div>
          </Card>

          {error && <Card className="px-4 py-3 text-sm text-amber-200 ring-1 ring-amber-400/30">{error}</Card>}

          {loading && (
            <Card className="p-10 text-center text-sm text-slate-400">
              <div className="mx-auto mb-3 h-7 w-7 animate-spin rounded-full border-2 border-slate-700 border-t-indigo-400" />
              <span className="text-slate-300">Routing → retrieving → grounding…</span>
            </Card>
          )}

          {!resp && !loading && (
            <Card className="p-12 text-center">
              <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-indigo-400/10 ring-1 ring-indigo-400/20">
                <Icons.spark className="h-6 w-6 text-indigo-300" />
              </div>
              <p className="text-sm text-slate-400">
                Pick an example, or ask your own. Every answer shows the full pipeline:
              </p>
              <p className="mt-1.5 text-sm font-medium text-slate-200">
                route → retrieval → evidence → grounded answer → verified citations
              </p>
            </Card>
          )}

          {resp && !loading && <Result resp={resp} />}
        </main>
      </div>

      <footer className="mt-12 border-t border-white/[0.06] pt-5 text-center text-[11px] leading-relaxed text-slate-600">
        PDF + SQLite · query routing · hybrid retrieval (dense + BM25 + RRF + rerank) · grounded generation ·
        citation verification · designed for CRM / email / cloud-storage extensibility
      </footer>
    </div>
  );
}
