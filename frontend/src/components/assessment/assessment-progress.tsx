"use client";

import { Loader2, Square } from "lucide-react";
import type { MarketId } from "@/lib/api/types";
import { formatElapsed } from "@/lib/format";
import { useNow } from "@/lib/hooks/use-api";
import { ANALYSIS_TIMEOUT_MS } from "@/lib/api/client";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

const STEPS: Record<MarketId, string[]> = {
  us_sec: [
    "Locate the latest annual filing on SEC EDGAR",
    "Download and segment the 10-K",
    "Extract sustainability claims",
    "Retrieve evidence passages for each claim",
    "Evaluate each claim against its evidence",
    "Compute claim, pillar and overall scores",
  ],
  gh_gse: [
    "Resolve the report (submitted URL or verified report on file)",
    "Download and extract the HTML or PDF text",
    "Extract sustainability claims",
    "Retrieve evidence passages for each claim",
    "Evaluate each claim against its evidence",
    "Compute claim, pillar and overall scores",
  ],
};

/**
 * Honest progress for a single long request: elapsed time and what the backend does, without a fake
 * percentage (the API does not report progress).
 */
export function AssessmentProgress({
  market,
  startedAt,
  onCancel,
  sourceUrl,
}: {
  market: MarketId;
  startedAt: number | null;
  onCancel: () => void;
  sourceUrl?: string | null;
}) {
  const now = useNow(true);
  const elapsed = startedAt ? now - startedAt : 0;
  return (
    <Card className="overflow-hidden">
      <div className="relative h-1 overflow-hidden bg-forest-50">
        <div className="absolute inset-y-0 w-1/3 animate-progress bg-forest-500" />
      </div>
      <div className="grid gap-6 p-5 md:grid-cols-[1fr_auto] md:p-6">
        <div role="status" aria-live="polite">
          <p className="flex items-center gap-2 text-[15px] font-semibold text-text">
            <Loader2 aria-hidden className="size-4 animate-spin text-forest-600" />
            Assessment in progress
            <span className="tabular ml-1 font-mono text-[13px] font-normal text-text-muted">{formatElapsed(elapsed)}</span>
          </p>
          <p className="mt-1 max-w-2xl text-[13px] leading-relaxed text-text-muted">
            The backend is processing the full pipeline in a single request. Large filings and PDF reports can take
            several minutes on first run; later requests for the same document are served from the backend cache.
            {sourceUrl ? " Using the submitted report URL." : null} You can keep browsing; the request continues in the
            background and the result appears here when ready.
          </p>
          <ol className="mt-4 grid gap-1.5 text-[13px] text-text-muted sm:grid-cols-2">
            {STEPS[market].map((s, i) => (
              <li key={s} className="flex items-start gap-2">
                <span className="tabular mt-px font-mono text-[11.5px] text-text-subtle">{i + 1}.</span>
                {s}
              </li>
            ))}
          </ol>
        </div>
        <div className="flex flex-col items-start gap-2 md:items-end">
          <Button variant="secondary" size="sm" onClick={onCancel}>
            <Square aria-hidden />
            Stop waiting
          </Button>
          <p className="max-w-56 text-[12px] leading-relaxed text-text-subtle md:text-right">
            Cancels the request in this browser. The backend may still finish and cache the result. Time limit{" "}
            {Math.round(ANALYSIS_TIMEOUT_MS / 60000)} min.
          </p>
        </div>
      </div>
    </Card>
  );
}
