"use client";

import { useEffect } from "react";
import { FileText, Gauge, ScanText } from "lucide-react";
import { api } from "@/lib/api/endpoints";
import { formatDate, formatNumber, MARKETS } from "@/lib/format";
import { useApiMutation, useApiQuery } from "@/lib/hooks/use-api";
import { routes, withContext } from "@/lib/routes";
import { useWorkspace } from "@/components/providers/workspace-provider";
import { Badge } from "@/components/ui/badge";
import { Button, ButtonLink } from "@/components/ui/button";
import { Card, CardBody, CardHeader, Field } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { EmptyState, ErrorState, LoadingState, Skeleton, Spinner } from "@/components/ui/states";
import { AssessmentStatus } from "./assessment-status";
import { ExternalLink } from "./external-link";

export function SecProfile({ ticker }: { ticker: string }) {
  const { setActiveCompany } = useWorkspace();
  const company = useApiQuery(`sec-company:${ticker}`, (signal) => api.secCompany(ticker, { signal }));
  const filings = useApiQuery(company.status === "success" ? `sec-filings:${ticker}` : null, (signal) =>
    api.secFilings(ticker, { signal }),
  );
  const latest = useApiQuery(company.status === "success" ? `sec-latest:${ticker}` : null, (signal) =>
    api.secLatestFiling(ticker, { signal }),
  );
  const doc = useApiMutation((signal) => api.secDocumentMetadata(ticker, { signal }));

  useEffect(() => {
    if (company.status === "success") {
      setActiveCompany({ market: "us_sec", ticker: company.data.ticker, name: company.data.company_name });
    }
  }, [company.status, company.data, setActiveCompany]);

  if (company.status === "error") {
    return (
      <div className="space-y-4">
        <PageHeader eyebrow={MARKETS.us_sec.label} title={ticker} />
        <ErrorState error={company.error} onRetry={company.reload} />
      </div>
    );
  }
  if (company.status !== "success") return <LoadingState label={`Identifying ${ticker} on SEC EDGAR…`} />;

  const c = company.data;
  const runHref = withContext(routes.assessment, { market: "us_sec", ticker: c.ticker }, { run: "1" });

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={
          <>
            <Badge tone="ink">US · SEC</Badge>
            <span className="font-mono normal-case">{c.ticker}</span>
          </>
        }
        title={c.company_name}
        description={c.sic_description ? `SIC ${c.sic ?? ""} · ${c.sic_description}` : "Industry classification not reported by SEC."}
        actions={
          <ButtonLink href={runHref} size="lg">
            <Gauge aria-hidden />
            Run ESG Integrity Assessment
          </ButtonLink>
        }
      />

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="space-y-6">
          <Card>
            <CardHeader title="Company identification" description="Verified SEC EDGAR registration metadata." />
            <CardBody>
              <dl className="grid grid-cols-2 gap-x-6 gap-y-4 md:grid-cols-3">
                <Field label="Ticker" value={c.ticker} mono />
                <Field label="Market" value={MARKETS.us_sec.label} />
                <Field label="Exchange" value={c.exchange} />
                <Field label="CIK" value={c.cik} mono />
                <Field label="SIC code" value={c.sic} mono />
                <Field label="Industry (SIC)" value={c.sic_description} />
              </dl>
            </CardBody>
          </Card>

          <Card>
            <CardHeader
              title="Latest annual filing"
              description="The filing an assessment will evaluate: the most recent suitable 10-K or prevailing 10-K/A."
            />
            <CardBody>
              {latest.status === "error" ? (
                <ErrorState error={latest.error} onRetry={latest.reload} compact />
              ) : latest.status !== "success" ? (
                <div className="grid grid-cols-2 gap-4 md:grid-cols-3">
                  {Array.from({ length: 6 }).map((_, i) => (
                    <Skeleton key={i} className="h-10" />
                  ))}
                </div>
              ) : (
                <div className="space-y-4">
                  <dl className="grid grid-cols-2 gap-x-6 gap-y-4 md:grid-cols-3">
                    <Field label="Form" value={latest.data.filing.form_type} />
                    <Field label="Fiscal year" value={latest.data.filing.fiscal_year?.toString()} />
                    <Field label="Period ending" value={formatDate(latest.data.filing.report_date)} />
                    <Field label="Filed" value={formatDate(latest.data.filing.filing_date)} />
                    <Field label="Accession number" value={latest.data.filing.accession_number} mono />
                    <Field label="Amendment" value={latest.data.filing.is_amendment ? "Yes" : "No"} />
                  </dl>
                  <div className="flex flex-col gap-1.5 text-[13px]">
                    <ExternalLink href={latest.data.filing.filing_url}>Primary document · {latest.data.filing.primary_document}</ExternalLink>
                    {latest.data.filing.filing_index_url ? (
                      <ExternalLink href={latest.data.filing.filing_index_url}>SEC filing index</ExternalLink>
                    ) : null}
                  </div>
                  <div className="rounded-md border border-line bg-surface-muted p-4">
                    {doc.status === "success" ? (
                      <div className="space-y-3">
                        <p className="text-[13px] font-medium text-text">{doc.data.title ?? "Processed document"}</p>
                        <dl className="grid grid-cols-2 gap-4 md:grid-cols-4">
                          <Field label="Words" value={formatNumber(doc.data.word_count)} />
                          <Field label="Characters" value={formatNumber(doc.data.character_count)} />
                          <Field label="Sections detected" value={formatNumber(doc.data.total_sections)} />
                          <Field label="Report date" value={formatDate(doc.data.report_date)} />
                        </dl>
                        {doc.data.detected_sections.length > 0 ? (
                          <ul className="flex flex-wrap gap-1.5">
                            {doc.data.detected_sections.map((s) => (
                              <li key={s} className="rounded border border-line bg-surface px-2 py-0.5 text-[12px] text-text-muted">
                                {s}
                              </li>
                            ))}
                          </ul>
                        ) : null}
                      </div>
                    ) : doc.status === "error" ? (
                      <ErrorState error={doc.error} onRetry={() => doc.run()} compact />
                    ) : (
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <p className="text-[13px] text-text-muted">
                          Inspect the processed filing (word count and detected 10-K sections). Downloads and parses the
                          document on the backend.
                        </p>
                        <Button variant="secondary" size="sm" onClick={() => doc.run()} disabled={doc.status === "loading"}>
                          {doc.status === "loading" ? <Spinner className="text-current" /> : <ScanText aria-hidden />}
                          {doc.status === "loading" ? "Processing…" : "Inspect document"}
                        </Button>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Annual filings on EDGAR" description="10-K and 10-K/A filings discovered for this company." />
            {filings.status === "error" ? (
              <CardBody>
                <ErrorState error={filings.error} onRetry={filings.reload} compact />
              </CardBody>
            ) : filings.status !== "success" ? (
              <CardBody className="space-y-2">
                <Skeleton className="h-9" />
                <Skeleton className="h-9" />
                <Skeleton className="h-9" />
              </CardBody>
            ) : filings.data.filings.length === 0 ? (
              <CardBody>
                <EmptyState icon={FileText} title="No annual filings found">
                  SEC EDGAR returned no 10-K or 10-K/A filings for this company.
                </EmptyState>
              </CardBody>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[560px] text-left text-[13px]">
                  <caption className="sr-only">Annual filings</caption>
                  <thead className="border-b border-line bg-surface-muted text-[11.5px] tracking-wider text-text-subtle uppercase">
                    <tr>
                      <th scope="col" className="px-5 py-2.5 font-medium">Form</th>
                      <th scope="col" className="px-3 py-2.5 font-medium">Fiscal year</th>
                      <th scope="col" className="px-3 py-2.5 font-medium">Period ending</th>
                      <th scope="col" className="px-3 py-2.5 font-medium">Filed</th>
                      <th scope="col" className="px-5 py-2.5 font-medium">Source</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {filings.data.filings.map((f) => (
                      <tr key={f.accession_number}>
                        <td className="px-5 py-2.5 font-medium text-text">
                          {f.form_type}
                          {f.is_amendment ? <Badge tone="warn" className="ml-2">Amendment</Badge> : null}
                        </td>
                        <td className="tabular px-3 py-2.5 text-text-muted">{f.fiscal_year ?? "—"}</td>
                        <td className="tabular px-3 py-2.5 text-text-muted">{formatDate(f.report_date) ?? "—"}</td>
                        <td className="tabular px-3 py-2.5 text-text-muted">{formatDate(f.filing_date)}</td>
                        <td className="px-5 py-2.5">
                          <ExternalLink href={f.filing_url}>{f.accession_number}</ExternalLink>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>

        <aside className="space-y-6">
          <AssessmentStatus
            market="us_sec"
            ticker={c.ticker}
            action={
              <ButtonLink href={runHref} variant="secondary">
                <Gauge aria-hidden />
                Run assessment
              </ButtonLink>
            }
          />
          <Card>
            <CardHeader title="What will be assessed" as="h3" />
            <CardBody className="text-[13px] leading-relaxed text-text-muted">
              Sustainability claims are extracted from the latest annual filing, matched with evidence passages from the
              same filing, evaluated, and scored with the backend&apos;s versioned methodology. Only the SEC filing is used; external
              news and third-party ESG data are out of scope.
            </CardBody>
          </Card>
        </aside>
      </div>
    </div>
  );
}
