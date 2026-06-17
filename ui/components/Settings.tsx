"use client";
import React from "react";
import type { AppConfig, SourceInfo } from "@/lib/types";
import { roleLabel } from "@/lib/role";
import type { PromptKind } from "@/lib/prompt";
import { useTheme } from "@/lib/theme";
import { Button, Card, Icons, Pill, SectionTitle, Switch, cn } from "./ui";
import ProviderSettings from "./ProviderSettings";
import type { ToastItem } from "./ui";

/* A light, plain-language heading that groups several cards together (item 5:
   "settings should be extremely simple and understandable"). */
function GroupHeader({ children, hint }: { children: React.ReactNode; hint?: string }) {
  return (
    <div className="lg:col-span-2 -mb-1 mt-1 first:mt-0">
      <h2 className="text-[13px] font-semibold text-text-strong">{children}</h2>
      {hint && <p className="mt-0.5 text-[12px] leading-relaxed text-text-muted">{hint}</p>}
    </div>
  );
}

export default function Settings({
  role, cases,
  config, sources, onReset, resetting, hasUploads,
  onOpenSources, onEditPrompt, pushToast, onRefreshConfig,
}: {
  role: string;                       // the SAVED role — the one applied to questions
  cases: string;                      // the SAVED case rules — applied to questions
  config: AppConfig | null;
  sources: SourceInfo[];
  onReset: () => void;
  resetting: boolean;
  hasUploads: boolean;
  onOpenSources: () => void;
  onEditPrompt: (kind: PromptKind) => void;   // jump to the prompt bar (Chat tab)
  pushToast: (message: string, tone?: ToastItem["tone"]) => void;
  onRefreshConfig: () => void;        // refresh /config after a provider switch (top-bar)
}) {
  const [theme, setTheme] = useTheme();
  const confirmReset = () => {
    if (window.confirm(
      "Remove all uploaded sources and clear the current conversation?\n\n" +
      "Your analysis mode and case rules are preferences and will be kept — clear " +
      "them separately above if you want a full reset.\n\nThis cannot be undone."
    )) {
      onReset();
    }
  };

  const connected = sources.filter((s) => s.status === "active").length;

  return (
    <div className="mx-auto grid max-w-5xl gap-4 lg:grid-cols-2">

      {/* ============ 1 · How it answers ============ */}
      <GroupHeader hint="Optional instructions you write once. They shape how the assistant responds — never the facts. Answers always come only from your sources, with citations.">
        How it answers
      </GroupHeader>

      {/* Prompts now live in the bar above the question (single source of truth).
          Settings shows a read-only summary + a deep link to edit them there. */}
      <Card className="p-4 lg:col-span-2">
        <SectionTitle hint="edited above the question">Your prompts</SectionTitle>
        <div className="space-y-2.5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="flex items-center gap-1.5 text-[12.5px] text-text-muted">
              <Icons.spark className="h-3.5 w-3.5 text-accent" />Analysis mode
            </span>
            {role.trim()
              ? <Pill tone="emerald"><Icons.check className="h-3 w-3" />{roleLabel(role)}</Pill>
              : <Pill tone="slate">General</Pill>}
            <Button variant="ghost" size="sm" className="ml-auto" onClick={() => onEditPrompt("role")}>
              <Icons.chevron className="h-3.5 w-3.5" />Edit above the question
            </Button>
          </div>
          <div className="flex flex-wrap items-center gap-2 border-t border-line pt-2.5">
            <span className="flex items-center gap-1.5 text-[12.5px] text-text-muted">
              <Icons.grid className="h-3.5 w-3.5 text-accent" />Triage rules
            </span>
            {cases.trim()
              ? <Pill tone="emerald"><Icons.check className="h-3 w-3" />On</Pill>
              : <Pill tone="slate">Off</Pill>}
            <Button variant="ghost" size="sm" className="ml-auto" onClick={() => onEditPrompt("cases")}>
              <Icons.chevron className="h-3.5 w-3.5" />Edit above the question
            </Button>
          </div>
        </div>
        <p className="mt-2.5 text-[11px] leading-relaxed text-text-faint">
          Both are saved in this browser and applied to every question until you clear them.
          Edit them from the bar that sits directly above the chat input.
        </p>
      </Card>

      {/* ---- appearance (theme) ---- */}
      <Card className="p-4 lg:col-span-2">
        <SectionTitle>Appearance</SectionTitle>
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-2 text-[12.5px] text-text-muted">
            {theme === "dark" ? <Icons.moon className="h-4 w-4 text-accent" /> : <Icons.sun className="h-4 w-4 text-accent" />}
            Dark mode
          </span>
          <Switch checked={theme === "dark"} onChange={(v) => setTheme(v ? "dark" : "light")} label="Toggle dark mode" />
        </div>
        <p className="mt-2 text-[11px] leading-relaxed text-text-faint">
          Follows your system setting until you choose here; your choice is saved in this browser.
        </p>
      </Card>

      {/* ============ 2 · Engine & provider ============ */}
      <GroupHeader hint="Which model answers, and the retrieval engine behind it.">
        Engine &amp; provider
      </GroupHeader>

      {/* ---- AI provider — selector, status, validation (sprint §14) ---- */}
      <ProviderSettings pushToast={pushToast} onApplied={onRefreshConfig} />

      {/* ---- engine ---- */}
      <Card className="p-4">
        <SectionTitle hint="read-only — configured server-side">Engine</SectionTitle>
        {config ? (
          <div className="space-y-2 text-[12.5px] text-slate-600">
            <div className="flex items-center justify-between">
              <span className="text-slate-500">Mode</span>
              <Pill tone={config.mode === "live" ? "emerald" : "amber"}>
                <span className={cn("h-1.5 w-1.5 rounded-full", config.mode === "live" ? "bg-emerald-500" : "bg-amber-500")} />
                {config.mode === "live" ? `Live · ${config.provider}` : "Offline (deterministic)"}
              </Pill>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-500">Generation model</span>
              <span className="font-mono text-[11.5px]">{config.models.generation}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-500">Router model</span>
              <span className="font-mono text-[11.5px]">{config.models.router}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-500">SQL model</span>
              <span className="font-mono text-[11.5px]">{config.models.sql}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-500">Embeddings</span>
              <span className="font-mono text-[11.5px]">{config.embedding_backend}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-500">Vector store</span>
              <span className="font-mono text-[11.5px]">{config.vector_backend}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-500">Reranker</span>
              <span className="font-mono text-[11.5px]">{config.reranker_backend}</span>
            </div>
            <p className="pt-1 text-[11px] leading-relaxed text-slate-400">
              These values show what is actually running right now. Model API keys are
              configured server-side and never reach the browser. In offline mode the engine
              answers with deterministic fallbacks — retrieval, grounding, and citations
              behave identically.
            </p>
          </div>
        ) : (
          <p className="text-[12px] text-slate-400">Connecting to the engine…</p>
        )}
      </Card>

      {/* ============ 3 · Workspace ============ */}
      <GroupHeader hint="The sources your answers come from, and how to clear them.">
        Workspace
      </GroupHeader>

      {/* ---- connected sources ---- */}
      <Card className="p-4">
        <SectionTitle hint={`${connected} connected`}>Connected sources</SectionTitle>
        <div className="space-y-2">
          {sources.map((s) => (
            <div key={s.name} className="rounded-xl border border-slate-200 bg-white p-3">
              <div className="flex items-center justify-between gap-2">
                <span className="flex items-center gap-2 text-[12.5px] font-medium text-slate-700">
                  {s.kind === "documents" ? <Icons.doc className="h-3.5 w-3.5 text-emerald-500" />
                    : s.kind === "relational" ? <Icons.db className="h-3.5 w-3.5 text-sky-500" />
                    : <Icons.bolt className="h-3.5 w-3.5 text-slate-400" />}
                  {s.title}
                </span>
                {s.status === "active" ? (
                  <Pill tone="emerald"><Icons.check className="h-3 w-3" />connected</Pill>
                ) : s.status === "empty" ? (
                  <Pill tone="slate">not connected</Pill>
                ) : (
                  <Pill tone="slate">roadmap</Pill>
                )}
              </div>
              <p className="mt-1 text-[11.5px] leading-relaxed text-slate-500">{s.description}</p>
              {s.status === "empty" && (
                <button onClick={onOpenSources}
                  className="mt-1.5 inline-flex items-center gap-1 text-[11.5px] font-medium text-indigo-600 hover:text-indigo-700">
                  <Icons.plus className="h-3 w-3" />Add in Sources
                </button>
              )}
            </div>
          ))}
        </div>
        <p className="mt-2 text-[11px] leading-relaxed text-slate-400">
          Answers come only from connected sources. New systems (CRM, email, cloud storage)
          connect through the same source model.
        </p>
      </Card>

      {/* ---- workspace data ---- */}
      <Card className="p-4">
        <SectionTitle>Reset</SectionTitle>
        <p className="mb-3 text-[12px] leading-relaxed text-slate-500">
          Removes every uploaded document and database from the index, deletes the uploaded
          files from the server, and clears the current conversation and Inspector trace.
          Your analysis mode and case rules are kept. This cannot be undone.
        </p>
        <Button variant="danger" size="md" onClick={confirmReset} disabled={resetting || !hasUploads}
          title={hasUploads ? "Remove all uploaded sources" : "No uploaded sources to remove"}>
          <Icons.refresh className={cn("h-4 w-4", resetting && "animate-spin")} />
          Clear workspace
        </Button>
        {!hasUploads && (
          <p className="mt-2 text-[11px] text-slate-400">
            Nothing to clear — your workspace has no uploaded sources.
          </p>
        )}
      </Card>
    </div>
  );
}
