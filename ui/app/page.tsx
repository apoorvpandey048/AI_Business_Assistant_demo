"use client";
import React from "react";
import {
  ask, fetchConfig, fetchInventory, fetchSources,
  ingestPdf, ingestSqlite, resetWorkspace,
} from "@/lib/api";
import type { AppConfig, AskResponse, Inventory, SourceInfo } from "@/lib/types";
import { Icons, Tabs, cn } from "@/components/ui";
import Chat from "@/components/Chat";
import Sources from "@/components/Sources";
import Inspector from "@/components/Inspector";
import Settings from "@/components/Settings";

type TabId = "chat" | "sources" | "inspector" | "settings";

export default function Page() {
  const [config, setConfig] = React.useState<AppConfig | null>(null);
  const [sources, setSources] = React.useState<SourceInfo[]>([]);
  const [inventory, setInventory] = React.useState<Inventory | null>(null);

  const [tab, setTab] = React.useState<TabId>("chat");
  const [question, setQuestion] = React.useState("");
  const [resp, setResp] = React.useState<AskResponse | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [connecting, setConnecting] = React.useState(true);

  // User-configured analysis mode (persona), persisted locally. Sent with every ask.
  const [role, setRole] = React.useState("");
  React.useEffect(() => {
    try { setRole(window.localStorage.getItem("aba.role") || ""); } catch { /* ignore */ }
  }, []);
  const updateRole = (r: string) => {
    setRole(r);
    try { window.localStorage.setItem("aba.role", r); } catch { /* ignore */ }
  };

  // Monotonic request token: a response (or retry) from a superseded question can
  // never overwrite the state of a newer one. This was the "evidence panel shows the
  // previous question's evidence" bug — a slow/retried response landing late.
  const askSeq = React.useRef(0);

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

  const run = async (q: string) => {
    const query = q.trim();
    if (!query) return;
    const seq = ++askSeq.current;          // this request now owns the answer state
    const stale = () => seq !== askSeq.current;
    setTab("chat");
    setQuestion(query);
    setLoading(true);
    setError(null);
    setResp(null);
    for (let attempt = 0; attempt < 4; attempt++) {
      try {
        const r = await ask(query, "workspace", role);
        if (stale()) return;               // a newer question took over — drop this result
        setResp(r);
        setError(null);
        setLoading(false);
        return;
      } catch {
        if (stale()) return;
        if (attempt === 0) setError("Reaching the engine… retrying.");
        await new Promise((res) => setTimeout(res, 1200));
        if (stale()) return;
      }
    }
    if (stale()) return;
    setLoading(false);
    setError("Could not reach the engine after several tries. Please confirm the API is running.");
    bootstrap();
  };

  const refreshSources = () => {
    fetchSources().then(setSources).catch(() => {});
  };

  const clearQuestion = () => {
    askSeq.current += 1;                   // invalidate any in-flight request
    setQuestion("");
    setResp(null);
    setError(null);
    setLoading(false);
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
    askSeq.current += 1;                   // invalidate any in-flight request
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

  const uploadedDocs = (inventory?.documents ?? []).filter((d) => d.origin === "uploaded");
  const uploadedDbs = (inventory?.databases ?? []).filter((d) => d.origin === "uploaded");
  const hasUploads = uploadedDocs.length > 0 || uploadedDbs.length > 0;

  const tabs: { id: TabId; label: string; icon?: React.ReactNode }[] = [
    { id: "chat", label: "Chat", icon: <Icons.chat className="h-3.5 w-3.5" /> },
    { id: "sources", label: "Sources", icon: <Icons.layers className="h-3.5 w-3.5" /> },
    { id: "inspector", label: "Inspector", icon: <Icons.inspect className="h-3.5 w-3.5" /> },
    { id: "settings", label: "Settings", icon: <Icons.gear className="h-3.5 w-3.5" /> },
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
              <p className="text-[11px] leading-tight text-slate-400">Your knowledge workspace</p>
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

        {tab === "chat" && (
          <Chat
            inventory={inventory} role={role}
            question={question} setQuestion={setQuestion}
            onAsk={run} onClear={clearQuestion} resp={resp} loading={loading} error={error}
            onOpenInspector={() => setTab("inspector")}
            onOpenSources={() => setTab("sources")}
            onOpenSettings={() => setTab("settings")}
          />
        )}
        {tab === "sources" && (
          <Sources
            inventory={inventory}
            onUploadPdf={handlePdf} onUploadSqlite={handleSqlite} onReset={handleReset}
            pdfBusy={pdfBusy} sqliteBusy={sqliteBusy} resetting={resetting}
            pdfMsg={pdfMsg} pdfErr={pdfErr} dbMsg={dbMsg} dbErr={dbErr}
          />
        )}
        {tab === "inspector" && <Inspector resp={resp} />}
        {tab === "settings" && (
          <Settings
            role={role} setRole={updateRole} config={config} sources={sources}
            onReset={handleReset} resetting={resetting} hasUploads={hasUploads}
          />
        )}
      </main>

      <footer className="mx-auto max-w-7xl px-5 pb-8 pt-4 text-center text-[11px] leading-relaxed text-slate-400">
        Documents + databases · query routing · hybrid retrieval (dense + BM25 + RRF + rerank) ·
        grounded generation · citation verification
      </footer>
    </div>
  );
}
