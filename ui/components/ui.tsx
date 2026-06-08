"use client";
import React from "react";
import type { Route } from "@/lib/types";

export function cn(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(" ");
}

export function isRTL(text: string | null | undefined): boolean {
  return !!text && /[֐-׿]/.test(text);
}

/* ---------------- icons (inline, stroke) ---------------- */
type IconProps = { className?: string };
const S = ({ children, className }: { children: React.ReactNode; className?: string }) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"
       strokeLinecap="round" strokeLinejoin="round"
       className={cn("h-4 w-4", className)}>{children}</svg>
);
export const Icons = {
  question: (p: IconProps) => <S {...p}><circle cx="12" cy="12" r="9" /><path d="M9.2 9a2.8 2.8 0 0 1 5.3 1c0 1.8-2.5 2-2.5 3.5" /><path d="M12 17.5h.01" /></S>,
  route: (p: IconProps) => <S {...p}><circle cx="6" cy="6" r="2.2" /><circle cx="18" cy="18" r="2.2" /><path d="M8 6h6a3 3 0 0 1 3 3v6.5" /><path d="M6 8v4a3 3 0 0 0 3 3h3" /></S>,
  search: (p: IconProps) => <S {...p}><circle cx="11" cy="11" r="6.5" /><path d="m20 20-3.5-3.5" /></S>,
  layers: (p: IconProps) => <S {...p}><path d="m12 3 9 5-9 5-9-5 9-5Z" /><path d="m3 13 9 5 9-5" /></S>,
  spark: (p: IconProps) => <S {...p}><path d="M12 3v4M12 17v4M3 12h4M17 12h4" /><path d="M12 8.5 13.4 11 16 12l-2.6 1L12 15.5 10.6 13 8 12l2.6-1L12 8.5Z" /></S>,
  check: (p: IconProps) => <S {...p}><path d="M20 6 9 17l-5-5" /></S>,
  chevron: (p: IconProps) => <S {...p}><path d="m9 18 6-6-6-6" /></S>,
  db: (p: IconProps) => <S {...p}><ellipse cx="12" cy="5.5" rx="7" ry="2.8" /><path d="M5 5.5v13c0 1.5 3.1 2.8 7 2.8s7-1.3 7-2.8v-13" /><path d="M5 12c0 1.5 3.1 2.8 7 2.8s7-1.3 7-2.8" /></S>,
  doc: (p: IconProps) => <S {...p}><path d="M14 3v4a1 1 0 0 0 1 1h4" /><path d="M19 8.5V19a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h6l6 5.5Z" /><path d="M9 13h6M9 17h4" /></S>,
  clock: (p: IconProps) => <S {...p}><circle cx="12" cy="12" r="9" /><path d="M12 7.5V12l3 2" /></S>,
  coin: (p: IconProps) => <S {...p}><circle cx="12" cy="12" r="9" /><path d="M12 7v10M9.5 9.2a2.4 2.4 0 0 1 2.5-1.7c1.3 0 2.4.8 2.4 1.9 0 2.4-4.8 1.2-4.8 3.4 0 1.1 1.1 1.9 2.4 1.9a2.4 2.4 0 0 0 2.5-1.7" /></S>,
  shield: (p: IconProps) => <S {...p}><path d="M12 3 5 6v5c0 4.2 2.9 7.6 7 9 4.1-1.4 7-4.8 7-9V6l-7-3Z" /><path d="m9.2 12 2 2 3.6-3.8" /></S>,
  bolt: (p: IconProps) => <S {...p}><path d="M13 3 5 13h6l-1 8 8-10h-6l1-8Z" /></S>,
  arrowR: (p: IconProps) => <S {...p}><path d="M5 12h14M13 6l6 6-6 6" /></S>,
};

/* ---------------- route badge ---------------- */
export const ROUTE_STYLE: Record<Route, { pill: string; dot: string }> = {
  PDF: { pill: "bg-emerald-400/10 text-emerald-300 ring-emerald-400/25", dot: "bg-emerald-400" },
  SQL: { pill: "bg-sky-400/10 text-sky-300 ring-sky-400/25", dot: "bg-sky-400" },
  HYBRID: { pill: "bg-indigo-400/10 text-indigo-300 ring-indigo-400/25", dot: "bg-indigo-400" },
  NONE: { pill: "bg-slate-400/10 text-slate-300 ring-slate-400/25", dot: "bg-slate-400" },
};

export function RouteBadge({ route, small }: { route: Route; small?: boolean }) {
  const s = ROUTE_STYLE[route];
  return (
    <span className={cn(
      "inline-flex items-center gap-1.5 rounded-md font-semibold ring-1 ring-inset",
      s.pill, small ? "px-1.5 py-0.5 text-[10px]" : "px-2 py-0.5 text-xs")}>
      <span className={cn("h-1.5 w-1.5 rounded-full", s.dot)} />
      {route}
    </span>
  );
}

export function Pill({
  children, tone = "slate", className,
}: {
  children: React.ReactNode;
  tone?: "slate" | "emerald" | "amber" | "sky" | "indigo" | "rose";
  className?: string;
}) {
  const tones: Record<string, string> = {
    slate: "bg-white/[0.04] text-slate-300 ring-white/10",
    emerald: "bg-emerald-400/10 text-emerald-300 ring-emerald-400/25",
    amber: "bg-amber-400/10 text-amber-200 ring-amber-400/25",
    sky: "bg-sky-400/10 text-sky-300 ring-sky-400/25",
    indigo: "bg-indigo-400/10 text-indigo-300 ring-indigo-400/25",
    rose: "bg-rose-400/10 text-rose-300 ring-rose-400/25",
  };
  return (
    <span className={cn(
      "inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-medium ring-1 ring-inset",
      tones[tone], className)}>
      {children}
    </span>
  );
}

export function Card({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("surface", className)}>{children}</div>;
}

export function SectionTitle({ children, hint }: { children: React.ReactNode; hint?: string }) {
  return (
    <div className="mb-2 flex items-baseline justify-between">
      <h3 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">{children}</h3>
      {hint && <span className="text-[11px] text-slate-500">{hint}</span>}
    </div>
  );
}

export function Collapsible({
  title, icon, defaultOpen = true, right, children,
}: {
  title: React.ReactNode;
  icon?: React.ReactNode;
  defaultOpen?: boolean;
  right?: React.ReactNode;
  children: React.ReactNode;
}) {
  const [open, setOpen] = React.useState(defaultOpen);
  return (
    <Card>
      <button onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between px-4 py-3 text-left transition hover:bg-white/[0.02]">
        <span className="flex items-center gap-2.5 text-sm font-semibold text-slate-100">
          <Icons.chevron className={cn("h-3.5 w-3.5 text-slate-500 transition-transform", open && "rotate-90")} />
          {icon && <span className="text-indigo-300/90">{icon}</span>}
          {title}
        </span>
        <span className="flex items-center gap-2">{right}</span>
      </button>
      {open && <div className="border-t border-white/[0.06] px-4 py-3.5">{children}</div>}
    </Card>
  );
}

export function ScoreBar({ value, max = 1 }: { value?: number | null; max?: number }) {
  if (value == null) return <span className="text-slate-600">—</span>;
  const pct = Math.max(4, Math.min(100, (value / max) * 100));
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="h-1.5 w-12 overflow-hidden rounded-full bg-white/[0.06]">
        <span className="block h-full rounded-full bg-gradient-to-r from-indigo-400 to-sky-400"
              style={{ width: `${pct}%` }} />
      </span>
      <span className="font-mono text-[10px] text-slate-400">{value.toFixed(3)}</span>
    </span>
  );
}
