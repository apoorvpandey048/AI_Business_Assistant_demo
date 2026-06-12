"use client";
import React from "react";
import type { AppConfig, SourceInfo } from "@/lib/types";
import { Button, Card, Icons, Pill, SectionTitle, cn, isRTL } from "./ui";

export default function Settings({
  role, setRole, config, sources, onReset, resetting, hasUploads,
}: {
  role: string;
  setRole: (r: string) => void;
  config: AppConfig | null;
  sources: SourceInfo[];
  onReset: () => void;
  resetting: boolean;
  hasUploads: boolean;
}) {
  const confirmReset = () => {
    if (window.confirm("Remove all sources from this workspace? This cannot be undone.")) {
      onReset();
    }
  };

  return (
    <div className="mx-auto grid max-w-5xl gap-4 lg:grid-cols-2">
      {/* ---- analysis mode (persona) ---- */}
      <Card className="p-4 lg:col-span-2">
        <SectionTitle hint={role.trim() ? "active" : "off"}>Analysis mode</SectionTitle>
        <p className="mb-2 text-[12px] leading-relaxed text-slate-500">
          Give the assistant a professional perspective for its analysis — it shapes tone and
          emphasis, never the facts. Answers always come only from your sources, with citations,
          and insufficient evidence is still declared.
        </p>
        <textarea
          value={role} onChange={(e) => setRole(e.target.value)}
          rows={2} maxLength={1500} dir={isRTL(role) ? "rtl" : "ltr"}
          placeholder='e.g. "Act as a lawyer reviewing these contracts" or "Analyze as a compliance officer"'
          className="focus-ring w-full resize-y rounded-xl border border-slate-200 bg-white px-3 py-2 text-[13px] text-slate-700 placeholder:text-slate-400" />
        {role.trim() && (
          <div className="mt-2 flex items-center gap-2">
            <Pill tone="indigo"><Icons.spark className="h-3 w-3" />applied to every question</Pill>
            <Button variant="ghost" size="sm" onClick={() => setRole("")}>
              <Icons.x className="h-3.5 w-3.5" />Turn off
            </Button>
          </div>
        )}
      </Card>

      {/* ---- engine ---- */}
      <Card className="p-4">
        <SectionTitle>Engine</SectionTitle>
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
              Model API keys are configured server-side and never reach the browser. In offline
              mode the engine answers with deterministic fallbacks — retrieval, grounding, and
              citations behave identically.
            </p>
          </div>
        ) : (
          <p className="text-[12px] text-slate-400">Connecting to the engine…</p>
        )}
      </Card>

      {/* ---- integrations ---- */}
      <Card className="p-4">
        <SectionTitle>Integrations</SectionTitle>
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
                <Pill tone={s.status === "active" ? "emerald" : "slate"}>
                  {s.status === "active" ? "connected" : "roadmap"}
                </Pill>
              </div>
              <p className="mt-1 text-[11.5px] leading-relaxed text-slate-500">{s.description}</p>
            </div>
          ))}
        </div>
        <p className="mt-2 text-[11px] leading-relaxed text-slate-400">
          New systems (CRM, email, cloud storage) connect through the same source model — once
          registered, questions route across them automatically.
        </p>
      </Card>

      {/* ---- workspace data ---- */}
      <Card className="p-4 lg:col-span-2">
        <SectionTitle>Workspace data</SectionTitle>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="max-w-xl text-[12px] leading-relaxed text-slate-500">
            Clearing the workspace removes every uploaded document and database from the index
            and deletes the uploaded files from the server. This cannot be undone.
          </p>
          <Button variant="danger" size="md" onClick={confirmReset} disabled={resetting || !hasUploads}
            title={hasUploads ? "Remove all uploaded sources" : "No uploaded sources to remove"}>
            <Icons.refresh className={cn("h-4 w-4", resetting && "animate-spin")} />
            Clear workspace
          </Button>
        </div>
      </Card>
    </div>
  );
}
