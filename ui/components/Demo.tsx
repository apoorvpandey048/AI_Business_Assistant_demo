"use client";
import React from "react";
import type { AppConfig, ExampleQuestion, Inventory, SourceInfo } from "@/lib/types";
import { Card, Icons, Pill, RouteBadge, SectionTitle, cn, isRTL } from "./ui";

export default function Demo({
  examples, sources, config, inventory, onRun,
}: {
  examples: ExampleQuestion[];
  sources: SourceInfo[];
  config: AppConfig | null;
  inventory: Inventory | null;
  onRun: (q: string) => void;
}) {
  const sampleDocs = (inventory?.documents ?? []).filter((d) => d.origin === "sample");
  const sampleDbs = (inventory?.databases ?? []).filter((d) => d.origin === "sample");
  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
      {/* curated scenarios */}
      <div className="space-y-4">
        <Card className="p-4">
          <SectionTitle hint="click any card to run it in the Workspace">Guided demo scenarios</SectionTitle>
          <p className="mb-3 text-[13px] leading-relaxed text-slate-500">
            Pre-built questions over the bundled sample contracts and business database — each chosen to
            show a different capability of the engine: pure SQL, document retrieval, keyword precision, the
            agentic hybrid flow, bilingual retrieval, and honest grounding.
          </p>
          <div className="grid gap-2.5 sm:grid-cols-2">
            {examples.map((ex) => (
              <button key={ex.question} onClick={() => onRun(ex.question)}
                className="group relative overflow-hidden rounded-xl border border-slate-200 bg-white p-3.5 pl-4 text-left transition hover:border-indigo-300 hover:shadow-sm">
                <span className={cn("absolute inset-y-0 left-0 w-[3px]",
                  ex.route === "PDF" ? "bg-emerald-400" : ex.route === "SQL" ? "bg-sky-400" :
                  ex.route === "HYBRID" ? "bg-indigo-400" : "bg-slate-300")} />
                <div className="mb-1.5 flex items-center justify-between gap-2">
                  <span className="text-[12px] font-semibold text-slate-700">{ex.label}</span>
                  <RouteBadge route={ex.route} small />
                </div>
                <div dir={isRTL(ex.question) ? "rtl" : "ltr"}
                  className={cn("text-[13px] font-medium leading-snug text-slate-700", isRTL(ex.question) && "text-right")}>
                  {ex.question}
                </div>
                <div className="mt-1.5 text-[11.5px] leading-snug text-slate-400">{ex.why}</div>
              </button>
            ))}
            {examples.length === 0 && Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="h-24 animate-pulse rounded-xl border border-slate-200 bg-slate-50" />
            ))}
          </div>
        </Card>
      </div>

      {/* sample sources + context */}
      <aside className="space-y-4">
        <Card className="p-4">
          <SectionTitle>Registered sources</SectionTitle>
          <div className="space-y-2">
            {sources.map((s) => (
              <div key={s.name} className="rounded-xl border border-slate-200 bg-white p-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="flex items-center gap-2 text-[12.5px] font-medium text-slate-700">
                    {s.kind === "relational" ? <Icons.db className="h-3.5 w-3.5 text-sky-500" />
                      : s.kind === "documents" ? <Icons.doc className="h-3.5 w-3.5 text-emerald-500" />
                      : <Icons.route className="h-3.5 w-3.5 text-slate-400" />}
                    {s.title}
                  </span>
                  <Pill tone={s.status === "active" ? "emerald" : "slate"}>
                    {s.status === "active" ? s.kind : "future"}
                  </Pill>
                </div>
                <p className="mt-1.5 text-[11.5px] leading-snug text-slate-500">{s.description}</p>
              </div>
            ))}
          </div>
          <p className="mt-3 text-[11px] leading-snug text-slate-400">
            New sources (CRM, email, cloud storage) implement one interface — the router and pipeline
            need no changes.
          </p>
        </Card>

        {(sampleDocs.length > 0 || sampleDbs.length > 0) && (
          <Card className="p-4">
            <SectionTitle hint={`${sampleDocs.length} docs · ${sampleDbs.length} db`}>Sample data</SectionTitle>
            <p className="mb-2.5 text-[11.5px] leading-snug text-slate-500">
              Preloaded for these scenarios. Kept separate from your Workspace — your own uploads are
              never mixed with this.
            </p>
            <div className="space-y-1.5">
              {sampleDocs.map((d) => (
                <div key={d.name} className="flex items-center justify-between gap-2 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5">
                  <span className="flex min-w-0 items-center gap-1.5 text-[11.5px] text-slate-700">
                    <Icons.doc className="h-3.5 w-3.5 shrink-0 text-emerald-500" />
                    <span className="truncate" title={d.name}>{d.name}</span>
                  </span>
                  <span className="shrink-0 text-[10.5px] text-slate-400">{d.chunks_indexed} chunks</span>
                </div>
              ))}
              {sampleDbs.map((d) => (
                <div key={d.name} className="flex items-center justify-between gap-2 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5">
                  <span className="flex min-w-0 items-center gap-1.5 text-[11.5px] text-slate-700">
                    <Icons.db className="h-3.5 w-3.5 shrink-0 text-sky-500" />
                    <span className="truncate" title={d.name}>{d.name}</span>
                  </span>
                  <span className="shrink-0 text-[10.5px] text-slate-400">{d.tables.length} tables · {d.total_rows} rows</span>
                </div>
              ))}
            </div>
          </Card>
        )}

        <Card className="p-4">
          <SectionTitle>Runtime mode</SectionTitle>
          {config && (
            <div className="space-y-2 text-[12.5px] text-slate-600">
              <div className="flex items-center gap-2">
                <span className={cn("h-2 w-2 rounded-full", config.mode === "live" ? "bg-emerald-500" : "bg-amber-500")} />
                {config.mode === "live"
                  ? <>Live answers via <span className="font-medium text-slate-800">{config.provider}</span></>
                  : "Offline mode — deterministic cached answers"}
              </div>
              <p className="text-[11.5px] leading-relaxed text-slate-400">
                Without an API key the system still runs end-to-end on deterministic fallbacks, so the
                routing, retrieval, and citation behaviour stay demonstrable. Repeated questions are served
                from cache for instant replay.
              </p>
            </div>
          )}
        </Card>
      </aside>
    </div>
  );
}
