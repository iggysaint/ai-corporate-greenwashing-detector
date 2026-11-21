"use client";

import { useEffect, useState } from "react";
import { ChevronDown, FileText, Gauge } from "lucide-react";
import { api } from "@/lib/api/endpoints";
import type { MarketDocument } from "@/lib/api/types";
import { formatDate, formatNumber, humanize, MARKETS, SOURCE_TYPE_LABEL } from "@/lib/format";
import { useApiQuery } from "@/lib/hooks/use-api";
import { routes, withContext } from "@/lib/routes";
import { useWorkspace } from "@/components/providers/workspace-provider";
import { Badge } from "@/components/ui/badge";
import { ButtonLink } from "@/components/ui/button";
import { Card, CardBody, CardHeader, Field } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { ErrorState, LoadingState, Notice } from "@/components/ui/states";
import { cn } from "@/lib/utils";
import { AssessmentStatus } from "./assessment-status";
import { ExternalLink } from "./external-link";
import { ReportUrlForm } from "./report-url-form";

function statusTone(status: string) {
  if (status === "retrieved") return "forest" as const;
  if (status === "failed") return "danger" as const;
  if (status === "unavailable") return "warn" as const;
  return "neutral" as const;
}

function DocumentRow({ doc, ticker }: { doc: MarketDocument; ticker: string }) {
  const assessHref = doc.source_url
    ? withContext(
        routes.assessment,
        { market: "gh_gse", ticker },
        { source_url: doc.source_url, reporting_period: doc.reporting_period ?? "", run: "1" },
      )
    : null;
  return (
    <li className="flex flex-col gap-3 px-5 py-4 md:flex-row md:items-center">
      <span className="flex size-9 shrink-0 items-center justify-center rounded-md bg-black/[0.04] text-text-muted">
        <FileText aria-hidden className="size-4" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-[14px] font-medium text-text">{doc.title}</p>
        <p className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[12.5px] text-text-muted">
          <span>{SOURCE_TYPE_LABEL[doc.source_type] ?? humanize(doc.source_type)}</span>
          <span aria-hidden>·</span>
          <span>Period {doc.reporting_period ?? "not stated"}</span>
          {doc.publication_date ? (
            <>
              <span aria-hidden>·</span>
              <span>Published {formatDate(doc.publication_date)}</span>
            </>
          ) : null}
          {doc.format && doc.format !== "unknown" ? (
            <>
              <span aria-hidden>·</span>
              <span className="uppercase">{doc.format}</span>
            </>
          ) : null}
          {doc.word_count ? (
            <>
              <span aria-hidden>·</span>
              <span>{formatNumber(doc.word_count)} words</span>
            </>
          ) : null}
        </p>
        {doc.source_url ? (
          <ExternalLink href={doc.source_url} className="mt-1.5 text-[12.5px]">
            Source document
          </ExternalLink>
        ) : (
          <p className="mt-1.5 text-[12.5px] text-text-subtle italic">No verified source URL on file.</p>
        )}
        {doc.error_message ? <p className="mt-1 text-[12.5px] text-danger">{doc.error_message}</p> : null}
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <Badge tone={statusTone(doc.retrieval_status)}>{humanize(doc.retrieval_status)}</Badge>
        {assessHref ? (
          <ButtonLink href={assessHref} variant="secondary" size="sm">
            <Gauge aria-hidden />
            Assess
          </ButtonLink>
        ) : null}
      </div>
    </li>
  );
}

