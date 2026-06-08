"use client";
import React from "react";
import type {
  AskResponse,
  Evidence,
  RetrievalCandidate,
  SqlExecutionTrace,
} from "@/lib/types";
import {
  Card,
  Collapsible,
  Pill,
  RouteBadge,
  ScoreBar,
  SectionTitle,
  cn,
  isRTL,
} from "./ui";

/* ---------- answer with clickable [eN] citation markers ---------- */
function CitedText({
  text,
  onCite,
  rtl,
}: {
  text: string;
  onCite: (id: string) => void;
  rtl: boolean;
}) {
  const parts = text.split(/(\[e\d+\])/g);
  return (
    <p
      dir={rtl ? "rtl" : "ltr"}
      className={cn("whitespace-pre-wrap leading-relaxed text-slate-100", rtl && "text-right")}
    >
      {parts.map((p, i) => {
        const m = p.match(/^\[(e\d+)\]$/);
        if (m) {
          return (
            <button
              key={i}
              onClick={() => onCite(m[1])}
              className="mx-0.5 inline-flex -translate-y-0.5 items-center rounded bg-indigo-500/20 px-1 text-[10px] font-semibold text-indigo-300 ring-1 ring-indigo-500/40 hover:bg-indigo-500/40"
            >
              {m[1]}
            </button>
          );
        }
        return <span key={i}>{p}</span>;
      })}
    </p>
  );
}

