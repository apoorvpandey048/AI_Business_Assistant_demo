"use client";
import React from "react";
import { Card, Skeleton } from "./ui";

/* Staged skeleton that mirrors the answer layout (badge row → answer lines →
   sources), shown while /ask is in flight. Replaces the bare spinner so the
   loading state previews the shape of what's coming. A live status line cycles
   the real pipeline stages. */
const STAGES = ["Routing", "Retrieving", "Grounding", "Verifying citations"];

export default function AnswerSkeleton() {
  const [stage, setStage] = React.useState(0);
  React.useEffect(() => {
    // Advance through the stage labels; clamp at the last so it reads as "almost done"
    // rather than looping forever on slow requests.
    const id = window.setInterval(() => setStage((s) => Math.min(s + 1, STAGES.length - 1)), 1100);
    return () => window.clearInterval(id);
  }, []);

  return (
    <div className="fade-up space-y-4" role="status" aria-live="polite" aria-busy="true">
      <span className="sr-only">{STAGES[stage]}…</span>

      {/* routing summary row */}
      <Card className="flex items-center gap-3 px-4 py-3">
        <Skeleton className="h-4 w-4 rounded" />
        <Skeleton className="h-4 w-24 rounded" />
        <Skeleton className="h-4 w-20 rounded" />
        <Skeleton className="ml-auto h-4 w-28 rounded" />
      </Card>

      {/* answer card */}
      <Card className="p-5">
        <div className="mb-3 flex items-center justify-between">
          <Skeleton className="h-3 w-16 rounded" />
          <span className="flex items-center gap-2 text-[12px] font-medium text-text-muted">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" />
            {STAGES[stage]}…
          </span>
        </div>
        <div className="space-y-2.5">
          <Skeleton className="h-3.5 w-[92%] rounded" />
          <Skeleton className="h-3.5 w-[97%] rounded" />
          <Skeleton className="h-3.5 w-[85%] rounded" />
          <Skeleton className="h-3.5 w-[70%] rounded" />
        </div>
        <div className="mt-4 flex gap-2 border-t border-line pt-3.5">
          <Skeleton className="h-7 w-20 rounded-lg" />
          <Skeleton className="h-7 w-24 rounded-lg" />
          <Skeleton className="h-7 w-16 rounded-lg" />
        </div>
      </Card>
    </div>
  );
}
