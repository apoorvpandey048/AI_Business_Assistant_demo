"use client";
import React from "react";
import type { AskResponse, Inventory } from "@/lib/types";
import { Button, Card, EmptyState, Icons, isRTL } from "./ui";
import type { PromptKind } from "@/lib/prompt";
import PromptBar from "./PromptBar";
import AnswerPanel from "./AnswerPanel";

export default function Chat({
  inventory, role, cases, question, setQuestion, onAsk, onClear, resp, loading, error,
  onOpenInspector, onOpenSources,
  onSaveRole, onClearRole, onSaveCases, onClearCases, openPrompt, onOpenPromptHandled,
}: {
  inventory: Inventory | null;
  role: string;
  cases: string;
  question: string;
  setQuestion: (q: string) => void;
  onAsk: (q: string) => void;
  onClear: () => void;
  resp: AskResponse | null;
  loading: boolean;
  error: string | null;
  onOpenInspector: () => void;
  onOpenSources: () => void;
  onSaveRole: (v: string) => void;
  onClearRole: () => void;
  onSaveCases: (v: string) => void;
  onClearCases: () => void;
  openPrompt?: PromptKind | null;
  onOpenPromptHandled?: () => void;
}) {
  const uploadedDocs = (inventory?.documents ?? []).filter((d) => d.origin === "uploaded" && d.status === "indexed");
  const uploadedDbs = (inventory?.databases ?? []).filter((d) => d.origin === "uploaded" && d.status === "indexed");
  const hasSources = uploadedDocs.length > 0 || uploadedDbs.length > 0;
  const sourceSummary = [
    uploadedDocs.length ? `${uploadedDocs.length} document${uploadedDocs.length > 1 ? "s" : ""}` : "",
    uploadedDbs.length ? `${uploadedDbs.length} database${uploadedDbs.length > 1 ? "s" : ""}` : "",
  ].filter(Boolean).join(" · ");

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      {/* knowledge-base status strip */}
      <div className="flex flex-wrap items-center gap-2 px-1 text-[12px] text-text-muted">
        <Icons.layers className="h-3.5 w-3.5 text-accent" />
        {hasSources ? (
          <span>Answering from <span className="font-medium text-text-strong">{sourceSummary}</span> in your knowledge base.</span>
        ) : (
          <span>Your knowledge base is empty.</span>
        )}
        <button onClick={onOpenSources} className="font-medium text-accent hover:text-accent-hover">
          Manage sources
        </button>
      </div>

      {/* Prompt bar — both prompts live here, above the input, as the single source
          of truth (moved out of Settings). */}
      <PromptBar
        role={role} cases={cases}
        onSaveRole={onSaveRole} onClearRole={onClearRole}
        onSaveCases={onSaveCases} onClearCases={onClearCases}
        openKind={openPrompt} onOpenHandled={onOpenPromptHandled}
      />

      <Card className="p-3">
        <textarea
          value={question} onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) onAsk(question); }}
          rows={3} dir={isRTL(question) ? "rtl" : "ltr"}
          placeholder="Ask a question about your documents and data…"
          className="focus-ring min-h-[88px] w-full resize-y rounded-xl border border-slate-200 bg-white px-3.5 py-3 text-[15px] text-slate-800 placeholder:text-slate-400" />
        <div className="mt-2.5 flex items-center justify-between">
          <span className="text-[11px] text-slate-400">Press ⌘/Ctrl + Enter to ask</span>
          <div className="flex items-center gap-2">
            {(question || resp) && !loading && (
              <Button variant="ghost" size="md" onClick={onClear} title="Clear the question and answer">
                <Icons.x className="h-3.5 w-3.5" />Clear
              </Button>
            )}
            <Button size="md" onClick={() => onAsk(question)} disabled={loading || !question.trim()}>
              {loading
                ? <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/50 border-t-white" />
                : <Icons.spark className="h-4 w-4" />}
              {loading ? "Working…" : "Ask"}
            </Button>
          </div>
        </div>
      </Card>

      {error && (
        <Card className="flex items-start gap-2 px-4 py-3 text-[13px] text-amber-700 ring-1 ring-amber-200">
          <Icons.alert className="mt-0.5 h-4 w-4 shrink-0" />{error}
        </Card>
      )}

      {loading && (
        <Card className="p-10 text-center">
          <div className="mx-auto mb-3 h-7 w-7 animate-spin rounded-full border-2 border-slate-200 border-t-indigo-500" />
          <span className="text-[13px] text-slate-500">Routing → retrieving → grounding…</span>
        </Card>
      )}

      {resp && !loading && <AnswerPanel resp={resp} onOpenInspector={onOpenInspector} />}

      {!resp && !loading && !error && (
        <Card>
          {hasSources ? (
            <EmptyState icon={<Icons.spark className="h-6 w-6" />} title="Ask anything about your sources">
              Answers are grounded in your knowledge base with verifiable citations — open the
              Inspector at any time to see exactly how each answer was produced.
            </EmptyState>
          ) : (
            <EmptyState icon={<Icons.upload className="h-6 w-6" />} title="Start by adding sources">
              <span className="block">
                Upload PDF documents and SQLite databases, then ask questions across all of them.
                Answers come only from your sources — with citations you can verify.
              </span>
              <span className="mt-4 block">
                <Button size="md" onClick={onOpenSources}>
                  <Icons.plus className="h-4 w-4" />Add sources
                </Button>
              </span>
            </EmptyState>
          )}
        </Card>
      )}
    </div>
  );
}
