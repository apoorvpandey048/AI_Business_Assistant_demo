"use client";
import React from "react";
import {
  fetchProviders, switchProvider, useDefaultProvider, validateProvider,
} from "@/lib/api";
import type {
  ProviderCheck, ProvidersResponse, ProviderValidation,
} from "@/lib/types";
import { Button, Card, Icons, Pill, SectionTitle, cn } from "./ui";

/* AI Provider settings (sprint §14).

   The provider is switchable from the UI with an explicit save lifecycle that mirrors the
   persona pattern (§12): picking an option is a DRAFT; nothing changes until Apply. The card
   always makes three things legible — the APPLIED provider, the PENDING (drafted) provider,
   and whether there are unsaved changes — then validates the switch end to end and shows
   actionable diagnostics for every failure state. No hard-coded "Connected": all status is
   driven by the backend probe. */

type ProviderTone = "emerald" | "sky" | "slate";
const DEPLOY_TONE: Record<string, ProviderTone> = {
  "Production Recommended": "emerald",
  "Private / Local Deployment": "sky",
  "Advanced Configuration": "slate",
};

function CheckRow({ check }: { check: ProviderCheck }) {
  const tone =
    check.status === "pass" ? "emerald" : check.status === "fail" ? "rose" : "slate";
  const icon =
    check.status === "pass" ? <Icons.check className="h-3 w-3" />
    : check.status === "fail" ? <Icons.alert className="h-3 w-3" />
    : <Icons.clock className="h-3 w-3" />;
  const label = check.name[0].toUpperCase() + check.name.slice(1);
  return (
    <div className="flex flex-col gap-1 rounded-lg border border-slate-200 bg-white px-3 py-2 sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-[12px] font-semibold text-slate-700">{label}</span>
          <Pill tone={tone as "emerald" | "rose" | "slate"}>{icon}{check.status}</Pill>
        </div>
        <p className="mt-0.5 text-[11.5px] leading-relaxed text-slate-500">{check.detail}</p>
        {check.fix && (
          <p className="mt-1 text-[11px] text-amber-700">
            <span className="font-medium">Fix: </span>
            <span className="font-mono">{check.fix}</span>
          </p>
        )}
      </div>
      <span className="shrink-0 font-mono text-[10.5px] text-slate-400">
        {Math.round(check.duration_ms)}ms
      </span>
    </div>
  );
}

