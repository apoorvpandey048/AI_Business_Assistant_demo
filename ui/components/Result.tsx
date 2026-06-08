"use client";
import React from "react";
import type {
  AskResponse, Evidence, RetrievalCandidate, SqlExecutionTrace,
} from "@/lib/types";
import {
  Card, Collapsible, Icons, Pill, RouteBadge, ScoreBar, SectionTitle, cn, isRTL,
} from "./ui";

/* ---------- answer with clickable [eN] citation markers ---------- */
function CitedText({ text, onCite, rtl }: { text: string; onCite: (id: string) => void; rtl: boolean }) {
  const parts = text.split(/(\[e\d+\])/g);
  return (
    <div dir={rtl ? "rtl" : "ltr"}
      className={cn("whitespace-pre-wrap text-[15px] leading-[1.7] text-slate-100", rtl && "text-right")}>
      {parts.map((p, i) => {
        const m = p.match(/^\[(e\d+)\]$/);
        if (m) return (
          <button key={i} onClick={() => onCite(m[1])}
            className="mx-0.5 inline-flex -translate-y-0.5 items-center rounded-md bg-indigo-400/15 px-1.5 text-[10px] font-bold text-indigo-300 ring-1 ring-indigo-400/30 transition hover:bg-indigo-400/30">
            {m[1]}
          </button>
        );
        return <span key={i}>{p}</span>;
      })}
    </div>
  );
}

/* ---------- pipeline stepper (hero) ---------- */
function StageNode({ icon, label, value, accent }: {
  icon: React.ReactNode; label: string; value: React.ReactNode; accent: string;
}) {
  return (
    <div className="flex min-w-0 flex-1 flex-col items-center px-1 text-center">
      <div className={cn("mb-2 flex h-9 w-9 items-center justify-center rounded-xl ring-1 ring-inset", accent)}>
        {icon}
      </div>
      <div className="text-[9.5px] font-semibold uppercase tracking-[0.12em] text-slate-500">{label}</div>
      <div className="mt-0.5 truncate text-[13px] font-medium text-slate-200">{value}</div>
    </div>
  );
}

function Stepper({ resp }: { resp: AskResponse }) {
  const t = resp.trace;
  const docSel = t.document_retrieval?.candidates.filter((c) => c.selected).length ?? 0;
  const sqlRows = t.sql_executions.filter((s) => s.purpose !== "entity_link").reduce((a, s) => a + s.row_count, 0);
  const retrieval = [t.sql_executions.length ? `${sqlRows} rows` : "", docSel ? `${docSel} passages` : ""]
    .filter(Boolean).join(" · ") || "—";
  const verified = t.citation_check?.verified;

  const stages = [
    { icon: <Icons.question className="text-slate-300" />, label: "Question", accent: "bg-slate-400/10 text-slate-300 ring-slate-400/20",
      value: t.languages.includes("he") ? "Hebrew" : "English" },
    { icon: <Icons.route className="text-indigo-300" />, label: "Route", accent: "bg-indigo-400/10 ring-indigo-400/25",
      value: t.route ? <RouteBadge route={t.route.route} small /> : "—" },
    { icon: <Icons.search className="text-sky-300" />, label: "Retrieval", accent: "bg-sky-400/10 ring-sky-400/25", value: retrieval },
    { icon: <Icons.layers className="text-cyan-300" />, label: "Evidence", accent: "bg-cyan-400/10 ring-cyan-400/25", value: `${t.evidence.length}` },
    { icon: <Icons.spark className={resp.insufficient ? "text-amber-300" : "text-emerald-300"} />, label: "Answer",
      accent: resp.insufficient ? "bg-amber-400/10 ring-amber-400/25" : "bg-emerald-400/10 ring-emerald-400/25",
      value: resp.insufficient ? "insufficient" : "grounded" },
    { icon: <Icons.shield className={verified ? "text-emerald-300" : "text-rose-300"} />, label: "Citations",
      accent: verified ? "bg-emerald-400/10 ring-emerald-400/25" : "bg-rose-400/10 ring-rose-400/25",
      value: t.citation_check ? <span className={verified ? "text-emerald-300" : "text-rose-300"}>
        {t.citation_check.cited_ids.length} {verified ? "✓" : "✗"}</span> : "—" },
  ];

  return (
    <div className="flex items-start">
      {stages.map((s, i) => (
        <React.Fragment key={s.label}>
          <StageNode {...s} />
          {i < stages.length - 1 && (
            <div className="mt-4 flex shrink-0 items-center px-0.5 text-slate-600">
              <Icons.arrowR className="h-3.5 w-3.5" />
            </div>
          )}
        </React.Fragment>
      ))}
    </div>
  );
}

