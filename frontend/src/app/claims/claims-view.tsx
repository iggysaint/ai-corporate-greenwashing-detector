"use client";

import Link from "next/link";
import { ArrowLeft, FileSearch, Gauge } from "lucide-react";
import type { MarketId } from "@/lib/api/types";
import { formatDateTime, formatScore, MARKETS } from "@/lib/format";
import { routes, withContext } from "@/lib/routes";
import { CompanyGate } from "@/components/company/company-gate";
import { useWorkspace } from "@/components/providers/workspace-provider";
import { ClaimsExplorer } from "@/components/claims/claims-explorer";
import { Badge } from "@/components/ui/badge";
import { ButtonLink } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { EmptyState } from "@/components/ui/states";

export function ClaimsView() {
  return (
    <CompanyGate purpose="investigate its claims and evidence">
      {({ market, ticker }) => <Claims market={market} ticker={ticker} />}
    </CompanyGate>
  );
}

function Claims({ market, ticker }: { market: MarketId; ticker: string }) {
  const { getAssessment, activeCompany } = useWorkspace();
  const stored = getAssessment(market, ticker);
  const name = stored?.breakdown.company_name ?? (activeCompany?.ticker === ticker ? activeCompany.name : ticker);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={
          <>
            <Link
              href={withContext(routes.assessment, { market, ticker })}
              className="inline-flex items-center gap-1 normal-case hover:text-text"
            >
              <ArrowLeft aria-hidden className="size-3.5" />
              Score dashboard
            </Link>
            <span aria-hidden>·</span>
            <Badge tone="ink">{MARKETS[market].short}</Badge>
            <span className="font-mono normal-case">{ticker}</span>
          </>
        }
        title={`Claims & Evidence — ${name}`}
        description="Every scored claim with its assessment, score calculation, materiality and quoted evidence from the source document."
      />

      {stored ? (
        <>
          <p className="-mt-3 text-[12.5px] text-text-subtle">
            From the assessment retrieved at {formatDateTime(stored.receivedAt)}
            {stored.breakdown.reporting_period ? ` · ${stored.breakdown.reporting_period}` : ""} · overall score{" "}
            {formatScore(stored.breakdown.esg_integrity_score) ?? "not computed (insufficient data)"}
          </p>
          <ClaimsExplorer data={stored.breakdown} />
        </>
      ) : (
        <EmptyState
          icon={FileSearch}
          title="No assessment loaded for this company"
          action={
            <ButtonLink href={withContext(routes.assessment, { market, ticker })}>
              <Gauge aria-hidden />
              Open ESG assessment
            </ButtonLink>
          }
        >
          Claims and evidence come from the score breakdown. Run or load the assessment first; the claim data is then
          available here without re-running the analysis.
        </EmptyState>
      )}
    </div>
  );
}
