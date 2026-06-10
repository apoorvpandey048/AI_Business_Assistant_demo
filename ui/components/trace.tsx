"use client";
import React from "react";
import type {
  AskResponse, Evidence, RetrievalCandidate, SqlExecutionTrace,
} from "@/lib/types";
import { Icons, OriginTag, Pill, RouteBadge, ScoreBar, cn, isRTL } from "./ui";

/* ---------- cite → scroll/highlight ---------- */
export function useCiteHighlight() {
  const [highlight, setHighlight] = React.useState<string | null>(null);
  const onCite = React.useCallback((id: string) => {
    setHighlight(id);
    document.getElementById(`ev-${id}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
    window.setTimeout(() => setHighlight(null), 1700);
  }, []);
  return { highlight, onCite };
}

/* ---------- answer text with clickable [eN] markers ---------- */
export function CitedText({ text, onCite, rtl }: { text: string; onCite: (id: string) => void; rtl: boolean }) {
  const parts = text.split(/(\[e\d+\])/g);
  return (
    <div dir={rtl ? "rtl" : "ltr"}
      className={cn("whitespace-pre-wrap text-[15px] leading-[1.75] text-slate-800", rtl && "text-right")}>
      {parts.map((p, i) => {
        const m = p.match(/^\[(e\d+)\]$/);
        if (m) return (
          <button key={i} onClick={() => onCite(m[1])}
            className="mx-0.5 inline-flex -translate-y-0.5 items-center rounded-md bg-indigo-50 px-1.5 text-[10px] font-bold text-indigo-600 ring-1 ring-indigo-200 transition hover:bg-indigo-100">
            {m[1]}
          </button>
        );
        return <span key={i}>{p}</span>;
      })}
    </div>
  );
}

/* ---------- evidence ---------- */
export function EvidenceItem({ e, highlight, compact, showUsed }: {
  e: Evidence; highlight: boolean; compact?: boolean; showUsed?: boolean;
}) {
  const rtl = isRTL(e.content);
  const limit = compact ? 220 : 320;
  return (
    <div id={`ev-${e.id}`}
      className={cn("rounded-xl border p-3 transition",
        highlight ? "cite-pulse border-indigo-300 bg-indigo-50/60" : "border-slate-200 bg-white")}>
      <div className="mb-1.5 flex flex-wrap items-center gap-2">
        <span className="rounded-md bg-indigo-50 px-1.5 py-0.5 font-mono text-[10px] font-bold text-indigo-600 ring-1 ring-indigo-200">{e.id}</span>
        <Pill tone={e.source_kind === "relational" ? "sky" : "emerald"}>
          {e.source_kind === "relational" ? <Icons.db className="h-3 w-3" /> : <Icons.doc className="h-3 w-3" />}
          {e.source_kind === "relational" ? "database" : "document"}
        </Pill>
        <span className="font-mono text-[11px] text-slate-500">{e.citation_label}</span>
        <OriginTag origin={e.origin} />
        {showUsed && e.used && <Pill tone="emerald"><Icons.check className="h-3 w-3" />used in answer</Pill>}
        {e.score != null && <span className="ml-auto font-mono text-[10px] text-slate-400">score {e.score.toFixed(3)}</span>}
      </div>
      <p dir={rtl ? "rtl" : "ltr"} className={cn("text-[12.5px] leading-relaxed text-slate-600", rtl && "text-right")}>
        {e.content.length > limit ? e.content.slice(0, limit) + "…" : e.content}
      </p>
    </div>
  );
}

export function CitationChips({ citations, onCite }: { citations: Evidence[]; onCite: (id: string) => void }) {
  return (
    <div className="flex flex-wrap gap-2">
      {citations.map((c) => (
        <button key={c.id} onClick={() => onCite(c.id)}
          title={c.origin === "uploaded" ? "From your upload" : c.origin === "sample" ? "From sample data" : undefined}
          className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2 py-1 text-[11px] transition hover:border-indigo-300 hover:bg-indigo-50">
          <span className="font-mono font-bold text-indigo-600">{c.id}</span>
          {c.source_kind === "relational" ? <Icons.db className="h-3 w-3 text-sky-500" /> : <Icons.doc className="h-3 w-3 text-emerald-500" />}
          <span className="text-slate-500">{c.citation_label}</span>
          {c.origin === "uploaded" && <span className="h-1.5 w-1.5 rounded-full bg-indigo-400" />}
        </button>
      ))}
    </div>
  );
}

/* ---------- SQL block ---------- */
export function SqlBlock({ s }: { s: SqlExecutionTrace }) {
  const cols = s.columns.length ? s.columns : Object.keys(s.rows[0] ?? {});
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50/60 p-3">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <Pill tone="sky">{s.purpose}</Pill>
        {s.valid ? <Pill tone="emerald"><Icons.check className="h-3 w-3" />read-only · validated</Pill>
                 : <Pill tone="rose">rejected</Pill>}
        <Pill>{s.row_count} rows</Pill>
        <Pill><Icons.clock className="h-3 w-3" />{s.duration_ms} ms</Pill>
        {s.tables.length > 0 && <Pill>{s.tables.join(", ")}</Pill>}
      </div>
      <pre className="scroll-thin code-surface overflow-x-auto p-2.5 font-mono text-[11px] leading-relaxed">{s.validated_sql || s.generated_sql}</pre>
      {s.validation_error && <p className="mt-1 text-[11px] text-rose-600">error: {s.validation_error}</p>}
      {s.rows.length > 0 && (
        <div className="scroll-thin mt-2 max-h-56 overflow-auto rounded-lg border border-slate-200">
          <table className="w-full text-left text-[11px]">
            <thead className="sticky top-0 bg-slate-100/95 text-slate-500 backdrop-blur">
              <tr>{cols.map((c) => <th key={c} className="px-2.5 py-1.5 font-medium">{c}</th>)}</tr>
            </thead>
            <tbody className="font-mono text-slate-600">
              {s.rows.slice(0, 12).map((r, i) => (
                <tr key={i} className="border-t border-slate-100 hover:bg-slate-50">
                  {cols.map((c) => <td key={c} className="px-2.5 py-1.5">{String((r as any)[c] ?? "")}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/* ---------- retrieval candidates ---------- */
export function CandidatesTable({ rows }: { rows: RetrievalCandidate[] }) {
  return (
    <div className="scroll-thin max-h-72 overflow-auto rounded-lg border border-slate-200">
      <table className="w-full text-left text-[11px]">
        <thead className="sticky top-0 bg-slate-100/95 text-slate-500 backdrop-blur">
          <tr>{["#", "document", "p.", "dense", "bm25", "rrf", "rerank", ""].map((h) =>
            <th key={h} className="px-2.5 py-1.5 font-medium">{h}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((c) => (
            <tr key={c.chunk_id} className={cn("border-t border-slate-100", c.selected ? "bg-indigo-50/70" : "hover:bg-slate-50")}>
              <td className="px-2.5 py-1.5 font-mono text-slate-500">{c.final_rank}</td>
              <td className="px-2.5 py-1.5"><span className="text-slate-700">{c.document}</span>
                {c.keyword_hit && <span className="ml-1.5 rounded bg-amber-50 px-1 py-0.5 text-[9px] font-semibold text-amber-700 ring-1 ring-amber-200">exact</span>}
                {c.section && <span className="ml-1 text-slate-400">· {c.section.slice(0, 26)}</span>}</td>
              <td className="px-2.5 py-1.5 font-mono text-slate-500">{c.page ?? "—"}</td>
              <td className="px-2.5 py-1.5 font-mono text-slate-500">{c.dense_rank ? `#${c.dense_rank}` : "—"}</td>
              <td className="px-2.5 py-1.5 font-mono text-slate-500">{c.bm25_rank ? `#${c.bm25_rank}` : "—"}</td>
              <td className="px-2.5 py-1.5"><ScoreBar value={c.rrf_score} max={0.05} /></td>
              <td className="px-2.5 py-1.5 font-mono text-slate-500">{c.rerank_score != null ? c.rerank_score.toFixed(2) : "—"}</td>
              <td className="px-2.5 py-1.5">{c.selected && <Pill tone="indigo">selected</Pill>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ---------- pipeline stepper ---------- */
function StageNode({ icon, label, value, accent }: {
  icon: React.ReactNode; label: string; value: React.ReactNode; accent: string;
}) {
  return (
    <div className="flex min-w-0 flex-1 flex-col items-center px-1 text-center">
      <div className={cn("mb-2 flex h-9 w-9 items-center justify-center rounded-xl ring-1 ring-inset", accent)}>
        {icon}
      </div>
      <div className="text-[9.5px] font-semibold uppercase tracking-[0.1em] text-slate-400">{label}</div>
      <div className="mt-0.5 truncate text-[13px] font-medium text-slate-700">{value}</div>
    </div>
  );
}

export function Stepper({ resp }: { resp: AskResponse }) {
  const t = resp.trace;
  const docSel = t.document_retrieval?.candidates.filter((c) => c.selected).length ?? 0;
  const sqlRows = t.sql_executions.filter((s) => s.purpose !== "entity_link").reduce((a, s) => a + s.row_count, 0);
  const retrieval = [t.sql_executions.length ? `${sqlRows} rows` : "", docSel ? `${docSel} passages` : ""]
    .filter(Boolean).join(" · ") || "—";
  const verified = t.citation_check?.verified;

  const stages = [
    { icon: <Icons.question className="text-slate-500" />, label: "Question", accent: "bg-slate-50 text-slate-500 ring-slate-200",
      value: t.languages.includes("he") ? "Hebrew" : "English" },
    { icon: <Icons.route className="text-indigo-500" />, label: "Route", accent: "bg-indigo-50 ring-indigo-200",
      value: t.route ? <RouteBadge route={t.route.route} small /> : "—" },
    { icon: <Icons.search className="text-sky-500" />, label: "Retrieval", accent: "bg-sky-50 ring-sky-200", value: retrieval },
    { icon: <Icons.layers className="text-cyan-500" />, label: "Evidence", accent: "bg-cyan-50 ring-cyan-200", value: `${t.evidence.length}` },
    { icon: <Icons.spark className={resp.insufficient ? "text-amber-500" : "text-emerald-500"} />, label: "Answer",
      accent: resp.insufficient ? "bg-amber-50 ring-amber-200" : "bg-emerald-50 ring-emerald-200",
      value: resp.insufficient ? "insufficient" : "grounded" },
    { icon: <Icons.shield className={verified ? "text-emerald-500" : "text-rose-500"} />, label: "Citations",
      accent: verified ? "bg-emerald-50 ring-emerald-200" : "bg-rose-50 ring-rose-200",
      value: t.citation_check ? <span className={verified ? "text-emerald-600" : "text-rose-600"}>
        {t.citation_check.cited_ids.length} {verified ? "✓" : "✗"}</span> : "—" },
  ];

  return (
    <div className="flex items-start">
      {stages.map((s, i) => (
        <React.Fragment key={s.label}>
          <StageNode {...s} />
          {i < stages.length - 1 && (
            <div className="mt-4 flex shrink-0 items-center px-0.5 text-slate-300">
              <Icons.arrowR className="h-3.5 w-3.5" />
            </div>
          )}
        </React.Fragment>
      ))}
    </div>
  );
}
