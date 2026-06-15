"use client";
import React from "react";
import type { TriageLevel, TriagePanel as TriagePanelData } from "@/lib/types";
import { Icons, bidiPlaintext, cn, isRTL } from "./ui";

/* ------------------------------------------------------------------ *
 * TriagePanel — the user-defined red / green / blue buckets.
 *
 * The MEANING of each colour is defined by the user (panel.legend) — we
 * NEVER hardcode "urgent" / "severe" semantics. Colour is never the only
 * signal: every column carries a text label + a distinct icon shape +
 * the tone colour, so the panel stays legible for color-blind users.
 * ------------------------------------------------------------------ */

type Cite = (id: string) => void;

// Display order is fixed: red, green, blue (left→right).
const ORDER: TriageLevel[] = ["red", "green", "blue"];

const COLUMN: Record<TriageLevel, {
  fallback: string;
  // distinct shapes — not just colour
  icon: (p: { className?: string }) => React.ReactNode;
  head: string;     // header band
  ring: string;     // column border
  dot: string;      // colour dot
  chipText: string; // count chip text
}> = {
  red: {
    fallback: "Red",
    icon: Icons.alert,        // triangle
    head: "bg-rose-50 text-rose-700",
    ring: "border-rose-200",
    dot: "bg-rose-500",
    chipText: "text-rose-700 bg-rose-100",
  },
  green: {
    fallback: "Green",
    icon: Icons.check,        // checkmark
    head: "bg-emerald-50 text-emerald-700",
    ring: "border-emerald-200",
    dot: "bg-emerald-500",
    chipText: "text-emerald-700 bg-emerald-100",
  },
  blue: {
    fallback: "Blue",
    icon: Icons.info,         // circle-i
    head: "bg-sky-50 text-sky-700",
    ring: "border-sky-200",
    dot: "bg-sky-500",
    chipText: "text-sky-700 bg-sky-100",
  },
};

function CiteChip({ id, onCite }: { id: string; onCite: Cite }) {
  return (
    <button onClick={() => onCite(id)}
      className="inline-flex items-center rounded-md bg-indigo-50 px-1.5 text-[10px] font-bold text-indigo-600 ring-1 ring-indigo-200 transition hover:bg-indigo-100">
      {id}
    </button>
  );
}

function ItemCard({ item, onCite }: { item: TriagePanelData["items"][number]; onCite: Cite }) {
  const rtl = isRTL(`${item.label} ${item.summary}`);
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-2.5 shadow-sm">
      <div dir={rtl ? "rtl" : "ltr"} style={bidiPlaintext}
        className={cn("text-[13px] font-semibold text-slate-800", rtl && "text-right")}>
        {item.label}
      </div>
      {item.summary && (
        <p dir={rtl ? "rtl" : "ltr"} style={bidiPlaintext}
          className={cn("mt-0.5 text-[12px] leading-snug text-slate-600", rtl && "text-right")}>
          {item.summary}
        </p>
      )}
      {item.rule && (
        <p className="mt-1 text-[10.5px] italic text-slate-400">
          rule: {item.rule}
        </p>
      )}
      {item.evidence_ids.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {item.evidence_ids.map((id) => <CiteChip key={id} id={id} onCite={onCite} />)}
        </div>
      )}
    </div>
  );
}

export default function TriagePanel({
  triage, onCite,
}: {
  triage?: TriagePanelData | null;
  onCite: Cite;
}) {
  // Nothing to show unless triage is explicitly defined.
  if (!triage || !triage.defined) return null;

  const byLevel: Record<TriageLevel, TriagePanelData["items"]> = { red: [], green: [], blue: [] };
  for (const it of triage.items) {
    if (byLevel[it.level]) byLevel[it.level].push(it);
  }

  return (
    <section className="surface p-4" aria-label="Triage">
      <div className="mb-3 flex items-center gap-2">
        <Icons.grid className="h-4 w-4 text-indigo-500" />
        <h3 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">Triage</h3>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        {ORDER.map((level) => {
          const col = COLUMN[level];
          const Icon = col.icon;
          const label = triage.legend[level] || col.fallback;
          const items = byLevel[level];
          return (
            <div key={level} className={cn("triage-col flex flex-col rounded-xl border", col.ring)}>
              <div className={cn("flex items-center gap-2 rounded-t-xl px-3 py-2", col.head)}>
                <span className={cn("h-2 w-2 shrink-0 rounded-full", col.dot)} aria-hidden />
                <Icon className="h-3.5 w-3.5 shrink-0" />
                <span className="min-w-0 flex-1 truncate text-[12px] font-semibold" title={label}>{label}</span>
                <span className={cn("rounded px-1.5 text-[10px] font-bold", col.chipText)}>{items.length}</span>
              </div>
              <div className="flex flex-col gap-2 p-2.5">
                {items.length === 0
                  ? <p className="px-1 py-2 text-[11.5px] text-slate-400">No items</p>
                  : items.map((it, i) => <ItemCard key={`${it.label}-${i}`} item={it} onCite={onCite} />)}
              </div>
            </div>
          );
        })}
      </div>

      {triage.note && (
        <p className="mt-3 border-t border-slate-100 pt-2.5 text-[11.5px] text-slate-400">{triage.note}</p>
      )}
    </section>
  );
}
