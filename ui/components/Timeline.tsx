"use client";
import React from "react";
import type { TimelineEvent } from "@/lib/types";
import { Icons, bidiPlaintext, cn, isRTL } from "./ui";

/* ------------------------------------------------------------------ *
 * Timeline — a vertical chronology of events.
 *
 * A date rail runs down one side with a node per event; event cards sit
 * on the other side. Semantic <ol> under the hood. RTL answers mirror
 * the rail to the right. Renders nothing when there are no events.
 * ------------------------------------------------------------------ */

type Cite = (id: string) => void;

function CiteChip({ id, onCite }: { id: string; onCite: Cite }) {
  return (
    <button onClick={() => onCite(id)} aria-label={`Citation ${id} — jump to source`}
      className="focus-ring inline-flex items-center rounded-md bg-indigo-50 px-1.5 text-[10px] font-bold text-indigo-600 ring-1 ring-indigo-200 transition hover:bg-indigo-100">
      {id}
    </button>
  );
}

export default function Timeline({
  events = [], onCite,
}: {
  events?: TimelineEvent[];
  onCite: Cite;
}) {
  if (!events || events.length === 0) return null;

  // Direction follows the dominant script of the event content.
  const rtl = isRTL(events.map((e) => `${e.title} ${e.detail}`).join(" "));

  return (
    <section className="surface p-4" aria-label="Timeline">
      <div className="mb-3 flex items-center gap-2">
        <Icons.clock className="h-4 w-4 text-indigo-500" />
        <h3 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">Timeline</h3>
      </div>

      <ol dir={rtl ? "rtl" : "ltr"} className={cn("timeline-rail relative space-y-4", rtl ? "pr-5" : "pl-5")}>
        {events.map((ev, i) => {
          const evRtl = isRTL(`${ev.title} ${ev.detail}`);
          return (
            <li key={i} className="relative">
              {/* node on the rail */}
              <span
                aria-hidden
                className={cn(
                  "absolute top-1.5 h-2.5 w-2.5 rounded-full border-2 border-white bg-indigo-500 shadow ring-1 ring-indigo-200",
                  rtl ? "-right-[1.45rem]" : "-left-[1.45rem]",
                )}
              />
              <div className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
                {ev.date && (
                  <div className="text-[11px] font-bold uppercase tracking-wide text-indigo-600">{ev.date}</div>
                )}
                {ev.title && (
                  <div dir={evRtl ? "rtl" : "ltr"} style={bidiPlaintext}
                    className={cn("mt-0.5 text-[13.5px] font-semibold text-slate-800", evRtl && "text-right")}>
                    {ev.title}
                  </div>
                )}
                {ev.detail && (
                  <p dir={evRtl ? "rtl" : "ltr"} style={bidiPlaintext}
                    className={cn("mt-1 text-[12.5px] leading-snug text-slate-600", evRtl && "text-right")}>
                    {ev.detail}
                  </p>
                )}
                {ev.evidence_ids.length > 0 && (
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {ev.evidence_ids.map((id) => <CiteChip key={id} id={id} onCite={onCite} />)}
                  </div>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