/* ---------- SQL block ---------- */
function SqlBlock({ s }: { s: SqlExecutionTrace }) {
  const cols = s.columns.length ? s.columns : Object.keys(s.rows[0] ?? {});
  return (
    <div className="rounded-xl border border-white/[0.06] bg-black/30 p-3">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <Pill tone="sky">{s.purpose}</Pill>
        {s.valid ? <Pill tone="emerald"><Icons.check className="h-3 w-3" />read-only · validated</Pill>
                 : <Pill tone="rose">rejected</Pill>}
        <Pill>{s.row_count} rows</Pill>
        <Pill><Icons.clock className="h-3 w-3" />{s.duration_ms} ms</Pill>
        {s.tables.length > 0 && <Pill>{s.tables.join(", ")}</Pill>}
      </div>
      <pre className="scroll-thin overflow-x-auto rounded-lg bg-black/50 p-2.5 font-mono text-[11px] leading-relaxed text-emerald-200">{s.validated_sql || s.generated_sql}</pre>
      {s.validation_error && <p className="mt-1 text-[11px] text-rose-300">error: {s.validation_error}</p>}
      {s.rows.length > 0 && (
        <div className="scroll-thin mt-2 max-h-56 overflow-auto rounded-lg border border-white/[0.06]">
          <table className="w-full text-left text-[11px]">
            <thead className="sticky top-0 bg-slate-900/95 text-slate-400 backdrop-blur">
              <tr>{cols.map((c) => <th key={c} className="px-2.5 py-1.5 font-medium">{c}</th>)}</tr>
            </thead>
            <tbody className="font-mono text-slate-300">
              {s.rows.slice(0, 12).map((r, i) => (
                <tr key={i} className="border-t border-white/[0.05] hover:bg-white/[0.02]">
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
function CandidatesTable({ rows }: { rows: RetrievalCandidate[] }) {
  return (
    <div className="scroll-thin max-h-72 overflow-auto rounded-lg border border-white/[0.06]">
      <table className="w-full text-left text-[11px]">
        <thead className="sticky top-0 bg-slate-900/95 text-slate-400 backdrop-blur">
          <tr>{["#", "document", "p.", "dense", "bm25", "rrf", "rerank", ""].map((h) =>
            <th key={h} className="px-2.5 py-1.5 font-medium">{h}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((c) => (
            <tr key={c.chunk_id} className={cn("border-t border-white/[0.05]", c.selected ? "bg-indigo-400/[0.07]" : "hover:bg-white/[0.02]")}>
              <td className="px-2.5 py-1.5 font-mono text-slate-400">{c.final_rank}</td>
              <td className="px-2.5 py-1.5"><span className="text-slate-200">{c.document}</span>
                {c.section && <span className="ml-1 text-slate-500">· {c.section.slice(0, 26)}</span>}</td>
              <td className="px-2.5 py-1.5 font-mono text-slate-400">{c.page ?? "—"}</td>
              <td className="px-2.5 py-1.5 font-mono text-slate-400">{c.dense_rank ? `#${c.dense_rank}` : "—"}</td>
              <td className="px-2.5 py-1.5 font-mono text-slate-400">{c.bm25_rank ? `#${c.bm25_rank}` : "—"}</td>
              <td className="px-2.5 py-1.5"><ScoreBar value={c.rrf_score} max={0.05} /></td>
              <td className="px-2.5 py-1.5 font-mono text-slate-400">{c.rerank_score != null ? c.rerank_score.toFixed(2) : "—"}</td>
              <td className="px-2.5 py-1.5">{c.selected && <Pill tone="indigo">selected</Pill>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ---------- evidence ---------- */
function EvidenceItem({ e, highlight }: { e: Evidence; highlight: boolean }) {
  const rtl = isRTL(e.content);
  return (
    <div id={`ev-${e.id}`}
      className={cn("rounded-xl border p-3 transition",
        highlight ? "cite-pulse border-indigo-400/60 bg-indigo-400/[0.08]" : "border-white/[0.06] bg-black/20")}>
      <div className="mb-1.5 flex flex-wrap items-center gap-2">
        <span className="rounded-md bg-indigo-400/15 px-1.5 py-0.5 font-mono text-[10px] font-bold text-indigo-300">{e.id}</span>
        <Pill tone={e.source_kind === "relational" ? "sky" : "emerald"}>
          {e.source_kind === "relational" ? <Icons.db className="h-3 w-3" /> : <Icons.doc className="h-3 w-3" />}
          {e.source_kind === "relational" ? "database" : "document"}
        </Pill>
        <span className="font-mono text-[11px] text-slate-400">{e.citation_label}</span>
        {e.score != null && <span className="font-mono text-[10px] text-slate-500">score {e.score.toFixed(3)}</span>}
      </div>
      <p dir={rtl ? "rtl" : "ltr"} className={cn("text-[12px] leading-relaxed text-slate-300", rtl && "text-right")}>
        {e.content.length > 320 ? e.content.slice(0, 320) + "…" : e.content}
      </p>
    </div>
  );
}

/* ================= main ================= */
export default function Result({ resp }: { resp: AskResponse }) {
  const t = resp.trace;
  const [highlight, setHighlight] = React.useState<string | null>(null);
  const rtlAnswer = isRTL(resp.answer) || t.languages.includes("he");

  const onCite = (id: string) => {
    setHighlight(id);
    document.getElementById(`ev-${id}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
    setTimeout(() => setHighlight(null), 1700);
  };

  return (
    <div className="fade-up space-y-4">
      <Card className="px-4 py-4"><Stepper resp={resp} /></Card>

      <Card className={cn("relative overflow-hidden p-5", resp.insufficient && "ring-1 ring-amber-400/30")}>
        <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-indigo-400/50 to-transparent" />
        <SectionTitle hint={`mode: ${t.mode}`}>Answer</SectionTitle>
        {resp.insufficient && (
          <div className="mb-2"><Pill tone="amber">⚠ insufficient evidence — not answered</Pill></div>
        )}
        <CitedText text={resp.answer} onCite={onCite} rtl={rtlAnswer} />
        {resp.citations.length > 0 && (
          <div className="mt-4 border-t border-white/[0.06] pt-3">
            <SectionTitle>Citations</SectionTitle>
            <div className="flex flex-wrap gap-2">
              {resp.citations.map((c) => (
                <button key={c.id} onClick={() => onCite(c.id)}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-white/[0.08] bg-black/20 px-2 py-1 text-[11px] transition hover:border-indigo-400/50 hover:bg-indigo-400/[0.06]">
                  <span className="font-mono font-bold text-indigo-300">{c.id}</span>
                  {c.source_kind === "relational" ? <Icons.db className="h-3 w-3 text-sky-300" /> : <Icons.doc className="h-3 w-3 text-emerald-300" />}
                  <span className="text-slate-400">{c.citation_label}</span>
                </button>
              ))}
            </div>
          </div>
        )}
      </Card>

      <div className="flex items-center gap-3 pt-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">
        <span className="h-px flex-1 bg-white/[0.07]" /><Icons.bolt className="h-3.5 w-3.5 text-indigo-400/70" />Inspector
        <span className="h-px flex-1 bg-white/[0.07]" />
      </div>

      {t.route && (
        <Collapsible icon={<Icons.route />} title={<>Routing decision <RouteBadge route={t.route.route} small /></>}
          right={<Pill tone="indigo">{(t.route.confidence * 100).toFixed(0)}% confidence</Pill>}>
          <div className="space-y-2 text-[12px] text-slate-300">
            <p>{t.route.reasoning}</p>
            <div className="flex flex-wrap gap-2">
              {t.route.agentic && <Pill tone="indigo"><Icons.bolt className="h-3 w-3" />agentic: SQL → entities → documents</Pill>}
              <Pill>languages: {t.route.languages.join(", ")}</Pill>
              {t.route.strategy_note && <Pill>{t.route.strategy_note}</Pill>}
            </div>
            {t.route.sql_subquery && <p className="text-slate-400"><span className="text-slate-500">sql sub-query:</span> {t.route.sql_subquery}</p>}
            {t.route.document_subquery && <p className="text-slate-400"><span className="text-slate-500">document sub-query:</span> {t.route.document_subquery}</p>}
          </div>
        </Collapsible>
      )}

      {t.notes.length > 0 && (
        <Collapsible icon={<Icons.layers />} title="Orchestrator trace" right={<Pill>{t.notes.length} steps</Pill>}>
          <ol className="space-y-2">
            {t.notes.map((n, i) => (
              <li key={i} className="flex gap-2.5 text-[12px] text-slate-300">
                <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-indigo-400/15 font-mono text-[9px] text-indigo-300">{i + 1}</span>
                <span>{n}</span>
              </li>
            ))}
          </ol>
        </Collapsible>
      )}

      {t.sql_executions.length > 0 && (
        <Collapsible icon={<Icons.db />} title="SQL branch" right={<Pill tone="sky">{t.sql_executions.length} query</Pill>}>
          <div className="space-y-3">{t.sql_executions.map((s, i) => <SqlBlock key={i} s={s} />)}</div>
        </Collapsible>
      )}

      {t.document_retrieval && (
        <Collapsible icon={<Icons.search />} title="Document retrieval — dense + BM25 → RRF → rerank"
          right={<Pill tone="emerald">{t.document_retrieval.candidates.length} candidates</Pill>}>
          <div className="mb-2.5 flex flex-wrap gap-2 text-[11px]">
            <Pill>embed: {t.document_retrieval.embedding_backend}</Pill>
            <Pill>rerank: {t.document_retrieval.reranker_backend}</Pill>
            {Object.entries(t.document_retrieval.params).map(([k, v]) => <Pill key={k}>{k}: {String(v)}</Pill>)}
            {!!(t.document_retrieval.filters as any)?.documents && (
              <Pill tone="indigo"><Icons.bolt className="h-3 w-3" />filtered → {(t.document_retrieval.filters as any).documents.length} doc(s)</Pill>)}
          </div>
          <CandidatesTable rows={t.document_retrieval.candidates} />
        </Collapsible>
      )}

      {t.evidence.length > 0 && (
        <Collapsible icon={<Icons.layers />} title="Evidence (single source of truth)" right={<Pill>{t.evidence.length} items</Pill>}>
          <div className="space-y-2">{t.evidence.map((e) => <EvidenceItem key={e.id} e={e} highlight={highlight === e.id} />)}</div>
        </Collapsible>
      )}

      <Card className="p-4">
        <div className="grid gap-5 sm:grid-cols-3">
          <div>
            <SectionTitle>Cost</SectionTitle>
            {t.cost && (
              <div className="space-y-1 text-[12px]">
                <div className="flex items-center gap-1.5 font-mono text-slate-100"><Icons.coin className="h-3.5 w-3.5 text-amber-300/80" />${t.cost.total_usd.toFixed(4)}</div>
                <div className="text-slate-500">{t.cost.input_tokens} in / {t.cost.output_tokens} out · {t.cost.live_calls} live</div>
                <div className="text-[11px] text-slate-500">{t.cost.note}</div>
              </div>
            )}
          </div>
          <div>
            <SectionTitle>Timings</SectionTitle>
            <div className="space-y-1 text-[12px]">
              {t.timings.map((ti) => (
                <div key={ti.name} className="flex justify-between font-mono text-slate-400">
                  <span>{ti.name}</span><span>{ti.duration_ms} ms</span>
                </div>
              ))}
            </div>
          </div>
          <div>
            <SectionTitle>Citation check</SectionTitle>
            {t.citation_check && (
              <div className="text-[12px]">
                <Pill tone={t.citation_check.verified ? "emerald" : "rose"}>
                  {t.citation_check.verified ? <><Icons.check className="h-3 w-3" />verified</> : "failed"}
                </Pill>
                <p className="mt-1.5 text-[11px] text-slate-500">{t.citation_check.note}</p>
              </div>
            )}
          </div>
        </div>
        {t.llm_calls.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2 border-t border-white/[0.06] pt-3">
            {t.llm_calls.map((c, i) => (
              <Pill key={i} tone={c.mode === "live" ? "emerald" : "slate"}>{c.purpose}: {c.model} ({c.mode})</Pill>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
