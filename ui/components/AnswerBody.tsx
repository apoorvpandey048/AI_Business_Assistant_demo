"use client";
import React from "react";
import type { AnswerTable } from "@/lib/types";
import { Icons, bidiPlaintext, cn, isRTL } from "./ui";
import { CitePreview } from "./trace";

/* ------------------------------------------------------------------ *
 * AnswerBody — rich, XSS-safe answer renderer.
 *
 * Renders the answer string with [eN] citation markers preserved and
 * clickable, plus a *tiny* hand-rolled markdown subset (bold, bullet /
 * numbered lists, and pipe tables). No raw HTML is ever injected — every
 * node is a React element built from parsed tokens, so the markdown is
 * safe by construction. (No markdown dependency exists in package.json;
 * a heavy parser is overkill for this controlled, model-generated text.)
 *
 * Citations are split FIRST at the inline level, so an [eN] marker is
 * always a real button regardless of surrounding bold/list/table syntax.
 * ------------------------------------------------------------------ */

type Cite = (id: string) => void;

/* ---------- inline: [eN] citations + **bold** ---------- */
function CiteButton({ id, onCite }: { id: string; onCite: Cite }) {
  return (
    <CitePreview id={id}>
      <button
        onClick={() => onCite(id)}
        className="mx-0.5 inline-flex -translate-y-0.5 items-center rounded-md bg-indigo-50 px-1.5 text-[10px] font-bold text-indigo-600 ring-1 ring-indigo-200 transition hover:bg-indigo-100"
      >
        {id}
      </button>
    </CitePreview>
  );
}

// Splits a run of plain text into bold / normal spans. Bold only — kept
// deliberately minimal. Returns React nodes.
function renderBold(text: string, keyBase: string): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  parts.forEach((part, i) => {
    if (!part) return;
    const b = part.match(/^\*\*([^*]+)\*\*$/);
    if (b) out.push(<strong key={`${keyBase}-b${i}`} className="font-semibold text-slate-900">{b[1]}</strong>);
    else out.push(<React.Fragment key={`${keyBase}-t${i}`}>{part}</React.Fragment>);
  });
  return out;
}

// Inline renderer: split on citations first, then apply bold to the rest.
export function renderInline(text: string, onCite: Cite, keyBase = "i"): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  text.split(/(\[e\d+\])/g).forEach((seg, i) => {
    if (!seg) return;
    const m = seg.match(/^\[(e\d+)\]$/);
    if (m) out.push(<CiteButton key={`${keyBase}-c${i}`} id={m[1]} onCite={onCite} />);
    else out.push(...renderBold(seg, `${keyBase}-${i}`));
  });
  return out;
}

/* ---------- block model ---------- */
type Block =
  | { kind: "p"; lines: string[] }
  | { kind: "ul"; items: string[] }
  | { kind: "ol"; items: string[] }
  | { kind: "table"; header: string[]; rows: string[][] };

function splitPipeRow(line: string): string[] {
  let s = line.trim();
  if (s.startsWith("|")) s = s.slice(1);
  if (s.endsWith("|")) s = s.slice(0, -1);
  return s.split("|").map((c) => c.trim());
}

const isPipeRow = (l: string) => l.includes("|") && /\|/.test(l.trim());
// A markdown table separator row: |---|:--:|---| etc.
const isSepRow = (l: string) => /^\s*\|?[\s:|-]+\|?\s*$/.test(l) && l.includes("-");

function parseBlocks(text: string): Block[] {
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  const blocks: Block[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();

    if (trimmed === "") { i++; continue; }

    // table: a pipe row immediately followed by a separator row
    if (isPipeRow(line) && i + 1 < lines.length && isSepRow(lines[i + 1])) {
      const header = splitPipeRow(line);
      i += 2; // skip header + separator
      const rows: string[][] = [];
      while (i < lines.length && isPipeRow(lines[i]) && lines[i].trim() !== "") {
        rows.push(splitPipeRow(lines[i]));
        i++;
      }
      blocks.push({ kind: "table", header, rows });
      continue;
    }

    // unordered list
    if (/^\s*[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*[-*]\s+/, ""));
        i++;
      }
      blocks.push({ kind: "ul", items });
      continue;
    }

    // ordered list
    if (/^\s*\d+[.)]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*\d+[.)]\s+/, ""));
        i++;
      }
      blocks.push({ kind: "ol", items });
      continue;
    }

    // paragraph: consecutive non-empty, non-structural lines
    const para: string[] = [];
    while (
      i < lines.length &&
      lines[i].trim() !== "" &&
      !/^\s*[-*]\s+/.test(lines[i]) &&
      !/^\s*\d+[.)]\s+/.test(lines[i]) &&
      !(isPipeRow(lines[i]) && i + 1 < lines.length && isSepRow(lines[i + 1]))
    ) {
      para.push(lines[i]);
      i++;
    }
    if (para.length) blocks.push({ kind: "p", lines: para });
  }

  return blocks;
}

