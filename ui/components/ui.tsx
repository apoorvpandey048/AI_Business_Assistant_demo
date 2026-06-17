"use client";
import React from "react";
import type { Route } from "@/lib/types";

export function cn(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(" ");
}

/* ---------------- text direction ---------------- */
// Dominant-script direction. "Any Hebrew char anywhere" is wrong for mixed content —
// an English answer that quotes one Hebrew word must NOT flip to RTL (and vice versa).
// We count strong-RTL vs strong-LTR characters and let the majority decide.
const RTL_CHARS = /[֐-׿؀-ۿ܀-ݏיִ-ﭏ]/g;
const LTR_CHARS = /[A-Za-z]/g;

export function textDir(text: string | null | undefined): "rtl" | "ltr" {
  if (!text) return "ltr";
  const rtl = (text.match(RTL_CHARS) || []).length;
  const ltr = (text.match(LTR_CHARS) || []).length;
  return rtl > ltr ? "rtl" : "ltr";
}

export function isRTL(text: string | null | undefined): boolean {
  return textDir(text) === "rtl";
}

// For mixed-direction bodies (Hebrew + English + numbers + [eN] citations): with
// unicode-bidi:plaintext each paragraph resolves its own direction from its first
// strong character, which renders mixed answers correctly regardless of the dir attr.
export const bidiPlaintext: React.CSSProperties = { unicodeBidi: "plaintext" };

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
  upload: (p: IconProps) => <S {...p}><path d="M12 16V4M7 9l5-5 5 5" /><path d="M5 16v2a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-2" /></S>,
  plus: (p: IconProps) => <S {...p}><path d="M12 5v14M5 12h14" /></S>,
  refresh: (p: IconProps) => <S {...p}><path d="M3 12a9 9 0 0 1 15-6.7L21 8" /><path d="M21 3v5h-5" /><path d="M21 12a9 9 0 0 1-15 6.7L3 16" /><path d="M3 21v-5h5" /></S>,
  table: (p: IconProps) => <S {...p}><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M3 9h18M3 14.5h18M9 4v16" /></S>,
  info: (p: IconProps) => <S {...p}><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8h.01" /></S>,
  alert: (p: IconProps) => <S {...p}><path d="M12 3 2.5 19.5h19L12 3Z" /><path d="M12 10v4M12 17h.01" /></S>,
  x: (p: IconProps) => <S {...p}><path d="M18 6 6 18M6 6l12 12" /></S>,
  inspect: (p: IconProps) => <S {...p}><circle cx="11" cy="11" r="7" /><path d="m20 20-3-3" /><path d="M11 8v6M8 11h6" /></S>,
  grid: (p: IconProps) => <S {...p}><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></S>,
  chat: (p: IconProps) => <S {...p}><path d="M21 11.5a8.5 8.5 0 0 1-8.5 8.5c-1.5 0-2.9-.4-4.1-1L3 20l1-5.4A8.5 8.5 0 1 1 21 11.5Z" /></S>,
  gear: (p: IconProps) => <S {...p}><circle cx="12" cy="12" r="3.2" /><path d="M19.4 13.5a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.9 2.9l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5v.2a2 2 0 1 1-4 0v-.2a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.9-2.9l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1h-.2a2 2 0 1 1 0-4h.2a1.7 1.7 0 0 0 1.5-1 1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.9-2.9l.1.1a1.7 1.7 0 0 0 1.9.3 1.7 1.7 0 0 0 1-1.5v-.2a2 2 0 1 1 4 0v.2a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.9 2.9l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.5 1h.2a2 2 0 1 1 0 4h-.2a1.7 1.7 0 0 0-1.5 1Z" /></S>,
};

/* ---------------- tooltip ----------------
   Lightweight hover/focus tooltip. No portal — positioned absolutely against a
   relatively-positioned wrapper. Shows on hover AND keyboard focus (a11y), and is
   exposed to assistive tech via aria-describedby. Pure CSS visibility toggle so it
   honours prefers-reduced-motion automatically. */
