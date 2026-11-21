"use client";

import Link from "next/link";
import { ArrowLeft, Gauge, History, RotateCcw } from "lucide-react";
import { fetchScoreHistory } from "@/lib/api/endpoints";
import type { EsgIntegrityScore, MarketId } from "@/lib/api/types";
import { formatDateTime, formatPercent, formatScore, MARKETS } from "@/lib/format";
import { useApiQuery } from "@/lib/hooks/use-api";
import { routes, withContext } from "@/lib/routes";
import { CompanyGate } from "@/components/company/company-gate";
import { ConfidenceBadge, Badge } from "@/components/ui/badge";
import { Button, ButtonLink } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { EmptyState, ErrorState, LoadingState, Notice } from "@/components/ui/states";

export function HistoryView() {
  return (
    <CompanyGate purpose="see its recorded assessments">
      {({ market, ticker }) => <HistoryForCompany market={market} ticker={ticker} />}
    </CompanyGate>
  );
}

function ScoreText({ value }: { value: number | null }) {
  const s = formatScore(value);
  return s === null ? <span className="text-text-subtle italic">Insufficient data</span> : <span className="tabular font-semibold">{s}</span>;
}

function HistoryRow({ r }: { r: EsgIntegrityScore }) {
  return (
    <tr className="align-top">
      <td className="px-5 py-3 whitespace-nowrap text-text">{formatDateTime(r.assessment_timestamp)}</td>
      <td className="px-3 py-3 text-text-muted">{r.reporting_period ?? "Not stated"}</td>
      <td className="px-3 py-3 text-right text-[15px]"><ScoreText value={r.esg_integrity_score} /></td>
      <td className="px-3 py-3"><ConfidenceBadge value={r.confidence} /></td>
      <td className="tabular px-3 py-3 text-right text-text-muted">{formatPercent(r.evidence_coverage)}</td>
      <td className="tabular px-3 py-3 text-right text-text-muted">{formatPercent(r.substantiation_rate) ?? "—"}</td>
      <td className="px-3 py-3 text-[12.5px] whitespace-nowrap text-text-muted">
        E <ScoreText value={r.environmental_score} /> · S <ScoreText value={r.social_score} /> · G{" "}
        <ScoreText value={r.governance_score} />
      </td>
      <td className="px-3 py-3 font-mono text-[12px] text-text-muted">v{r.methodology_version}</td>
      <td className="max-w-xs px-5 py-3 text-[12px] break-words text-text-muted">{r.source_document_references[0] ?? "—"}</td>
    </tr>
  );
}

function HistoryForCompany({ market, ticker }: { market: MarketId; ticker: string }) {
  const q = useApiQuery(`history:${market}:${ticker}`, (signal) => fetchScoreHistory(market, ticker, { signal }));
  const records = q.status === "success" ? [...q.data.history].reverse() : [];

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
        title={`Assessment History${q.status === "success" && q.data.total_records > 0 ? ` — ${q.data.company_name}` : ""}`}
        description="Assessments actually computed by the running backend for this company. No historical scores are estimated."
        actions={
          <Button variant="secondary" onClick={q.reload} disabled={q.status === "loading"}>
            <RotateCcw aria-hidden />
            Refresh
          </Button>
        }
      />

      <Notice title="Session-limited records">
        {q.status === "success" ? q.data.note : "The backend stores assessment history in memory only. Records are cleared when the server restarts."}
      </Notice>

      {q.status === "error" ? (
        <ErrorState error={q.error} onRetry={q.reload} />
      ) : q.status !== "success" ? (
        <LoadingState label="Loading recorded assessments…" />
      ) : records.length === 0 ? (
        <EmptyState
          icon={History}
          title="No assessments recorded"
          action={
            <ButtonLink href={withContext(routes.assessment, { market, ticker })}>
              <Gauge aria-hidden />
              Open ESG assessment
            </ButtonLink>
          }
        >
          The running backend has not computed an assessment for {ticker} yet. Run one and it will be listed here for the
          rest of the server session.
        </EmptyState>
      ) : (
        <Card className="overflow-hidden">
          <div className="flex items-center justify-between border-b border-line px-5 py-3 text-[13px]">
            <span className="text-text-muted">
              <span className="tabular font-semibold text-text">{q.data.total_records}</span> record
              {q.data.total_records === 1 ? "" : "s"}, most recent first. One record per source document and methodology version.
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[960px] text-left text-[13px]">
              <caption className="sr-only">Recorded ESG Integrity assessments</caption>
              <thead className="border-b border-line bg-surface-muted text-[11px] tracking-wider text-text-subtle uppercase">
                <tr>
                  <th scope="col" className="px-5 py-2.5 font-medium">Assessed</th>
                  <th scope="col" className="px-3 py-2.5 font-medium">Period</th>
                  <th scope="col" className="px-3 py-2.5 text-right font-medium">Score</th>
                  <th scope="col" className="px-3 py-2.5 font-medium">Confidence</th>
                  <th scope="col" className="px-3 py-2.5 text-right font-medium">Coverage</th>
                  <th scope="col" className="px-3 py-2.5 text-right font-medium">Substantiation</th>
                  <th scope="col" className="px-3 py-2.5 font-medium">Pillars</th>
                  <th scope="col" className="px-3 py-2.5 font-medium">Method</th>
                  <th scope="col" className="px-5 py-2.5 font-medium">Source</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {records.map((r) => (
                  <HistoryRow key={`${r.assessment_timestamp}-${r.source_document_references.join("|")}`} r={r} />
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}
