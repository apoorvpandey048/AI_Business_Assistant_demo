"use client";
import React from "react";
import type { AskResponse } from "@/lib/types";
import { Button, Card, Icons, Pill, RouteBadge, SectionTitle, cn, isRTL } from "./ui";
import { CitationChips, CitedText, EvidenceItem, useCiteHighlight } from "./trace";

export default function AnswerPanel({
  resp, onOpenInspector,
}: { resp: AskResponse; onOpenInspector?: () => void }) {
  const t = resp.trace;
  const { highlight, onCite } = useCiteHighlight();
  const rtlAnswer = isRTL(resp.answer) || t.languages.includes("he");
  const docSel = t.document_retrieval?.candidates.filter((c) => c.selected).length ?? 0;
  const sqlRows = t.sql_executions.filter((s) => s.purpose !== "entity_link").reduce((a, s) => a + s.row_count, 0);
  const retrievalSummary = [
    t.sql_executions.length ? `${sqlRows} database row(s)` : "",
    docSel ? `${docSel} document passage(s)` : "",
  ].filter(Boolean).join(" · ");
  // Supporting evidence = ONLY what the answer actually used (answer-supported), not the
  // full retrieved candidate set. The Inspector keeps the complete set for transparency.
  const supporting = t.evidence.filter((e) => e.used);
  const supportingHint = supporting.length === t.evidence.length
    ? `${supporting.length} item(s)`
    : `${supporting.length} of ${t.evidence.length} retrieved`;

  return (
    <div className="fade-up space-y-4">
      {/* routing summary */}
      <Card className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3">
        <div className="flex items-center gap-2">
          <Icons.route className="h-4 w-4 text-indigo-500" />
          <span className="text-[11px] font-semibold uppercase tracking-[0.1em] text-slate-400">Routed to</span>
          {t.route ? <RouteBadge route={t.route.route} withLabel /> : <Pill>—</Pill>}
        </div>
        {t.route && (
          <span className="text-[12px] text-slate-500">
            {(t.route.confidence * 100).toFixed(0)}% confidence
            {t.route.agentic && " · agentic"}
          </span>
        )}
        {retrievalSummary && (
          <span className="flex items-center gap-1.5 text-[12px] text-slate-500">
            <Icons.search className="h-3.5 w-3.5 text-sky-500" />{retrievalSummary}
          </span>
        )}
        <span className="ml-auto flex items-center gap-1.5 text-[12px]">
          {t.citation_check?.verified ? (
            <Pill tone="emerald"><Icons.shield className="h-3 w-3" />citations verified</Pill>
          ) : t.evidence.length ? (
            <Pill tone="amber">citations unverified</Pill>
          ) : null}
        </span>
      </Card>

      {/* answer */}
      <Card className={cn("p-5", resp.insufficient && "ring-1 ring-amber-200")}>
        <div className="mb-3 flex items-center justify-between">
          <SectionTitle>Answer</SectionTitle>
          {onOpenInspector && (
            <Button variant="ghost" size="sm" onClick={onOpenInspector}>
              <Icons.inspect className="h-3.5 w-3.5" />View retrieval trace
            </Button>
          )}
        </div>
        {resp.insufficient && (
          <div className="mb-3"><Pill tone="amber"><Icons.alert className="h-3 w-3" />Insufficient evidence — not answered</Pill></div>
        )}
        <CitedText text={resp.answer} onCite={onCite} rtl={rtlAnswer} />

        {resp.citations.length > 0 && (
          <div className="mt-4 border-t border-slate-100 pt-3.5">
            <SectionTitle>Sources</SectionTitle>
            <CitationChips citations={resp.citations} onCite={onCite} />
          </div>
        )}
      </Card>

      {/* supporting evidence — only the passages/rows the answer is grounded in */}
      {supporting.length > 0 && (
        <Card className="p-4">
          <SectionTitle hint={supportingHint}>Supporting evidence</SectionTitle>
          <p className="-mt-1 mb-2.5 text-[11.5px] text-slate-400">
            The exact passages and records this answer is grounded in.
            {supporting.length < t.evidence.length && " Open the trace to see everything that was retrieved."}
          </p>
          <div className="space-y-2">
            {supporting.map((e) => <EvidenceItem key={e.id} e={e} highlight={highlight === e.id} compact />)}
          </div>
        </Card>
      )}
    </div>
  );
}
