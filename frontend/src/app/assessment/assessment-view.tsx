"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef } from "react";
import { ArrowLeft, FileSearch, Gauge, History, RotateCcw } from "lucide-react";
import { fetchScoreHistory } from "@/lib/api/endpoints";
import type { MarketId } from "@/lib/api/types";
import { formatDateTime, MARKETS } from "@/lib/format";
import { useApiQuery } from "@/lib/hooks/use-api";
import { routes, withContext } from "@/lib/routes";
import { safeExternalUrl, validateReportingPeriod } from "@/lib/validation";
import { isApiError } from "@/lib/api/client";
import { CompanyGate } from "@/components/company/company-gate";
import { assessmentKey, useWorkspace } from "@/components/providers/workspace-provider";
import { AssessmentProgress } from "@/components/assessment/assessment-progress";
import { ScoreDashboard } from "@/components/assessment/score-dashboard";
import { ExternalLink } from "@/components/company/external-link";
import { Badge } from "@/components/ui/badge";
import { Button, ButtonLink } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { EmptyState, ErrorState, Notice } from "@/components/ui/states";

export function AssessmentView() {
  return (
    <CompanyGate purpose="run an ESG Integrity Assessment">
      {({ market, ticker }) => <Assessment key={`${market}:${ticker}`} market={market} ticker={ticker} />}
    </CompanyGate>
  );
}

function Assessment({ market, ticker }: { market: MarketId; ticker: string }) {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const { getAssessment, runs, startAssessment, cancelAssessment, activeCompany } = useWorkspace();
  const stored = getAssessment(market, ticker);
  const run = runs[assessmentKey(market, ticker)] ?? null;

  // GSE document selection from the URL (validated; ignored for SEC).
  const rawSource = market === "gh_gse" ? params.get("source_url") : null;
  const sourceUrl = rawSource && safeExternalUrl(rawSource) ? rawSource : null;
  const rawPeriod = market === "gh_gse" ? (params.get("reporting_period") ?? "") : "";
  const period = validateReportingPeriod(rawPeriod);
  const reportingPeriod = period.ok && period.value ? period.value : null;
  const wantsRun = params.get("run") === "1";

  const history = useApiQuery(stored ? null : `history:${market}:${ticker}`, (signal) =>
    fetchScoreHistory(market, ticker, { signal }),
  );
  const backendHasRecord = history.status === "success" && history.data.total_records > 0;

  const start = (source: { sourceUrl: string | null; reportingPeriod: string | null }) =>
    startAssessment(market, ticker, source);

  // Auto-start when arriving with ?run=1, then drop the flag so a reload does not re-run.
  // startAssessment is idempotent while a run for this company is in flight.
  const started = useRef(false);
  useEffect(() => {
    if (!wantsRun) {
      started.current = false; // re-arm for the next arrival (pages are preserved, not remounted)
      return;
    }
    if (started.current) return;
    started.current = true;
    startAssessment(market, ticker, { sourceUrl, reportingPeriod });
    const next = new URLSearchParams(params.toString());
    next.delete("run");
    router.replace(`${pathname}?${next.toString()}`);
  }, [wantsRun, startAssessment, market, ticker, sourceUrl, reportingPeriod, params, pathname, router]);

  const running = run?.status === "running";
  const runError = run?.status === "error" ? run.error : null;
  const data = stored?.breakdown ?? null;
  const companyName = data?.company_name ?? (activeCompany?.ticker === ticker ? activeCompany.name : ticker);
  const shownSource = running ? run.sourceUrl : (stored?.sourceUrl ?? null);
  const needsSource = isApiError(runError) && runError.code === "gse_document_source_required";

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={
          <>
            <Link
              href={withContext(routes.company, { market, ticker })}
              className="inline-flex items-center gap-1 normal-case hover:text-text"
            >
              <ArrowLeft aria-hidden className="size-3.5" />
              Company profile
            </Link>
            <span aria-hidden>·</span>
            <Badge tone="ink">{MARKETS[market].short}</Badge>
            <span className="font-mono normal-case">{ticker}</span>
          </>
        }
        title={companyName}
        description="ESG Integrity Assessment — credibility and evidence substantiation of disclosed sustainability claims."
        actions={
          data && !running ? (
            <>
              <ButtonLink href={withContext(routes.claims, { market, ticker })} variant="secondary">
                <FileSearch aria-hidden />
                Claims & evidence
              </ButtonLink>
              <ButtonLink href={withContext(routes.history, { market, ticker })} variant="ghost">
                <History aria-hidden />
                History
              </ButtonLink>
              <Button
                variant="secondary"
                onClick={() => start({ sourceUrl: stored?.sourceUrl ?? null, reportingPeriod: stored?.reportingPeriod ?? null })}
              >
                <RotateCcw aria-hidden />
                Re-run
              </Button>
            </>
          ) : null
        }
      />

      {shownSource ? (
        <p className="-mt-3 flex flex-wrap items-center gap-2 text-[13px] text-text-muted">
          Report: <ExternalLink href={shownSource} />
        </p>
      ) : null}

      {running ? (
        <AssessmentProgress
          market={market}
          startedAt={run.startedAt}
          onCancel={() => cancelAssessment(market, ticker)}
          sourceUrl={run.sourceUrl}
        />
      ) : null}

      {runError ? (
        <div className="space-y-3">
          <ErrorState
            error={runError}
            onRetry={
              needsSource || run?.status !== "error"
                ? undefined
                : () => start({ sourceUrl: run.sourceUrl, reportingPeriod: run.reportingPeriod })
            }
          />
          {needsSource ? (
            <ButtonLink href={withContext(routes.company, { market, ticker })} variant="secondary">
              Provide a report URL on the company profile
            </ButtonLink>
          ) : null}
          {data ? <p className="text-[13px] text-text-muted">The previous result from this session is shown below.</p> : null}
        </div>
      ) : null}

      {data && !running ? (
        <>
          <p className="text-[12.5px] text-text-subtle">
            Result retrieved in this browser session at {formatDateTime(stored?.receivedAt)}.
          </p>
          <ScoreDashboard data={data} />
        </>
      ) : null}

      {!data && !running && !runError ? (
        <EmptyState
          icon={Gauge}
          title={backendHasRecord ? "An assessment exists on the backend" : "Not assessed yet"}
          action={
            <Button onClick={() => start({ sourceUrl, reportingPeriod })}>
              <Gauge aria-hidden />
              {backendHasRecord ? "Load latest result" : "Run ESG Integrity Assessment"}
            </Button>
          }
        >
          {backendHasRecord
            ? "The running backend has a cached assessment for this company. Loading it returns the stored breakdown."
            : market === "gh_gse" && !sourceUrl
              ? "Runs against the most recent verified report on file. If none exists, you will be asked for a public report URL."
              : "Runs the full claim extraction, evidence retrieval and scoring pipeline on the latest annual filing. This can take several minutes."}
        </EmptyState>
      ) : null}

      {market === "gh_gse" && !data && !running && !sourceUrl ? (
        <Notice>
          To assess a specific report, open the{" "}
          <Link className="font-medium text-forest-700 hover:underline" href={withContext(routes.company, { market, ticker })}>
            company profile
          </Link>{" "}
          and choose a document or submit a report URL.
        </Notice>
      ) : null}
    </div>
  );
}
