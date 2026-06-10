"use client";
import React from "react";
import type { AskResponse } from "@/lib/types";
import { Card, Collapsible, EmptyState, Icons, Pill, RouteBadge, SectionTitle } from "./ui";
import {
  CandidatesTable, EvidenceItem, SqlBlock, Stepper, useCiteHighlight,
} from "./trace";

export default function Inspector({ resp }: { resp: AskResponse | null }) {
  const { highlight } = useCiteHighlight();
  if (!resp) {
    return (
      <Card>
        <EmptyState icon={<Icons.inspect className="h-6 w-6" />} title="No retrieval trace yet">
          Ask a question in the Workspace. Every answer is recorded here in full — routing decision,
          generated SQL, hybrid retrieval scores, evidence aggregation, citation verification, timing,
          and token usage.
        </EmptyState>
      </Card>
    );
  }

  const t = resp.trace;

  return (
    <div className="fade-up space-y-4">
      <Card className="px-4 py-4"><Stepper resp={resp} /></Card>

      {t.route && (
        <Collapsible icon={<Icons.route />} title={<>Routing decision <RouteBadge route={t.route.route} small /></>}
          right={<Pill tone="indigo">{(t.route.confidence * 100).toFixed(0)}% confidence</Pill>}>
          <div className="space-y-2 text-[12.5px] text-slate-600">
            <p>{t.route.reasoning}</p>
            {t.route.route === "NONE" && (
              <p className="text-slate-500">No matching evidence found in uploaded sources.</p>
            )}
            <div className="flex flex-wrap gap-2">
              {t.route.agentic && <Pill tone="indigo"><Icons.bolt className="h-3 w-3" />agentic: SQL → entities → documents</Pill>}
              <Pill>languages: {t.route.languages.join(", ")}</Pill>
              {t.route.strategy_note && <Pill>{t.route.strategy_note}</Pill>}
            </div>
            {t.route.sql_subquery && <p className="text-slate-500"><span className="text-slate-400">sql sub-query:</span> {t.route.sql_subquery}</p>}
            {t.route.document_subquery && <p className="text-slate-500"><span className="text-slate-400">document sub-query:</span> {t.route.document_subquery}</p>}
          </div>
        </Collapsible>
      )}

      {t.notes.length > 0 && (
        <Collapsible icon={<Icons.layers />} title="Orchestrator trace" right={<Pill>{t.notes.length} steps</Pill>}>
          <ol className="space-y-2">
            {t.notes.map((n, i) => (
              <li key={i} className="flex gap-2.5 text-[12.5px] text-slate-600">
                <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-indigo-50 font-mono text-[9px] text-indigo-600 ring-1 ring-indigo-200">{i + 1}</span>
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
          {t.document_retrieval.strategy && (
            <p className="mb-2.5 text-[12.5px] leading-relaxed text-slate-600">
              {t.document_retrieval.strategy}
            </p>
          )}
          <div className="mb-2.5 flex flex-wrap gap-2 text-[11px]">
            {t.document_retrieval.intent && (
              <Pill tone={t.document_retrieval.intent === "keyword" ? "amber" : "slate"}>
                intent: {t.document_retrieval.intent}
              </Pill>
            )}
            {t.document_retrieval.intent === "keyword" && !!t.document_retrieval.search_terms?.length && (
              <Pill tone="amber">terms: {t.document_retrieval.search_terms.join(", ")}</Pill>
            )}
            {!!t.document_retrieval.exact_hits && (
              <Pill tone="amber">{t.document_retrieval.exact_hits} exact match(es)</Pill>
            )}
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
          <p className="mb-2.5 text-[11.5px] text-slate-400">
            Everything retrieved for this answer. Items marked <span className="font-medium text-emerald-600">used in answer</span> are
            what the response is actually grounded in.
          </p>
          <div className="space-y-2">{t.evidence.map((e) => <EvidenceItem key={e.id} e={e} highlight={highlight === e.id} showUsed />)}</div>
        </Collapsible>
      )}

      <Card className="p-4">
        <div className="grid gap-5 sm:grid-cols-3">
          <div>
            <SectionTitle>Cost &amp; tokens</SectionTitle>
            {t.cost && (
              <div className="space-y-1 text-[12px]">
                <div className="flex items-center gap-1.5 font-mono text-slate-800"><Icons.coin className="h-3.5 w-3.5 text-amber-500" />${t.cost.total_usd.toFixed(4)}</div>
                <div className="text-slate-500">{t.cost.input_tokens} in / {t.cost.output_tokens} out · {t.cost.live_calls} live</div>
                <div className="text-[11px] text-slate-400">{t.cost.note}</div>
              </div>
            )}
          </div>
          <div>
            <SectionTitle>Timings</SectionTitle>
            <div className="space-y-1 text-[12px]">
              {t.timings.map((ti) => (
                <div key={ti.name} className="flex justify-between font-mono text-slate-500">
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
          <div className="mt-3 flex flex-wrap gap-2 border-t border-slate-100 pt-3">
            {t.llm_calls.map((c, i) => (
              <Pill key={i} tone={c.mode === "live" ? "emerald" : "slate"}>{c.purpose}: {c.model} ({c.mode})</Pill>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