export default function ProviderSettings({
  pushToast, onApplied,
}: {
  pushToast: (message: string, tone?: "success" | "error" | "info") => void;
  onApplied: () => void;        // let the page refresh /config (top-bar model + mode)
}) {
  const [data, setData] = React.useState<ProvidersResponse | null>(null);
  const [draft, setDraft] = React.useState<string>("");
  const [busy, setBusy] = React.useState(false);
  const [validating, setValidating] = React.useState(false);
  const [validation, setValidation] = React.useState<ProviderValidation | null>(null);

  const load = React.useCallback(() => {
    fetchProviders().then((d) => { setData(d); setDraft(d.applied); }).catch(() => {});
  }, []);
  React.useEffect(() => { load(); }, [load]);

  const labelFor = React.useCallback((name: string) =>
    data?.options.find((o) => o.name === name)?.label || name, [data]);

  const runValidation = React.useCallback(async () => {
    setValidating(true);
    try {
      const v = await validateProvider();
      setValidation(v);
      fetchProviders().then(setData).catch(() => {});   // health may change after the first live call
      pushToast(v.ok ? v.summary : `Validation found issues — ${v.summary}`, v.ok ? "success" : "error");
    } catch {
      pushToast("Validation could not run — please try again.", "error");
    } finally {
      setValidating(false);
    }
  }, [pushToast]);

  if (!data) {
    return (
      <Card className="p-4 lg:col-span-2">
        <SectionTitle hint="live status — reflects reality">AI Provider</SectionTitle>
        <p className="text-[12px] text-slate-400">Connecting to the engine…</p>
      </Card>
    );
  }

  const dirty = draft !== data.applied;
  const ps = data.status;
  const healthTone = ps.health === "healthy" ? "emerald" : ps.health === "degraded" ? "amber" : "rose";
  const healthText = ps.health === "healthy" ? "Healthy" : ps.health === "degraded" ? "Degraded" : "Unavailable";
  const connTone = ps.connection === "connected" ? "emerald" : ps.connection === "disconnected" ? "rose" : "slate";
  const connText = ps.connection === "connected" ? "Connected" : ps.connection === "disconnected" ? "Disconnected" : "Unknown";

  const apply = async () => {
    if (!dirty) return;
    setBusy(true);
    setValidation(null);
    try {
      const next = await switchProvider(draft);
      setData(next);
      setDraft(next.applied);
      pushToast(`Provider switched to ${labelFor(next.applied)} — validating…`);
      onApplied();
      await runValidation();
    } catch (e: any) {
      pushToast(`Could not switch provider — ${e?.message || "unknown error"}`, "error");
    } finally {
      setBusy(false);
    }
  };

  const revert = async () => {
    setBusy(true);
    setValidation(null);
    try {
      const next = await useDefaultProvider();
      setData(next);
      setDraft(next.applied);
      pushToast(`Reverted to the server default — ${labelFor(next.applied)}.`);
      onApplied();
    } catch {
      pushToast("Could not revert to the server default — please try again.", "error");
    } finally {
      setBusy(false);
    }
  };

  // First-clone guidance shows on ANY non-healthy state — including offline-because-no-key,
  // which is exactly the fresh-clone case where a recovery path matters most.
  const notHealthy = ps.health !== "healthy";

  return (
    <Card className="p-4 lg:col-span-2">
      <SectionTitle hint="select · apply · validate">AI Provider</SectionTitle>
      <p className="mb-3 text-[12px] leading-relaxed text-slate-500">
        Choose where answers are generated. Switching is safe — your uploaded sources, the
        conversation, and the Inspector are preserved. The choice is saved on the server and
        survives a reload. API keys are configured server-side and never reach the browser.
      </p>

      {/* ---- selector ---- */}
      <div className="grid gap-2 sm:grid-cols-3">
        {data.options.map((o) => {
          const selected = draft === o.name;
          const applied = data.applied === o.name;
          return (
            <button
              key={o.name} type="button" onClick={() => setDraft(o.name)}
              className={cn(
                "flex flex-col gap-1.5 rounded-xl border p-3 text-left transition",
                selected ? "border-indigo-400 bg-indigo-50/60 ring-1 ring-indigo-200"
                         : "border-slate-200 bg-white hover:border-slate-300")}>
              <div className="flex items-center justify-between gap-2">
                <span className="flex items-center gap-1.5 text-[13px] font-semibold text-slate-800">
                  <Icons.bolt className={cn("h-3.5 w-3.5", selected ? "text-indigo-500" : "text-slate-400")} />
                  {o.label}
                </span>
                {applied && <Pill tone="emerald"><Icons.check className="h-3 w-3" />applied</Pill>}
              </div>
              <Pill tone={DEPLOY_TONE[o.deployment_mode] || "slate"}>{o.deployment_mode}</Pill>
              <p className="text-[11px] leading-relaxed text-slate-500">{o.description}</p>
            </button>
          );
        })}
      </div>

      {/* ---- state + actions ---- */}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {dirty ? (
          <Pill tone="amber"><Icons.alert className="h-3 w-3" />
            Pending: {labelFor(draft)} — not applied until you click Apply
          </Pill>
        ) : (
          <Pill tone="emerald"><Icons.check className="h-3 w-3" />
            Applied: {labelFor(data.applied)}
            {data.source === "override" ? " (UI override)" : " (server default)"}
          </Pill>
        )}
        <span className="ml-auto flex items-center gap-2">
          {data.overridden && !dirty && (
            <Button variant="ghost" size="sm" onClick={revert} disabled={busy}
              title={`Revert to the server-configured default (${labelFor(data.default)})`}>
              <Icons.refresh className="h-3.5 w-3.5" />Use server default
            </Button>
          )}
          <Button variant="secondary" size="sm" onClick={runValidation} disabled={validating || busy}
            title="Run health, routing, generation, and embedding checks">
            <Icons.shield className={cn("h-3.5 w-3.5", validating && "animate-pulse")} />
            {validating ? "Validating…" : "Run validation"}
          </Button>
          <Button size="sm" onClick={apply} disabled={!dirty || busy}
            title={dirty ? "Switch to the selected provider" : "No change to apply"}>
            <Icons.check className="h-3.5 w-3.5" />{busy ? "Applying…" : "Apply"}
          </Button>
        </span>
      </div>

      {/* ---- live status of the applied provider ---- */}
      <div className="mt-4 grid gap-x-6 gap-y-2 border-t border-slate-100 pt-3 text-[12.5px] text-slate-600 sm:grid-cols-2">
        <div className="flex items-center justify-between">
          <span className="text-slate-500">Deployment</span>
          <Pill tone={DEPLOY_TONE[ps.deployment_mode || ""] || "slate"}>{ps.deployment_mode || "—"}</Pill>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-slate-500">Status</span>
          <Pill tone={healthTone as "emerald" | "amber" | "rose"}>
            {ps.health === "healthy" ? <Icons.check className="h-3 w-3" /> : <Icons.alert className="h-3 w-3" />}
            {healthText}
          </Pill>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-slate-500">Generation model</span>
          <span className="font-mono text-[11.5px]">{ps.generation_model}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-slate-500">Connection</span>
          <Pill tone={connTone as "emerald" | "rose" | "slate"}>
            <span className={cn("h-1.5 w-1.5 rounded-full", ps.connection === "connected" ? "bg-emerald-500" : ps.connection === "disconnected" ? "bg-rose-500" : "bg-slate-400")} />
            {connText}
          </Pill>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-slate-500">Embedding model</span>
          <span className="font-mono text-[11.5px]">{ps.embedding_model}</span>
        </div>
        {ps.base_url && (
          <div className="flex items-center justify-between">
            <span className="text-slate-500">Endpoint</span>
            <span className="font-mono text-[11.5px] text-slate-500">{ps.base_url}</span>
          </div>
        )}
        <p className="text-[11.5px] leading-relaxed text-slate-500 sm:col-span-2">{ps.detail}</p>
        {ps.fix && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[11.5px] text-amber-800 sm:col-span-2">
            <span className="font-medium">To fix: </span><span className="font-mono">{ps.fix}</span>
          </div>
        )}
      </div>

      {/* ---- first-clone guidance ---- */}
      {notHealthy && (
        <div className="mt-3 rounded-lg border border-sky-200 bg-sky-50 px-3 py-2 text-[11.5px] leading-relaxed text-sky-800">
          <span className="font-medium">Getting started: </span>
          {ps.provider === "ollama"
            ? "Install Ollama, run “ollama serve”, then “ollama pull qwen2.5:7b-instruct”. See docs/setup-local.md."
            : "Set the provider’s API key in your server’s .env (OPENAI_API_KEY or ANTHROPIC_API_KEY), then re-validate. See docs/setup-openai.md."}
          {" "}Until configured, the engine still answers with deterministic offline fallbacks.
        </div>
      )}

      {/* ---- validation results ---- */}
      {(validation || validating) && (
        <div className="mt-4 border-t border-slate-100 pt-3">
          <div className="mb-2 flex items-center gap-2">
            <span className="text-[12px] font-semibold text-slate-700">Validation</span>
            {validating && <Pill tone="slate"><Icons.clock className="h-3 w-3" />running…</Pill>}
            {validation && !validating && (
              <Pill tone={validation.ok ? "emerald" : "rose"}>
                {validation.ok ? <Icons.check className="h-3 w-3" /> : <Icons.alert className="h-3 w-3" />}
                {validation.ok ? "passed" : "issues found"}
              </Pill>
            )}
          </div>
          {validation && <p className="mb-2 text-[11.5px] leading-relaxed text-slate-500">{validation.summary}</p>}
          {validation && (
            <div className="grid gap-1.5 sm:grid-cols-2">
              {validation.checks.map((c) => <CheckRow key={c.name} check={c} />)}
            </div>
          )}
        </div>
      )}

      <p className="mt-3 text-[11px] leading-relaxed text-slate-400">
        The default provider is configured server-side (<span className="font-mono">ABA_PROVIDER</span>); a
        switch here overrides it and is saved on the server until you choose “Use server default”. This is a
        single-operator control — gate it behind auth before exposing the app to untrusted users.
      </p>
    </Card>
  );
}
