"use client";
import React from "react";
import type { Route } from "@/lib/types";

export function cn(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(" ");
}

export function isRTL(text: string | null | undefined): boolean {
  return !!text && /[֐-׿]/.test(text);
}

export const ROUTE_STYLE: Record<Route, string> = {
  PDF: "bg-emerald-500/15 text-emerald-300 ring-emerald-500/30",
  SQL: "bg-sky-500/15 text-sky-300 ring-sky-500/30",
  HYBRID: "bg-indigo-500/15 text-indigo-300 ring-indigo-500/30",
  NONE: "bg-slate-500/15 text-slate-300 ring-slate-500/30",
};

export function RouteBadge({ route, small }: { route: Route; small?: boolean }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md font-semibold ring-1 ring-inset",
        ROUTE_STYLE[route],
        small ? "px-1.5 py-0.5 text-[10px]" : "px-2 py-0.5 text-xs"
      )}
    >
      {route}
    </span>
  );
}

export function Pill({
  children,
  tone = "slate",
}: {
  children: React.ReactNode;
  tone?: "slate" | "emerald" | "amber" | "sky" | "indigo" | "rose";
}) {
  const tones: Record<string, string> = {
    slate: "bg-slate-800 text-slate-300 ring-slate-700",
    emerald: "bg-emerald-500/10 text-emerald-300 ring-emerald-500/30",
    amber: "bg-amber-500/10 text-amber-300 ring-amber-500/30",
    sky: "bg-sky-500/10 text-sky-300 ring-sky-500/30",
    indigo: "bg-indigo-500/10 text-indigo-300 ring-indigo-500/30",
    rose: "bg-rose-500/10 text-rose-300 ring-rose-500/30",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-medium ring-1 ring-inset",
        tones[tone]
      )}
    >
      {children}
    </span>
  );
}

export function Card({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "rounded-xl border border-slate-800 bg-slate-900/60 backdrop-blur",
        className
      )}
    >
      {children}
    </div>
  );
}

export function SectionTitle({
  children,
  hint,
}: {
  children: React.ReactNode;
  hint?: string;
}) {
  return (
    <div className="mb-2 flex items-baseline justify-between">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
        {children}
      </h3>
      {hint && <span className="text-[11px] text-slate-500">{hint}</span>}
    </div>
  );
}

export function Collapsible({
  title,
  defaultOpen = true,
  right,
  children,
}: {
  title: React.ReactNode;
  defaultOpen?: boolean;
  right?: React.ReactNode;
  children: React.ReactNode;
}) {
  const [open, setOpen] = React.useState(defaultOpen);
  return (
    <Card>
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between px-4 py-3 text-left"
      >
        <span className="flex items-center gap-2 text-sm font-semibold text-slate-200">
          <span className="text-slate-500">{open ? "▾" : "▸"}</span>
          {title}
        </span>
        <span className="flex items-center gap-2">{right}</span>
      </button>
      {open && <div className="border-t border-slate-800 px-4 py-3">{children}</div>}
    </Card>
  );
}

export function ScoreBar({ value, max = 1 }: { value?: number | null; max?: number }) {
  if (value == null) return <span className="text-slate-600">—</span>;
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="h-1.5 w-12 overflow-hidden rounded bg-slate-800">
        <span
          className="block h-full rounded bg-indigo-400"
          style={{ width: `${pct}%` }}
        />
      </span>
      <span className="font-mono text-[10px] text-slate-400">{value.toFixed(3)}</span>
    </span>
  );
}