/* ---------- inline markdown table (from the answer string) ---------- */
function InlineTable({ header, rows, onCite, rtl }: {
  header: string[]; rows: string[][]; onCite: Cite; rtl: boolean;
}) {
  return (
    <div className="scroll-thin my-3 max-h-80 overflow-auto rounded-xl border border-slate-200">
      <table className="w-full text-left text-[12.5px]" dir={rtl ? "rtl" : "ltr"}>
        <thead className="sticky top-0 bg-slate-100/95 text-slate-500 backdrop-blur">
          <tr>{header.map((h, i) => (
            <th key={i} className="px-3 py-2 font-semibold">{renderInline(h, onCite, `th${i}`)}</th>
          ))}</tr>
        </thead>
        <tbody className="text-slate-700">
          {rows.map((r, ri) => (
            <tr key={ri} className="border-t border-slate-100 hover:bg-slate-50">
              {r.map((c, ci) => (
                <td key={ci} className="px-3 py-2 align-top" style={bidiPlaintext}>
                  {renderInline(c, onCite, `td${ri}-${ci}`)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ---------- structured AnswerTable[] (separate from inline markdown) ---------- */
function StructuredTable({ table, onCite }: { table: AnswerTable; onCite: Cite }) {
  const rtl = isRTL([table.title, ...table.columns, ...table.rows.flat()].join(" "));
  return (
    <div className="surface-muted p-3.5">
      {table.title && (
        <div className="mb-2 flex items-center gap-2">
          <Icons.table className="h-3.5 w-3.5 text-indigo-500" />
          <span dir={rtl ? "rtl" : "ltr"} className="text-[13px] font-semibold text-slate-800">{table.title}</span>
        </div>
      )}
      <div className="scroll-thin max-h-96 overflow-auto rounded-lg border border-slate-200 bg-white">
        <table className="w-full text-left text-[12.5px]" dir={rtl ? "rtl" : "ltr"}>
          <thead className="sticky top-0 bg-slate-100/95 text-slate-500 backdrop-blur">
            <tr>{table.columns.map((c, i) => (
              <th key={i} className="px-3 py-2 font-semibold">{renderInline(c, onCite, `sth${i}`)}</th>
            ))}</tr>
          </thead>
          <tbody className="text-slate-700">
            {table.rows.map((r, ri) => (
              <tr key={ri} className="border-t border-slate-100 hover:bg-slate-50">
                {r.map((c, ci) => (
                  <td key={ci} className="px-3 py-2 align-top" style={bidiPlaintext}>
                    {renderInline(c ?? "", onCite, `std${ri}-${ci}`)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {table.evidence_ids.length > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <span className="text-[10.5px] uppercase tracking-wide text-slate-400">Cited</span>
          {table.evidence_ids.map((id) => <CiteButton key={id} id={id} onCite={onCite} />)}
        </div>
      )}
    </div>
  );
}

/* ---------- main ---------- */
export default function AnswerBody({
  text, tables = [], onCite, rtl,
}: {
  text: string;
  tables?: AnswerTable[];
  onCite: Cite;
  rtl: boolean;
}) {
  const blocks = React.useMemo(() => parseBlocks(text), [text]);
  const dir = rtl ? "rtl" : "ltr";

  // Anomaly B fix — a pipe table in the answer string is ALSO extracted server-side into
  // `tables` (the richer StructuredTable with title + Cited chips). Rendering both yields
  // two <table> for one logical table. When structured tables exist they are the single
  // source of truth, so we drop the inline duplicates. Frontend-only + reversible: we
  // never mutate the grounded answer text.
  const hasStructured = tables.length > 0;
  const inlineTableCount = React.useMemo(
    () => blocks.filter((b) => b.kind === "table").length, [blocks],
  );
  React.useEffect(() => {
    if (process.env.NODE_ENV !== "production" && hasStructured && inlineTableCount !== tables.length) {
      // Drift between the inline pipe tables and the extracted structured set is worth
      // surfacing in dev — it means the extractor missed (or over-captured) a table.
      // eslint-disable-next-line no-console
      console.warn(
        `[AnswerBody] table drift: ${inlineTableCount} inline pipe table(s) vs ${tables.length} structured — suppressing inline to avoid duplicates.`,
      );
    }
  }, [hasStructured, inlineTableCount, tables.length]);

  return (
    <div dir={dir} style={bidiPlaintext} className={cn("text-[15px] leading-[1.75] text-slate-800", rtl && "text-right")}>
      {blocks.map((b, bi) => {
        if (b.kind === "table") return hasStructured ? null : <InlineTable key={bi} header={b.header} rows={b.rows} onCite={onCite} rtl={rtl} />;
        if (b.kind === "ul") return (
          <ul key={bi} className={cn("my-2 space-y-1", rtl ? "mr-5 list-disc" : "ml-5 list-disc")}>
            {b.items.map((it, ii) => <li key={ii}>{renderInline(it, onCite, `ul${bi}-${ii}`)}</li>)}
          </ul>
        );
        if (b.kind === "ol") return (
          <ol key={bi} className={cn("my-2 space-y-1", rtl ? "mr-5 list-decimal" : "ml-5 list-decimal")}>
            {b.items.map((it, ii) => <li key={ii}>{renderInline(it, onCite, `ol${bi}-${ii}`)}</li>)}
          </ol>
        );
        // paragraph — preserve internal line breaks
        return (
          <p key={bi} className="my-2 whitespace-pre-wrap first:mt-0 last:mb-0">
            {b.lines.map((ln, li) => (
              <React.Fragment key={li}>
                {li > 0 && <br />}
                {renderInline(ln, onCite, `p${bi}-${li}`)}
              </React.Fragment>
            ))}
          </p>
        );
      })}

      {tables.length > 0 && (
        <div className="mt-4 space-y-3">
          {tables.map((tbl, i) => <StructuredTable key={i} table={tbl} onCite={onCite} />)}
        </div>
      )}
    </div>
  );
}