export function Tooltip({
  label, children, side = "top", className,
}: {
  label: React.ReactNode;
  children: React.ReactNode;
  side?: "top" | "bottom";
  className?: string;
}) {
  const id = React.useId();
  return (
    <span className={cn("group/tt relative inline-flex", className)}>
      <span aria-describedby={id} tabIndex={0} className="focus-ring inline-flex rounded outline-none">
        {children}
      </span>
      <span
        role="tooltip" id={id}
        className={cn(
          "pointer-events-none absolute left-1/2 z-30 w-max max-w-xs -translate-x-1/2 rounded-lg px-2.5 py-1.5",
          "text-[11.5px] font-medium leading-snug text-white shadow-lg",
          "bg-slate-900/95 opacity-0 transition-opacity duration-150",
          "group-hover/tt:opacity-100 group-focus-within/tt:opacity-100",
          side === "top" ? "bottom-full mb-1.5" : "top-full mt-1.5")}>
        {label}
      </span>
    </span>
  );
}

/* ---------------- route badge ---------------- */
export const ROUTE_STYLE: Record<Route, { pill: string; dot: string; label: string }> = {
  PDF: { pill: "bg-emerald-50 text-emerald-700 ring-emerald-200", dot: "bg-emerald-500", label: "Documents" },
  SQL: { pill: "bg-sky-50 text-sky-700 ring-sky-200", dot: "bg-sky-500", label: "Database" },
  HYBRID: { pill: "bg-indigo-50 text-indigo-700 ring-indigo-200", dot: "bg-indigo-500", label: "Hybrid" },
  NONE: { pill: "bg-slate-100 text-slate-600 ring-slate-200", dot: "bg-slate-400", label: "Insufficient evidence" },
};

export function RouteBadge({ route, small, withLabel }: { route: Route; small?: boolean; withLabel?: boolean }) {
  const s = ROUTE_STYLE[route];
  return (
    <span className={cn(
      "inline-flex items-center gap-1.5 rounded-md font-semibold ring-1 ring-inset",
      s.pill, small ? "px-1.5 py-0.5 text-[10px]" : "px-2 py-0.5 text-xs")}>
      <span className={cn("h-1.5 w-1.5 rounded-full", s.dot)} />
      {route}{withLabel && <span className="font-medium opacity-70">· {s.label}</span>}
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
    slate: "bg-slate-50 text-slate-600 ring-slate-200",
    emerald: "bg-emerald-50 text-emerald-700 ring-emerald-200",
    amber: "bg-amber-50 text-amber-700 ring-amber-200",
    sky: "bg-sky-50 text-sky-700 ring-sky-200",
    indigo: "bg-indigo-50 text-indigo-700 ring-indigo-200",
    rose: "bg-rose-50 text-rose-700 ring-rose-200",
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

/* ---------------- provenance tag (uploaded vs sample) ---------------- */
export function OriginTag({ origin }: { origin?: "sample" | "uploaded" | null }) {
  if (!origin) return null;
  return origin === "uploaded" ? (
    <Pill tone="indigo">Your upload</Pill>
  ) : (
    <Pill tone="slate">Sample data</Pill>
  );
}

export function SectionTitle({ children, hint }: { children: React.ReactNode; hint?: string }) {
  return (
    <div className="mb-2 flex items-baseline justify-between gap-3">
      <h3 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">{children}</h3>
      {hint && <span className="text-[11px] text-slate-400">{hint}</span>}
    </div>
  );
}

/* ---------------- button ---------------- */
export function Button({
  children, onClick, variant = "primary", size = "md", disabled, type = "button", className, title,
}: {
  children: React.ReactNode;
  onClick?: () => void;
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md" | "lg";
  disabled?: boolean;
  type?: "button" | "submit";
  className?: string;
  title?: string;
}) {
  const variants: Record<string, string> = {
    primary: "bg-indigo-600 text-white shadow-sm hover:bg-indigo-700 disabled:bg-indigo-300",
    secondary: "bg-white text-slate-700 ring-1 ring-inset ring-slate-200 hover:bg-slate-50 disabled:opacity-50",
    ghost: "text-slate-600 hover:bg-slate-100 disabled:opacity-50",
    danger: "bg-white text-rose-600 ring-1 ring-inset ring-rose-200 hover:bg-rose-50 disabled:opacity-50",
  };
  const sizes: Record<string, string> = {
    sm: "h-8 px-3 text-[13px] gap-1.5 rounded-lg",
    md: "h-10 px-4 text-sm gap-2 rounded-lg",
    lg: "h-12 px-5 text-sm gap-2 rounded-xl",
  };
  return (
    <button type={type} onClick={onClick} disabled={disabled} title={title}
      className={cn("focus-ring inline-flex shrink-0 items-center justify-center font-semibold transition",
        variants[variant], sizes[size], className)}>
      {children}
    </button>
  );
}

/* ---------------- segmented tab control ---------------- */
export function Tabs<T extends string>({
  tabs, active, onChange,
}: {
  tabs: { id: T; label: string; icon?: React.ReactNode }[];
  active: T;
  onChange: (id: T) => void;
}) {
  return (
    <div className="inline-flex items-center gap-1 rounded-xl border border-slate-200 bg-white p-1 shadow-sm">
      {tabs.map((t) => (
        <button key={t.id} onClick={() => onChange(t.id)}
          className={cn(
            "inline-flex items-center gap-2 rounded-lg px-3.5 py-1.5 text-[13px] font-semibold transition",
            active === t.id
              ? "bg-indigo-600 text-white shadow-sm"
              : "text-slate-500 hover:bg-slate-100 hover:text-slate-700")}>
          {t.icon}{t.label}
        </button>
      ))}
    </div>
  );
}

/* ---------------- collapsible ---------------- */
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
        className="flex w-full items-center justify-between rounded-t-[14px] px-4 py-3 text-left transition hover:bg-slate-50">
        <span className="flex items-center gap-2.5 text-sm font-semibold text-slate-800">
          <Icons.chevron className={cn("h-3.5 w-3.5 text-slate-400 transition-transform", open && "rotate-90")} />
          {icon && <span className="text-indigo-500">{icon}</span>}
          {title}
        </span>
        <span className="flex items-center gap-2">{right}</span>
      </button>
      {open && <div className="border-t border-slate-100 px-4 py-3.5">{children}</div>}
    </Card>
  );
}

