"use client";
import React from "react";
import type { AppConfig, SourceInfo } from "@/lib/types";
import { roleLabel } from "@/lib/role";
import { Button, Card, Icons, Pill, SectionTitle, cn, isRTL } from "./ui";
import ProviderSettings from "./ProviderSettings";
import type { ToastItem } from "./ui";

/* Both prompt editors (Analysis mode and Case rules) are draft-based: nothing is
   applied until Save. Each card always shows exactly one of three states so the user
   never has to guess:
   - "Active"           saved, non-empty, draft matches what is applied
   - "Inactive"         nothing saved, nothing typed
   - "Unsaved changes"  the draft differs from what is currently applied        */
type PromptState = "active" | "inactive" | "unsaved";

function promptState(saved: string, draft: string): PromptState {
  if (draft.trim() !== saved.trim()) return "unsaved";
  return saved.trim() ? "active" : "inactive";
}

/* A light, plain-language heading that groups several cards together (item 5:
   "settings should be extremely simple and understandable"). */
function GroupHeader({ children, hint }: { children: React.ReactNode; hint?: string }) {
  return (
    <div className="lg:col-span-2 -mb-1 mt-1 first:mt-0">
      <h2 className="text-[13px] font-semibold text-slate-800">{children}</h2>
      {hint && <p className="mt-0.5 text-[12px] leading-relaxed text-slate-500">{hint}</p>}
    </div>
  );
}

export default function Settings({
  role, onSaveRole, onClearRole,
  cases, onSaveCases, onClearCases,
  config, sources, onReset, resetting, hasUploads,
  onOpenSources, pushToast, onRefreshConfig,
}: {
  role: string;                       // the SAVED role — the one applied to questions
  onSaveRole: (r: string) => void;
  onClearRole: () => void;
  cases: string;                      // the SAVED case rules — applied to questions
  onSaveCases: (c: string) => void;
  onClearCases: () => void;
  config: AppConfig | null;
  sources: SourceInfo[];
  onReset: () => void;
  resetting: boolean;
  hasUploads: boolean;
  onOpenSources: () => void;
  pushToast: (message: string, tone?: ToastItem["tone"]) => void;
  onRefreshConfig: () => void;        // refresh /config after a provider switch (top-bar)
}) {
  // ---- analysis mode (role) draft ----
  const [roleDraft, setRoleDraft] = React.useState(role);
  React.useEffect(() => { setRoleDraft(role); }, [role]);
  const roleDirty = roleDraft.trim() !== role.trim();
  const rState = promptState(role, roleDraft);

  // ---- case rules draft ----
  const [casesDraft, setCasesDraft] = React.useState(cases);
  React.useEffect(() => { setCasesDraft(cases); }, [cases]);
  const casesDirty = casesDraft.trim() !== cases.trim();
  const cState = promptState(cases, casesDraft);

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

      {/* ---- analysis mode (persona) ---- */}
      <Card className="p-4 lg:col-span-2">
        <SectionTitle>Analysis mode</SectionTitle>
        <p className="mb-2 text-[12px] leading-relaxed text-slate-500">
          Give the assistant a professional perspective — it shapes tone and emphasis only.
          Insufficient evidence is still declared.
        </p>
        <textarea
          value={roleDraft} onChange={(e) => setRoleDraft(e.target.value)}
          rows={2} maxLength={1500} dir={isRTL(roleDraft) ? "rtl" : "ltr"}
          placeholder='e.g. "Act as a lawyer reviewing these contracts" or "Analyze as a compliance officer"'
          className="focus-ring w-full resize-y rounded-xl border border-slate-200 bg-white px-3 py-2 text-[13px] text-slate-700 placeholder:text-slate-400" />
        <div className="mt-2 flex flex-wrap items-center gap-2">
          {rState === "active" && (
            <Pill tone="emerald"><Icons.check className="h-3 w-3" />Active — “{roleLabel(role)}” is applied to every question</Pill>
          )}
          {rState === "inactive" && (
            <Pill tone="slate">Inactive — answering in General mode</Pill>
          )}
          {rState === "unsaved" && (
            <Pill tone="amber"><Icons.alert className="h-3 w-3" />Unsaved changes — not applied until you save</Pill>
          )}
          <span className="ml-auto flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={() => { setRoleDraft(""); onClearRole(); }}
              disabled={!role.trim() && !roleDraft.trim()}
              title="Remove the analysis mode and return to General">
              <Icons.x className="h-3.5 w-3.5" />Clear
            </Button>
            <Button size="sm" onClick={() => onSaveRole(roleDraft)} disabled={!roleDirty}
              title={roleDirty ? "Save and apply this analysis mode" : "No changes to save"}>
              <Icons.check className="h-3.5 w-3.5" />Save
            </Button>
          </span>
        </div>
        <p className="mt-2 text-[11px] leading-relaxed text-slate-400">
          Saved in this browser and applied to every question until you clear it.
          The current mode is always shown next to the chat input.
        </p>
      </Card>

      {/* ---- case rules (triage) ---- */}
      <Card className="p-4 lg:col-span-2">
        <SectionTitle>Case rules</SectionTitle>
        <p className="mb-2 text-[12px] leading-relaxed text-slate-500">
          Define how results are sorted into the three colour panels (red / green / blue)
          shown with each answer. The meaning of each colour is whatever you write here.
        </p>
        <textarea
          value={casesDraft} onChange={(e) => setCasesDraft(e.target.value)}
          rows={3} maxLength={1500} dir={isRTL(casesDraft) ? "rtl" : "ltr"}
          placeholder='e.g. "Patients on life support → red; with fever or unstable vitals → green; stable → blue"'
          className="focus-ring w-full resize-y rounded-xl border border-slate-200 bg-white px-3 py-2 text-[13px] text-slate-700 placeholder:text-slate-400" />
        <div className="mt-2 flex flex-wrap items-center gap-2">
          {cState === "active" && (
            <Pill tone="emerald"><Icons.check className="h-3 w-3" />Active — triage panels appear with every answer</Pill>
          )}
          {cState === "inactive" && (
            <Pill tone="slate">Inactive — no triage panels shown</Pill>
          )}
          {cState === "unsaved" && (
            <Pill tone="amber"><Icons.alert className="h-3 w-3" />Unsaved changes — not applied until you save</Pill>
          )}
          <span className="ml-auto flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={() => { setCasesDraft(""); onClearCases(); }}
              disabled={!cases.trim() && !casesDraft.trim()}
              title="Remove the case rules and hide triage panels">
              <Icons.x className="h-3.5 w-3.5" />Clear
            </Button>
            <Button size="sm" onClick={() => onSaveCases(casesDraft)} disabled={!casesDirty}
              title={casesDirty ? "Save and apply these case rules" : "No changes to save"}>
              <Icons.check className="h-3.5 w-3.5" />Save
            </Button>
          </span>
        </div>
        <p className="mt-2 text-[11px] leading-relaxed text-slate-400">
          Saved in this browser and applied to every question until you clear it.
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
