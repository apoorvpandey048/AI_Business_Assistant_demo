"use client";
import React from "react";
import type { AppConfig, SourceInfo } from "@/lib/types";
import { roleLabel } from "@/lib/role";
import { Button, Card, Icons, Pill, SectionTitle, cn, isRTL } from "./ui";
import ProviderSettings from "./ProviderSettings";
import type { ToastItem } from "./ui";

/* Persona editing is draft-based: nothing is applied until Save. The card always
   shows exactly one of three states so the user never has to guess:
   - "Active"           saved, non-empty, draft matches what is applied
   - "Inactive"         nothing saved, nothing typed
   - "Unsaved changes"  the draft differs from what is currently applied        */
type RoleState = "active" | "inactive" | "unsaved";

export default function Settings({
  role, onSaveRole, onClearRole, config, sources, onReset, resetting, hasUploads,
  onOpenSources, pushToast, onRefreshConfig,
}: {
  role: string;                       // the SAVED role — the one applied to questions
  onSaveRole: (r: string) => void;
  onClearRole: () => void;
  config: AppConfig | null;
  sources: SourceInfo[];
  onReset: () => void;
  resetting: boolean;
  hasUploads: boolean;
  onOpenSources: () => void;
  pushToast: (message: string, tone?: ToastItem["tone"]) => void;
  onRefreshConfig: () => void;        // refresh /config after a provider switch (top-bar)
}) {
  const [draft, setDraft] = React.useState(role);
  // When the saved role changes elsewhere (load from storage, Clear), resync the draft.
  React.useEffect(() => { setDraft(role); }, [role]);

  const dirty = draft.trim() !== role.trim();
  const state: RoleState = dirty ? "unsaved" : role.trim() ? "active" : "inactive";

  const confirmReset = () => {
    if (window.confirm(
      "Remove all uploaded sources and clear the current conversation?\n\n" +
      "Your analysis mode (role) is a preference and will be kept — clear it " +
      "separately above if you want a full reset.\n\nThis cannot be undone."
    )) {
      onReset();
    }
  };

  const connected = sources.filter((s) => s.status === "active").length;

  return (
    <div className="mx-auto grid max-w-5xl gap-4 lg:grid-cols-2">
      {/* ---- analysis mode (persona) ---- */}
      <Card className="p-4 lg:col-span-2">
        <SectionTitle>Analysis mode</SectionTitle>
        <p className="mb-2 text-[12px] leading-relaxed text-slate-500">
          Give the assistant a professional perspective for its analysis — it shapes tone and
          emphasis, never the facts. Answers always come only from your sources, with citations,
          and insufficient evidence is still declared.
        </p>
        <textarea
          value={draft} onChange={(e) => setDraft(e.target.value)}
          rows={2} maxLength={1500} dir={isRTL(draft) ? "rtl" : "ltr"}
          placeholder='e.g. "Act as a lawyer reviewing these contracts" or "Analyze as a compliance officer"'
          className="focus-ring w-full resize-y rounded-xl border border-slate-200 bg-white px-3 py-2 text-[13px] text-slate-700 placeholder:text-slate-400" />
        <div className="mt-2 flex flex-wrap items-center gap-2">
          {state === "active" && (
            <Pill tone="emerald"><Icons.check className="h-3 w-3" />Active — “{roleLabel(role)}” is applied to every question</Pill>
          )}
          {state === "inactive" && (
            <Pill tone="slate">Inactive — answering in General mode</Pill>
          )}
          {state === "unsaved" && (
            <Pill tone="amber"><Icons.alert className="h-3 w-3" />Unsaved changes — not applied until you save</Pill>
          )}
          <span className="ml-auto flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={() => { setDraft(""); onClearRole(); }}
              disabled={!role.trim() && !draft.trim()}
              title="Remove the analysis mode and return to General">
              <Icons.x className="h-3.5 w-3.5" />Clear
            </Button>
            <Button size="sm" onClick={() => onSaveRole(draft)} disabled={!dirty}
              title={dirty ? "Save and apply this analysis mode" : "No changes to save"}>
              <Icons.check className="h-3.5 w-3.5" />Save
            </Button>
          </span>
        </div>
        <p className="mt-2 text-[11px] leading-relaxed text-slate-400">
          Saved in this browser and applied to every question you ask until you clear it.
          The current mode is always shown next to the chat input.
        </p>
      </Card>

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
          This list reflects what is in your workspace right now — answers come only from
          connected sources. New systems (CRM, email, cloud storage) connect through the
          same source model.
        </p>
      </Card>

      {/* ---- workspace data ---- */}
      <Card className="p-4 lg:col-span-2">
        <SectionTitle>Workspace data</SectionTitle>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="max-w-xl text-[12px] leading-relaxed text-slate-500">
            Clearing the workspace removes every uploaded document and database from the index,
            deletes the uploaded files from the server, and clears the current conversation and
            Inspector trace. Your analysis mode is kept. This cannot be undone.
          </p>
          <Button variant="danger" size="md" onClick={confirmReset} disabled={resetting || !hasUploads}
            title={hasUploads ? "Remove all uploaded sources" : "No uploaded sources to remove"}>
            <Icons.refresh className={cn("h-4 w-4", resetting && "animate-spin")} />
            Clear workspace
          </Button>
        </div>
        {!hasUploads && (
          <p className="mt-2 text-[11px] text-slate-400">
            Nothing to clear — your workspace has no uploaded sources.
          </p>
        )}
      </Card>
    </div>
  );
}