export function GseProfile({ ticker }: { ticker: string }) {
  const { setActiveCompany } = useWorkspace();
  const detail = useApiQuery(`gse-company:${ticker}`, (signal) => api.gseCompany(ticker, { signal }));
  const [showCustom, setShowCustom] = useState(false);

  useEffect(() => {
    if (detail.status === "success") {
      const c = detail.data.company;
      setActiveCompany({ market: "gh_gse", ticker: c.ticker, name: c.company_name });
    }
  }, [detail.status, detail.data, setActiveCompany]);

  if (detail.status === "error") {
    return (
      <div className="space-y-4">
        <PageHeader eyebrow={MARKETS.gh_gse.label} title={ticker} />
        <ErrorState error={detail.error} onRetry={detail.reload} />
      </div>
    );
  }
  if (detail.status !== "success") return <LoadingState label={`Loading ${ticker} from the Ghana Stock Exchange…`} />;

  const { company: c, documents } = detail.data;
  const verified = documents.filter((d) => Boolean(d.source_url));
  const hasVerified = verified.length > 0;
  const defaultRun = withContext(routes.assessment, { market: "gh_gse", ticker: c.ticker }, { run: "1" });

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={
          <>
            <Badge tone="ink">GH · GSE</Badge>
            <span className="font-mono normal-case">{c.ticker}</span>
          </>
        }
        title={c.company_name}
        description={[c.sector, c.industry].filter(Boolean).join(" · ") || "Sector classification not reported."}
        actions={
          hasVerified ? (
            <ButtonLink href={defaultRun} size="lg">
              <Gauge aria-hidden />
              Run ESG Integrity Assessment
            </ButtonLink>
          ) : null
        }
      />

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="space-y-6">
          <Card>
            <CardHeader title="Company information" description="From the GSE listings source used by the backend." />
            <CardBody>
              <dl className="grid grid-cols-2 gap-x-6 gap-y-4 md:grid-cols-3">
                <Field label="Ticker" value={c.ticker} mono />
                <Field label="Market" value={MARKETS.gh_gse.label} />
                <Field label="ISIN" value={c.isin} mono />
                <Field label="Sector" value={c.sector} />
                <Field label="Industry" value={c.industry} />
                <Field label="Currency" value={c.currency} />
                <Field label="Year listed" value={c.year_listed?.toString()} />
                <Field label="Shares outstanding" value={formatNumber(c.shares_outstanding)} />
                <Field
                  label="Market capitalisation"
                  value={c.market_cap !== null ? `${c.currency} ${formatNumber(c.market_cap)}` : null}
                />
                <Field
                  label="Website"
                  value={c.website ? <ExternalLink href={c.website}>{c.website.replace(/^https?:\/\//, "")}</ExternalLink> : null}
                  className="col-span-2"
                />
              </dl>
            </CardBody>
          </Card>

          <Card>
            <CardHeader
              title="Corporate documents"
              description={
                hasVerified
                  ? "Verified public reports on file for this issuer. Choose one to assess, or supply another report."
                  : "No verified public report is on file. The entries below are expected document types awaiting a source URL."
              }
            />
            <ul className="divide-y divide-line">
              {documents.map((d) => (
                <DocumentRow key={d.document_id} doc={d} ticker={c.ticker} />
              ))}
            </ul>
          </Card>

          <Card>
            {hasVerified ? (
              <>
                <button
                  type="button"
                  onClick={() => setShowCustom((s) => !s)}
                  aria-expanded={showCustom}
                  className="flex w-full items-center justify-between gap-3 px-5 py-4 text-left"
                >
                  <span>
                    <span className="block text-[15px] font-semibold text-text">Assess a different report</span>
                    <span className="mt-0.5 block text-[13px] text-text-muted">
                      Submit the URL of another public annual or sustainability report.
                    </span>
                  </span>
                  <ChevronDown aria-hidden className={cn("size-4 text-text-muted transition-transform", showCustom && "rotate-180")} />
                </button>
                {showCustom ? (
                  <CardBody className="border-t border-line">
                    <ReportUrlForm ticker={c.ticker} />
                  </CardBody>
                ) : null}
              </>
            ) : (
              <>
                <CardHeader
                  title="Provide a report to assess"
                  description="An assessment needs a public annual, integrated or sustainability report for this company."
                />
                <CardBody>
                  <ReportUrlForm ticker={c.ticker} />
                </CardBody>
              </>
            )}
          </Card>
        </div>

        <aside className="space-y-6">
          <AssessmentStatus
            market="gh_gse"
            ticker={c.ticker}
            action={
              hasVerified ? (
                <ButtonLink href={defaultRun} variant="secondary">
                  <Gauge aria-hidden />
                  Run assessment
                </ButtonLink>
              ) : null
            }
          />
          <Notice title="About GSE disclosures">
            Ghana has no centralised filing repository. Reports are retrieved from the URL provided, with the backend
            blocking private addresses and unsafe file types. Without a specified report, the backend uses the most recent
            verified report on file.
          </Notice>
        </aside>
      </div>
    </div>
  );
}
