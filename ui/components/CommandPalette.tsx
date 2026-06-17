"use client";
import React from "react";
import { Icons, Kbd, cn } from "./ui";

/* Command palette (⌘K / Ctrl+K) — fuzzy-ish jump to actions: switch tabs,
   toggle theme, edit prompts, manage sources. Keyboard-first: arrow keys move,
   Enter runs, Esc closes. Focus is trapped in the input while open. */

export interface Command {
  id: string;
  label: string;
  hint?: string;
  icon?: React.ReactNode;
  run: () => void;
}

export default function CommandPalette({
  open, onClose, commands,
}: {
  open: boolean;
  onClose: () => void;
  commands: Command[];
}) {
  const [query, setQuery] = React.useState("");
  const [active, setActive] = React.useState(0);
  const inputRef = React.useRef<HTMLInputElement>(null);

  const filtered = React.useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return commands;
    return commands.filter((c) => `${c.label} ${c.hint ?? ""}`.toLowerCase().includes(q));
  }, [query, commands]);

  React.useEffect(() => {
    if (open) {
      setQuery("");
      setActive(0);
      // focus after paint
      const id = window.setTimeout(() => inputRef.current?.focus(), 0);
      return () => window.clearTimeout(id);
    }
  }, [open]);

  React.useEffect(() => { setActive(0); }, [query]);

  if (!open) return null;

  const run = (cmd?: Command) => {
    if (!cmd) return;
    cmd.run();
    onClose();
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 px-4 pt-[12vh]"
      role="dialog" aria-modal="true" aria-label="Command palette"
      onClick={onClose}
    >
      <div
        className="surface-raised w-full max-w-lg overflow-hidden rounded-xl"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => {
          if (e.key === "Escape") { e.preventDefault(); onClose(); }
          else if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, filtered.length - 1)); }
          else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
          else if (e.key === "Enter") { e.preventDefault(); run(filtered[active]); }
        }}
      >
        <div className="flex items-center gap-2 border-b border-line px-3.5 py-3">
          <Icons.search className="h-4 w-4 text-text-faint" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Type a command…"
            className="w-full bg-transparent text-[14px] text-text outline-none placeholder:text-text-faint"
            aria-label="Command search"
          />
          <Kbd>Esc</Kbd>
        </div>
        <ul className="max-h-80 overflow-auto p-1.5" role="listbox">
          {filtered.length === 0 && (
            <li className="px-3 py-6 text-center text-[12.5px] text-text-faint">No matching commands</li>
          )}
          {filtered.map((c, i) => (
            <li key={c.id} role="option" aria-selected={i === active}>
              <button
                onClick={() => run(c)}
                onMouseEnter={() => setActive(i)}
                className={cn(
                  "flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-[13px] transition",
                  i === active ? "bg-accent-soft text-accent" : "text-text hover:bg-surface-muted")}>
                <span className={cn("shrink-0", i === active ? "text-accent" : "text-text-faint")}>{c.icon}</span>
                <span className="flex-1 font-medium">{c.label}</span>
                {c.hint && <span className="text-[11px] text-text-faint">{c.hint}</span>}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
