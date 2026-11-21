"use client";

import Link from "next/link";
import { ArrowRight, CircleDashed, Gauge } from "lucide-react";
import { fetchScoreHistory } from "@/lib/api/endpoints";
import type { MarketId } from "@/lib/api/types";
import { formatDateTime, formatScore } from "@/lib/format";
import { useApiQuery } from "@/lib/hooks/use-api";
import { routes, withContext } from "@/lib/routes";
import { useWorkspace } from "@/components/providers/workspace-provider";
import { ConfidenceBadge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/states";

/**
 * Assessment status from real sources only: the result stored in this browser tab, or the backend's
 * in-memory score history. Nothing is shown as "assessed" unless one of those has a record.
 */
export function AssessmentStatus({ market, ticker, action }: { market: MarketId; ticker: string; action: React.ReactNode }) {
  const { getAssessment } = useWorkspace();
  const local = getAssessment(market, ticker);
  const history = useApiQuery(`history:${market}:${ticker}`, (signal) => fetchScoreHistory(market, ticker, { signal }));

  const latestBackend =
    history.status === "success" && history.data.history.length > 0
      ? history.data.history[history.data.history.length - 1]
      : null;
  const latest = local?.breakdown ?? latestBackend;

  return (
    <Card>
      <CardHeader title="Assessment status" description="ESG Integrity assessments for this company in the current sessions." />
      <CardBody className="space-y-4">
        {history.status === "loading" && !local ? (
          <Skeleton className="h-14 w-full" />
        ) : latest ? (
          <div className="flex items-center gap-4">
            <span className="flex size-12 shrink-0 items-center justify-center rounded-lg bg-forest-50 text-forest-700">
              {formatScore(latest.esg_integrity_score) !== null ? (
                <span className="tabular font-serif text-[20px] font-semibold">{formatScore(latest.esg_integrity_score)}</span>
              ) : (
                <CircleDashed aria-label="No score" className="size-5" />
              )}
            </span>
            <div className="min-w-0">
              <p className="text-[13.5px] font-medium text-text">
                {latest.score_status === "scored" ? "Assessed" : "Assessed — insufficient data for a score"}
              </p>
              <p className="mt-0.5 text-[12.5px] text-text-muted">
                {latest.reporting_period ? `${latest.reporting_period} · ` : ""}
                {formatDateTime(latest.assessment_timestamp)}
              </p>
              <div className="mt-1.5">
                <ConfidenceBadge value={latest.confidence} />
              </div>
            </div>
          </div>
        ) : (
          <div className="flex items-start gap-3 text-[13px] text-text-muted">
            <Gauge aria-hidden className="mt-0.5 size-4 shrink-0 text-text-subtle" />
            <p>
              Not yet assessed in this session. The backend keeps assessments in memory only, so results from earlier
              server sessions are not available.
            </p>
          </div>
        )}
        {history.status === "error" ? (
          <p className="text-[12.5px] text-text-subtle">Backend history could not be loaded.</p>
        ) : null}
        <div className="flex flex-wrap gap-2">
          {action}
          {latest ? (
            <Link
              href={withContext(routes.assessment, { market, ticker })}
              className="inline-flex h-10 items-center gap-1.5 px-2 text-[13px] font-medium text-forest-700 hover:underline"
            >
              View result <ArrowRight aria-hidden className="size-3.5" />
            </Link>
          ) : null}
        </div>
      </CardBody>
    </Card>
  );
}
