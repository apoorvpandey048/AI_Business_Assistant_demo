"use client";
import React from "react";
import type { AskResponse } from "@/lib/types";
import { IconButton, Icons } from "./ui";
import {
  answerMarkdown, answerWithCitationsMarkdown, fullMarkdown,
  copyText, downloadMarkdown,
} from "@/lib/export";

/* Answer actions — copy / copy-with-citations / export. Icon-only buttons with
   tooltips, shown top-right of the answer card. Each gives transient feedback via
   the toast system (passed in from the page). */
export default function AnswerActions({
  resp, onToast,
}: {
  resp: AskResponse;
  onToast: (msg: string, tone?: "success" | "error" | "info") => void;
}) {
  const [copied, setCopied] = React.useState<string | null>(null);
  const flash = (key: string) => { setCopied(key); window.setTimeout(() => setCopied((k) => (k === key ? null : k)), 1500); };

  const copy = async (key: string, text: string, label: string) => {
    const ok = await copyText(text);
    if (ok) { flash(key); onToast(label); }
    else onToast("Couldn't access the clipboard.", "error");
  };

  const fileBase = (resp.question || "answer").trim().slice(0, 48).replace(/[^\w֐-׿]+/g, "-").replace(/^-+|-+$/g, "") || "answer";

  return (
    <div className="flex items-center gap-0.5">
      <IconButton
        icon={copied === "answer" ? <Icons.check className="h-3.5 w-3.5 text-success" /> : <Icons.copy className="h-3.5 w-3.5" />}
        label="Copy answer"
        onClick={() => copy("answer", answerMarkdown(resp), "Answer copied to clipboard.")}
      />
      <IconButton
        icon={copied === "cited" ? <Icons.check className="h-3.5 w-3.5 text-success" /> : <Icons.shield className="h-3.5 w-3.5" />}
        label="Copy with citations"
        disabled={!resp.citations.length}
        onClick={() => copy("cited", answerWithCitationsMarkdown(resp), "Answer + sources copied.")}
      />
      <IconButton
        icon={<Icons.download className="h-3.5 w-3.5" />}
        label="Export as Markdown"
        onClick={() => { downloadMarkdown(fileBase, fullMarkdown(resp)); onToast("Exported as Markdown."); }}
      />
    </div>
  );
}