/* ---------- pipeline stepper ---------- */
function Stepper({ resp }: { resp: AskResponse }) {
  const t = resp.trace;
  const docSel = t.document_retrieval?.candidates.filter((c) => c.selected).length ?? 0;
  const sqlRows = t.sql_executions
    .filter((s) => s.purpose !== "entity_link")
    .reduce((a, s) => a + s.row_count, 0);
  const stages = [
    { k: "Question", v: `${t.languages.join(", ")}` },
    { k: "Route", v: t.route ? <RouteBadge route={t.route.route} small /> : "—" },
    {
      k: "Retrieval",
      v: `${t.sql_executions.length ? `${sqlRows} row` : ""}${
        t.sql_executions.length && docSel ? " · " : ""
      }${docSel ? `${docSel} passage` : ""}` || "—",
    },
    { k: "Evidence", v: `${t.evidence.length}` },
    { k: "Answer", v: resp.insufficient ? "insufficient" : "grounded" },
    {
      k: "Citations",
      v: t.citation_check ? (
        <span className={t.citation_check.verified ? "text-emerald-300" : "text-rose-300"}>
          {t.citation_check.cited_ids.length} {t.citation_check.verified ? "✓" : "✗"}
        </span>
      ) : (
        "—"
      ),
    },
  ];
  return (
    <div className="flex flex-wrap items-stretch gap-1 text-center">
      {stages.map((s, i) => (
        <React.Fragment key={s.k}>
          <div className="min-w-[92px] flex-1 rounded-lg border border-slate-800 bg-slate-900/70 px-2 py-2">
            <div className="text-[10px] uppercase tracking-wider text-slate-500">{s.k}</div>
            <div className="mt-1 text-sm font-medium text-slate-200">{s.v}</div>
          </div>
          {i < stages.length - 1 && (
            <div className="flex items-center text-slate-600">→</div>
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
    <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <Pill tone="sky">{s.purpose}</Pill>
        {s.valid ? (
          <Pill tone="emerald">validated · read-only</Pill>
        ) : (
          <Pill tone="rose">rejected</Pill>
        )}
        <Pill>{s.row_count} rows</Pill>
        <Pill>{s.duration_ms} ms</Pill>
        {s.tables.length > 0 && <Pill>tables: {s.tables.join(", ")}</Pill>}
      </div>
      <pre className="scroll-thin overflow-x-auto rounded bg-black/40 p-2 font-mono text-[11px] leading-relaxed text-emerald-200">
        {s.validated_sql || s.generated_sql}
      </pre>
      {s.validation_error && (
        <p className="mt-1 text-[11px] text-rose-300">error: {s.validation_error}</p>
      )}
      {s.rows.length > 0 && (
        <div className="scroll-thin mt-2 max-h-56 overflow-auto rounded border border-slate-800">
          <table className="w-full text-left text-[11px]">
            <thead className="sticky top-0 bg-slate-900 text-slate-400">
              <tr>
                {cols.map((c) => (
                  <th key={c} className="px-2 py-1 font-medium">{c}</th>
                ))}
              </tr>
            </thead>
            <tbody className="font-mono text-slate-300">
              {s.rows.slice(0, 12).map((r, i) => (
                <tr key={i} className="border-t border-slate-800/60">
                  {cols.map((c) => (
                    <td key={c} className="px-2 py-1">{String((r as any)[c] ?? "")}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/* ---------- retrieval candidates table ---------- */
function CandidatesTable({ rows }: { rows: RetrievalCandidate[] }) {
  return (
    <div className="scroll-thin max-h-72 overflow-auto rounded border border-slate-800">
      <table className="w-full text-left text-[11px]">
        <thead className="sticky top-0 bg-slate-900 text-slate-400">
          <tr>
            {["#", "document", "p.", "dense", "bm25", "rrf", "rerank", ""].map((h) => (
              <th key={h} className="px-2 py-1 font-medium">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((c) => (
            <tr
              key={c.chunk_id}
              className={cn(
                "border-t border-slate-800/60",
                c.selected ? "bg-indigo-500/10" : ""
              )}
            >
              <td className="px-2 py-1 font-mono text-slate-400">{c.final_rank}</td>
              <td className="px-2 py-1">
                <span className="text-slate-200">{c.document}</span>
                {c.section && (
                  <span className="ml-1 text-slate-500">· {c.section.slice(0, 28)}</span>
                )}
              </td>
              <td className="px-2 py-1 font-mono text-slate-400">{c.page ?? "—"}</td>
              <td className="px-2 py-1 font-mono text-slate-400">
                {c.dense_rank ? `#${c.dense_rank}` : "—"}
              </td>
              <td className="px-2 py-1 font-mono text-slate-400">
                {c.bm25_rank ? `#${c.bm25_rank}` : "—"}
              </td>
              <td className="px-2 py-1">
                <ScoreBar value={c.rrf_score} max={0.05} />
              </td>
              <td className="px-2 py-1 font-mono text-slate-400">
                {c.rerank_score != null ? c.rerank_score.toFixed(2) : "—"}
              </td>
              <td className="px-2 py-1">
                {c.selected && <Pill tone="indigo">selected</Pill>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ---------- evidence card ---------- */
function EvidenceItem({ e, highlight }: { e: Evidence; highlight: boolean }) {
  const rtl = isRTL(e.content);
  return (
    <div
      id={`ev-${e.id}`}
      className={cn(
        "rounded-lg border p-3 transition",
        highlight
          ? "cite-pulse border-indigo-400 bg-indigo-500/10"
          : "border-slate-800 bg-slate-950/40"
      )}
    >
      <div className="mb-1 flex flex-wrap items-center gap-2">
        <span className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[10px] text-indigo-300">
          {e.id}
        </span>
        <Pill tone={e.source_kind === "relational" ? "sky" : "emerald"}>
          {e.source_kind === "relational" ? "database" : "document"}
        </Pill>
        <span className="font-mono text-[11px] text-slate-400">{e.citation_label}</span>
        {e.score != null && (
          <span className="font-mono text-[10px] text-slate-500">score {e.score.toFixed(3)}</span>
        )}
      </div>
      <p
        dir={rtl ? "rtl" : "ltr"}
        className={cn("text-[12px] leading-relaxed text-slate-300", rtl && "text-right")}
      >
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
    const el = document.getElementById(`ev-${id}`);
    el?.scrollIntoView({ behavior: "smooth", block: "center" });
    setTimeout(() => setHighlight(null), 1600);
  };

  return (
    <div className="space-y-4">
      {/* pipeline */}
      <Card className="p-3">
        <Stepper resp={resp} />
      </Card>

      {/* answer */}
      <Card className={cn("p-5", resp.insufficient && "border-amber-500/40")}>
        <SectionTitle hint={`mode: ${t.mode}`}>Answer</SectionTitle>
        {resp.insufficient && (
          <div className="mb-2">
            <Pill tone="amber">⚠ insufficient evidence — not answered</Pill>
          </div>
        )}
        <CitedText text={resp.answer} onCite={onCite} rtl={rtlAnswer} />

        {resp.citations.length > 0 && (
          <div className="mt-4 border-t border-slate-800 pt-3">
            <SectionTitle>Citations</SectionTitle>
            <div className="flex flex-wrap gap-2">
              {resp.citations.map((c) => (
                <button
                  key={c.id}
                  onClick={() => onCite(c.id)}
                  className="inline-flex items-center gap-1.5 rounded-md border border-slate-800 bg-slate-950/60 px-2 py-1 text-[11px] hover:border-indigo-500/50"
                >
                  <span className="font-mono text-indigo-300">{c.id}</span>
                  <span className="text-slate-400">{c.citation_label}</span>
                </button>
              ))}
            </div>
          </div>
        )}
      </Card>

      {/* inspector */}
      <div className="space-y-3">
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
          <span className="h-px flex-1 bg-slate-800" />
          Developer / Inspector
          <span className="h-px flex-1 bg-slate-800" />
        </div>

        {/* routing */}
        {t.route && (
          <Collapsible
            title={
              <>
                Routing decision <RouteBadge route={t.route.route} small />
              </>
            }
            right={
              <Pill tone="indigo">
                confidence {(t.route.confidence * 100).toFixed(0)}%
              </Pill>
            }
          >
            <div className="space-y-2 text-[12px] text-slate-300">
              <p>{t.route.reasoning}</p>
              <div className="flex flex-wrap gap-2">
                {t.route.agentic && <Pill tone="indigo">agentic: SQL → entities → documents</Pill>}
                <Pill>languages: {t.route.languages.join(", ")}</Pill>
                {t.route.strategy_note && <Pill>{t.route.strategy_note}</Pill>}
              </div>
              {t.route.sql_subquery && (
                <p className="text-slate-400">
                  <span className="text-slate-500">sql sub-query:</span> {t.route.sql_subquery}
                </p>
              )}
              {t.route.document_subquery && (
                <p className="text-slate-400">
                  <span className="text-slate-500">document sub-query:</span>{" "}
                  {t.route.document_subquery}
                </p>
              )}
            </div>
          </Collapsible>
        )}

        {/* orchestrator narration */}
        {t.notes.length > 0 && (
          <Collapsible title="Orchestrator trace" right={<Pill>{t.notes.length} steps</Pill>}>
            <ol className="space-y-1.5">
              {t.notes.map((n, i) => (
                <li key={i} className="flex gap-2 text-[12px] text-slate-300">
                  <span className="font-mono text-slate-600">{i + 1}.</span>
                  <span>{n}</span>
                </li>
              ))}
            </ol>
          </Collapsible>
        )}

        {/* sql */}
        {t.sql_executions.length > 0 && (
          <Collapsible
            title="SQL branch"
            right={<Pill tone="sky">{t.sql_executions.length} query</Pill>}
          >
            <div className="space-y-3">
              {t.sql_executions.map((s, i) => (
                <SqlBlock key={i} s={s} />
              ))}
            </div>
          </Collapsible>
        )}

        {/* document retrieval */}
        {t.document_retrieval && (
          <Collapsible
            title="Document retrieval — dense + BM25 → RRF → rerank"
            right={<Pill tone="emerald">{t.document_retrieval.candidates.length} candidates</Pill>}
          >
            <div className="mb-2 flex flex-wrap gap-2 text-[11px]">
              <Pill>embed: {t.document_retrieval.embedding_backend}</Pill>
              <Pill>rerank: {t.document_retrieval.reranker_backend}</Pill>
              {Object.entries(t.document_retrieval.params).map(([k, v]) => (
                <Pill key={k}>
                  {k}: {String(v)}
                </Pill>
              ))}
              {!!(t.document_retrieval.filters as any)?.documents && (
                <Pill tone="indigo">
                  filtered → {(t.document_retrieval.filters as any).documents.length} doc(s)
                </Pill>
              )}
            </div>
            <CandidatesTable rows={t.document_retrieval.candidates} />
          </Collapsible>
        )}

        {/* evidence */}
        {t.evidence.length > 0 && (
          <Collapsible
            title="Evidence (single source of truth)"
            right={<Pill>{t.evidence.length} items</Pill>}
          >
            <div className="space-y-2">
              {t.evidence.map((e) => (
                <EvidenceItem key={e.id} e={e} highlight={highlight === e.id} />
              ))}
            </div>
          </Collapsible>
        )}

        {/* footer: cost / timings / verification */}
        <Card className="p-4">
          <div className="grid gap-4 sm:grid-cols-3">
            <div>
              <SectionTitle>Cost</SectionTitle>
              {t.cost && (
                <div className="space-y-1 text-[12px]">
                  <div className="font-mono text-slate-200">
                    ${t.cost.total_usd.toFixed(4)}
                  </div>
                  <div className="text-slate-500">
                    {t.cost.input_tokens} in / {t.cost.output_tokens} out · {t.cost.live_calls} live
                  </div>
                  <div className="text-[11px] text-slate-500">{t.cost.note}</div>
                </div>
              )}
            </div>
            <div>
              <SectionTitle>Timings</SectionTitle>
              <div className="space-y-1 text-[12px]">
                {t.timings.map((ti) => (
                  <div key={ti.name} className="flex justify-between font-mono text-slate-400">
                    <span>{ti.name}</span>
                    <span>{ti.duration_ms} ms</span>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <SectionTitle>Citation check</SectionTitle>
              {t.citation_check && (
                <div className="text-[12px]">
                  <Pill tone={t.citation_check.verified ? "emerald" : "rose"}>
                    {t.citation_check.verified ? "verified ✓" : "failed ✗"}
                  </Pill>
                  <p className="mt-1 text-[11px] text-slate-500">{t.citation_check.note}</p>
                </div>
              )}
            </div>
          </div>
          {t.llm_calls.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2 border-t border-slate-800 pt-3">
              {t.llm_calls.map((c, i) => (
                <Pill key={i} tone={c.mode === "live" ? "emerald" : "slate"}>
                  {c.purpose}: {c.model} ({c.mode})
                </Pill>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
