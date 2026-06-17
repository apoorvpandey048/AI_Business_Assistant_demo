// Build copyable / exportable Markdown from an answer. Pure functions — no DOM —
// so they're easy to test and reuse for both clipboard and file download.
import type { AskResponse, Evidence } from "./types";

export function answerMarkdown(resp: AskResponse): string {
  return resp.answer.trim();
}

function sourcesMarkdown(citations: Evidence[]): string {
  if (!citations.length) return "";
  const lines = citations.map(
    (c) => `- [${c.id}] ${c.citation_label}${c.source_name ? ` — ${c.source_name}` : ""}`,
  );
  return `## Sources\n${lines.join("\n")}`;
}

// Full export: answer + sources + triage + timeline as a single Markdown document.
export function fullMarkdown(resp: AskResponse): string {
  const parts: string[] = [];
  if (resp.question) parts.push(`# ${resp.question.trim()}`);
  parts.push(answerMarkdown(resp));

  const src = sourcesMarkdown(resp.citations);
  if (src) parts.push(src);

  if (resp.triage?.defined && resp.triage.items.length) {
    const order: Array<"red" | "green" | "blue"> = ["red", "green", "blue"];
    const lines: string[] = ["## Triage"];
    for (const level of order) {
      const items = resp.triage.items.filter((i) => i.level === level);
      if (!items.length) continue;
      const legend = resp.triage.legend[level] || level;
      lines.push(`### ${legend}`);
      for (const it of items) {
        const cites = it.evidence_ids.length ? ` ${it.evidence_ids.map((e) => `[${e}]`).join(" ")}` : "";
        lines.push(`- **${it.label}**${it.summary ? ` — ${it.summary}` : ""}${cites}`);
      }
    }
    if (lines.length > 1) parts.push(lines.join("\n"));
  }

  if (resp.timeline && resp.timeline.length) {
    const lines = ["## Timeline"];
    for (const ev of resp.timeline) {
      const cites = ev.evidence_ids.length ? ` ${ev.evidence_ids.map((e) => `[${e}]`).join(" ")}` : "";
      lines.push(`- **${ev.date}** — ${ev.title}${ev.detail ? `: ${ev.detail}` : ""}${cites}`);
    }
    parts.push(lines.join("\n"));
  }

  return parts.join("\n\n") + "\n";
}

// Answer with an inline Sources section (for "Copy with citations").
export function answerWithCitationsMarkdown(resp: AskResponse): string {
  const src = sourcesMarkdown(resp.citations);
  return src ? `${answerMarkdown(resp)}\n\n${src}\n` : answerMarkdown(resp) + "\n";
}

export async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch { /* fall through to legacy path */ }
  // Legacy fallback for non-secure contexts.
  try {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(ta);
    return ok;
  } catch {
    return false;
  }
}

export function downloadMarkdown(filename: string, text: string): void {
  const blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename.endsWith(".md") ? filename : `${filename}.md`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
