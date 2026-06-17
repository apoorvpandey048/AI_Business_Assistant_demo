"use client";
import React from "react";
import { Button, Icons, Pill, cn, isRTL } from "./ui";
import { roleLabel } from "@/lib/role";
import { PROMPT_MAX_CHARS, promptState, type PromptKind } from "@/lib/prompt";

/* ------------------------------------------------------------------ *
 * PromptBar — the two user prompts (Analysis mode + Case rules) live here,
 * directly above the question input, as the single source of truth (moved
 * out of Settings).
 *
 * Collapsed: two glanceable chips. Click a chip to expand an inline editor
 * with a draft textarea, char counter, draft-state pill, and Clear / Save.
 * Apply-on-Save is preserved — editing the draft never fires /ask; only Save
 * commits (via the page handlers) and raises the existing toast.
 *
 * Keyboard: Ctrl/Cmd+Enter saves the open editor, Esc closes without applying,
 * focus returns to the chip that opened it.
 * ------------------------------------------------------------------ */

type EditorProps = {
  kind: PromptKind;
  saved: string;
  placeholder: string;
  help: React.ReactNode;
  onSave: (v: string) => void;
  onClear: () => void;
  onClose: (returnFocus: boolean) => void;
};

function PromptEditor({ kind, saved, placeholder, help, onSave, onClear, onClose }: EditorProps) {
  const [draft, setDraft] = React.useState(saved);
  const ref = React.useRef<HTMLTextAreaElement>(null);
  React.useEffect(() => { setDraft(saved); }, [saved]);
  // Autofocus the textarea when the editor opens (focus moves into the disclosure).
  React.useEffect(() => { ref.current?.focus(); }, []);

  const dirty = draft.trim() !== saved.trim();
  const state = promptState(saved, draft);
  const rtl = isRTL(draft);

  const save = () => { if (dirty) { onSave(draft); onClose(true); } };

  return (
    <div
      className="surface-raised mt-2 rounded-xl p-3"
      role="group"
      aria-label={kind === "role" ? "Edit analysis mode" : "Edit case rules"}
      onKeyDown={(e) => {
        if (e.key === "Escape") { e.stopPropagation(); onClose(true); }
        if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); save(); }
      }}
    >
      <textarea
        ref={ref}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        rows={kind === "cases" ? 3 : 2}
        maxLength={PROMPT_MAX_CHARS}
        dir={rtl ? "rtl" : "ltr"}
        placeholder={placeholder}
        className="focus-ring w-full resize-y rounded-lg border border-line bg-surface px-3 py-2 text-[13px] text-text placeholder:text-text-faint" />
      <div className="mt-1 flex items-center justify-between text-[10.5px] text-text-faint">
        <span>{help}</span>
        <span className={cn(draft.length > PROMPT_MAX_CHARS - 100 && "text-warn")}>
          {draft.length}/{PROMPT_MAX_CHARS}
        </span>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        {state === "active" && <Pill tone="emerald"><Icons.check className="h-3 w-3" />Active</Pill>}
        {state === "inactive" && <Pill tone="slate">Inactive</Pill>}
        {state === "unsaved" && <Pill tone="amber"><Icons.alert className="h-3 w-3" />Unsaved changes</Pill>}
        <span className="ml-auto flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={() => { setDraft(""); onClear(); onClose(true); }}
            disabled={!saved.trim() && !draft.trim()}>
            <Icons.x className="h-3.5 w-3.5" />Clear
          </Button>
          <Button size="sm" onClick={save} disabled={!dirty}
            title={dirty ? "Save and apply" : "No changes to save"}>
            <Icons.check className="h-3.5 w-3.5" />Save &amp; apply
          </Button>
        </span>
      </div>
    </div>
  );
}

function Chip({
  active, icon, label, value, open, onClick, chipRef,
}: {
  active: boolean;
  icon: React.ReactNode;
  label: string;
  value: string;
  open: boolean;
  onClick: () => void;
  chipRef: React.RefObject<HTMLButtonElement>;
}) {
  return (
    <button
      ref={chipRef}
      onClick={onClick}
      aria-expanded={open}
      className={cn(
        "focus-ring inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[12px] font-medium ring-1 ring-inset transition",
        active
          ? "bg-accent-soft text-accent ring-accent/30"
          : "bg-surface text-text-muted ring-line hover:bg-surface-muted")}>
      {icon}
      <span className="text-text-faint">{label}</span>
      <span className="font-semibold">{value}</span>
      <Icons.chevron className={cn("h-3 w-3 text-text-faint transition-transform", open && "rotate-90")} />
    </button>
  );
}

export default function PromptBar({
  role, cases, onSaveRole, onClearRole, onSaveCases, onClearCases, openKind, onOpenHandled,
}: {
  role: string;
  cases: string;
  onSaveRole: (v: string) => void;
  onClearRole: () => void;
  onSaveCases: (v: string) => void;
  onClearCases: () => void;
  // External request to open a specific editor (e.g. from the Settings "Edit above" link).
  openKind?: PromptKind | null;
  onOpenHandled?: () => void;
}) {
  const [open, setOpen] = React.useState<PromptKind | null>(null);
  const roleChip = React.useRef<HTMLButtonElement>(null);
  const casesChip = React.useRef<HTMLButtonElement>(null);

  // Honour an external open request (deep-link from Settings), then clear the signal.
  React.useEffect(() => {
    if (openKind) {
      setOpen(openKind);
      onOpenHandled?.();
      // focus the matching chip's editor on next paint (editor autofocuses itself)
    }
  }, [openKind, onOpenHandled]);

  const close = (kind: PromptKind, returnFocus: boolean) => {
    setOpen(null);
    if (returnFocus) (kind === "role" ? roleChip : casesChip).current?.focus();
  };

  return (
    <div className="rounded-xl border border-line bg-surface-muted p-2.5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[11px] font-semibold uppercase tracking-[0.1em] text-text-faint">Answer setup</span>
        <Chip
          chipRef={roleChip}
          active={!!role.trim()}
          icon={<Icons.spark className="h-3.5 w-3.5" />}
          label="Analysis:"
          value={role.trim() ? roleLabel(role) : "General"}
          open={open === "role"}
          onClick={() => setOpen((o) => (o === "role" ? null : "role"))}
        />
        <Chip
          chipRef={casesChip}
          active={!!cases.trim()}
          icon={<Icons.grid className="h-3.5 w-3.5" />}
          label="Triage rules:"
          value={cases.trim() ? "On" : "Off"}
          open={open === "cases"}
          onClick={() => setOpen((o) => (o === "cases" ? null : "cases"))}
        />
      </div>

      {open === "role" && (
        <PromptEditor
          kind="role"
          saved={role}
          placeholder='e.g. "Act as a lawyer reviewing these contracts" or "Analyze as a compliance officer"'
          help="Shapes tone and emphasis only — never the facts."
          onSave={onSaveRole}
          onClear={onClearRole}
          onClose={(rf) => close("role", rf)}
        />
      )}
      {open === "cases" && (
        <PromptEditor
          kind="cases"
          saved={cases}
          placeholder='e.g. "Patients on life support → red; fever or unstable vitals → green; stable → blue"'
          help="Sorts an answer's entities into your three colour panels."
          onSave={onSaveCases}
          onClear={onClearCases}
          onClose={(rf) => close("cases", rf)}
        />
      )}
    </div>
  );
}
