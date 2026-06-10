"use client";
import React from "react";
import {
  ask, fetchConfig, fetchExamples, fetchInventory, fetchSources,
  ingestPdf, ingestSqlite, resetWorkspace, type AskScope,
} from "@/lib/api";
import type {
  AppConfig, AskResponse, ExampleQuestion, Inventory, SourceInfo,
} from "@/lib/types";
import { Icons, Tabs, cn } from "@/components/ui";
import Workspace from "@/components/Workspace";
import Inspector from "@/components/Inspector";
import Demo from "@/components/Demo";

type TabId = "workspace" | "inspector" | "demo";

export default function Page() {
  const [config, setConfig] = React.useState<AppConfig | null>(null);
  const [examples, setExamples] = React.useState<ExampleQuestion[]>([]);
  const [sources, setSources] = React.useState<SourceInfo[]>([]);
  const [inventory, setInventory] = React.useState<Inventory | null>(null);

  const [tab, setTab] = React.useState<TabId>("workspace");
  const [question, setQuestion] = React.useState("");
  const [resp, setResp] = React.useState<AskResponse | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [connecting, setConnecting] = React.useState(true);

  // upload state
  const [pdfBusy, setPdfBusy] = React.useState(false);
  const [sqliteBusy, setSqliteBusy] = React.useState(false);
  const [resetting, setResetting] = React.useState(false);
  const [pdfMsg, setPdfMsg] = React.useState<string | null>(null);
  const [pdfErr, setPdfErr] = React.useState<string | null>(null);
  const [dbMsg, setDbMsg] = React.useState<string | null>(null);
  const [dbErr, setDbErr] = React.useState<string | null>(null);

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
        fetchInventory().then(setInventory).catch(() => {});
      } catch {
        if (cancelled) return;
        tries += 1;
        setConnecting(true);
        if (tries < 80) setTimeout(tick, 700);
      }
    };
    tick();
    return () => { cancelled = true; };
  }, []);

  React.useEffect(() => bootstrap(), [bootstrap]);

  const run = async (q: string, scope: AskScope = "workspace") => {
    const query = q.trim();
    if (!query) return;
    setTab("workspace");
    setQuestion(query);
    setLoading(true);
    setError(null);
    setResp(null);
    for (let attempt = 0; attempt < 4; attempt++) {
      try {
        const r = await ask(query, scope);
        setResp(r);
        setError(null);
        setLoading(false);
        return;
      } catch {
        if (attempt === 0) setError("Reaching the engine… retrying.");
        await new Promise((res) => setTimeout(res, 1200));
      }
    }
    setLoading(false);
    setError("Could not reach the engine after several tries. Please confirm the API is running.");
    bootstrap();
  };

  const refreshSources = () => {
    fetchSources().then(setSources).catch(() => {});
  };

  const clearQuestion = () => {
    setQuestion("");
    setResp(null);
    setError(null);
  };

  const handlePdf = async (files: File[]) => {
    setPdfBusy(true); setPdfMsg(null); setPdfErr(null);
    try {
      const res = await ingestPdf(files);
      setInventory(res.inventory);
      const failed = res.documents.filter((d) => d.status === "error");
      if (failed.length) setPdfErr(failed.map((f) => `${f.name}: ${f.error || "failed"}`).join("; "));
      else setPdfMsg(res.message);
      refreshSources();
    } catch (e: any) {
      setPdfErr(e?.message || "Upload failed.");
    } finally {
      setPdfBusy(false);
    }
  };

  const handleSqlite = async (files: File[]) => {
    setSqliteBusy(true); setDbMsg(null); setDbErr(null);
    try {
      const res = await ingestSqlite(files);
      setInventory(res.inventory);
      const failed = res.databases.filter((d) => d.status === "error");
      if (failed.length) setDbErr(failed.map((f) => `${f.name}: ${f.error || "failed"}`).join("; "));
      else setDbMsg(res.message);
      refreshSources();
    } catch (e: any) {
      setDbErr(e?.message || "Upload failed.");
    } finally {
      setSqliteBusy(false);
    }
  };

  const handleReset = async () => {
    setResetting(true);
    try {
      const inv = await resetWorkspace();
      setInventory(inv);
      setResp(null); setQuestion(""); setError(null);
      setPdfMsg(null); setPdfErr(null); setDbMsg(null); setDbErr(null);
      refreshSources();
    } catch {
      /* ignore */
    } finally {
      setResetting(false);
    }
  };

  const tabs: { id: TabId; label: string; icon?: React.ReactNode }[] = [
    { id: "workspace", label: "Workspace", icon: <Icons.grid className="h-3.5 w-3.5" /> },
    { id: "inspector", label: "Inspector", icon: <Icons.inspect className="h-3.5 w-3.5" /> },
    { id: "demo", label: "Demo", icon: <Icons.play className="h-3.5 w-3.5" /> },
  ];

  return (
    <div className="min-h-screen">
      {/* ---- top app bar ---- */}
      <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/85 backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-4 gap-y-3 px-5 py-3">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-600 text-white shadow-sm">
              <Icons.layers className="h-5 w-5" />
            </div>
            <div>
              <h1 className="text-[15px] font-bold leading-tight text-slate-900">AI Business Assistant</h1>
              <p className="text-[11px] leading-tight text-slate-400">Multi-source retrieval &amp; orchestration</p>
            </div>
          </div>

          <div className="order-3 w-full sm:order-2 sm:mx-auto sm:w-auto">
            <Tabs tabs={tabs} active={tab} onChange={setTab} />
          </div>

          <div className="order-2 ml-auto flex items-center gap-1.5 sm:order-3">
            {config && (
              <>
                <span className="inline-flex items-center gap-1.5 rounded-md bg-slate-50 px-2 py-1 text-[11px] font-medium text-slate-600 ring-1 ring-inset ring-slate-200">
                  <span className={cn("h-1.5 w-1.5 rounded-full", config.mode === "live" ? "bg-emerald-500" : "bg-amber-500")} />
                  {config.mode === "live" ? `Live · ${config.provider}` : "Offline"}
                </span>
                <span className="hidden items-center rounded-md bg-slate-50 px-2 py-1 text-[11px] font-medium text-slate-600 ring-1 ring-inset ring-slate-200 md:inline-flex">
                  {config.models.generation}
                </span>
              </>
            )}
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-5 py-6">
        {connecting && (
          <div className="mb-4 flex items-center gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 text-[13px] text-slate-500 shadow-sm">
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-200 border-t-indigo-500" />
            Connecting to the engine… (this can take a few seconds while it starts up)
          </div>
        )}

        {tab === "workspace" && (
          <Workspace
            inventory={inventory}
            question={question} setQuestion={setQuestion}
            onAsk={run} onClear={clearQuestion} resp={resp} loading={loading} error={error}
            onOpenInspector={() => setTab("inspector")}
            onUploadPdf={handlePdf} onUploadSqlite={handleSqlite} onReset={handleReset}
            pdfBusy={pdfBusy} sqliteBusy={sqliteBusy} resetting={resetting}
            pdfMsg={pdfMsg} pdfErr={pdfErr} dbMsg={dbMsg} dbErr={dbErr}
          />
        )}
        {tab === "inspector" && <Inspector resp={resp} />}
        {tab === "demo" && (
          <Demo examples={examples} sources={sources} config={config} inventory={inventory}
            onRun={(q) => run(q, "demo")} />
        )}
      </main>

      <footer className="mx-auto max-w-7xl px-5 pb-8 pt-4 text-center text-[11px] leading-relaxed text-slate-400">
        PDF + SQLite · query routing · hybrid retrieval (dense + BM25 + RRF + rerank) · grounded generation ·
        citation verification
      </footer>
    </div>
  );
}