/* ---------------- score bar ---------------- */
export function ScoreBar({ value, max = 1 }: { value?: number | null; max?: number }) {
  if (value == null) return <span className="text-slate-300">—</span>;
  const pct = Math.max(4, Math.min(100, (value / max) * 100));
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="h-1.5 w-12 overflow-hidden rounded-full bg-slate-100">
        <span className="block h-full rounded-full bg-indigo-500" style={{ width: `${pct}%` }} />
      </span>
      <span className="font-mono text-[10px] text-slate-500">{value.toFixed(3)}</span>
    </span>
  );
}

/* ---------------- toasts (visual feedback for every state change) ---------------- */
export interface ToastItem {
  id: number;
  message: string;
  tone: "success" | "error" | "info";
}

export function Toasts({ items, onDismiss }: { items: ToastItem[]; onDismiss: (id: number) => void }) {
  if (items.length === 0) return null;
  const tones: Record<ToastItem["tone"], { box: string; icon: React.ReactNode }> = {
    success: { box: "ring-emerald-200 text-emerald-800", icon: <Icons.check className="h-4 w-4 text-emerald-500" /> },
    error: { box: "ring-rose-200 text-rose-700", icon: <Icons.alert className="h-4 w-4 text-rose-500" /> },
    info: { box: "ring-slate-200 text-slate-700", icon: <Icons.info className="h-4 w-4 text-slate-400" /> },
  };
  return (
    <div className="pointer-events-none fixed bottom-5 left-1/2 z-50 flex w-full max-w-md -translate-x-1/2 flex-col items-center gap-2 px-4">
      {items.map((t) => (
        <div key={t.id} role="status"
          className={cn("pointer-events-auto flex w-full items-start gap-2 rounded-xl bg-white px-3.5 py-2.5",
            "text-[12.5px] font-medium shadow-lg ring-1 ring-inset", tones[t.tone].box)}>
          <span className="mt-0.5 shrink-0">{tones[t.tone].icon}</span>
          <span className="min-w-0 flex-1">{t.message}</span>
          <button onClick={() => onDismiss(t.id)} className="shrink-0 text-slate-300 hover:text-slate-500" aria-label="Dismiss">
            <Icons.x className="h-3.5 w-3.5" />
          </button>
        </div>
      ))}
    </div>
  );
}

/* ---------------- empty state ---------------- */
export function EmptyState({
  icon, title, children,
}: { icon?: React.ReactNode; title: string; children?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center px-6 py-14 text-center">
      {icon && (
        <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-indigo-50 text-indigo-500 ring-1 ring-indigo-100">
          {icon}
        </div>
      )}
      <h3 className="text-[15px] font-semibold text-slate-800">{title}</h3>
      {children && <div className="mt-1.5 max-w-md text-sm leading-relaxed text-slate-500">{children}</div>}
    </div>
  );
}
