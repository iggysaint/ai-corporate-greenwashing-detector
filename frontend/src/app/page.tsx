import Link from "next/link";
import { ArrowRight, BookOpenText, Building2, FileSearch, Gauge, History, ShieldCheck, XCircle } from "lucide-react";
import { TickerSearch } from "@/components/company/ticker-search";
import { GseDirectory } from "@/components/company/gse-directory";
import { AssessmentBadge } from "@/components/ui/badge";
import { ButtonLink } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { SectionHeading } from "@/components/ui/page-header";
import { ASSESSMENT_DESCRIPTION, ASSESSMENT_ORDER } from "@/lib/format";
import { routes, withContext } from "@/lib/routes";

const WORKFLOW = [
  {
    icon: Building2,
    title: "Find a company",
    body: "Look up a US issuer by exact ticker or browse Ghana Stock Exchange listings.",
    href: routes.explorer,
  },
  {
    icon: Gauge,
    title: "Run an assessment",
    body: "Score the latest SEC 10-K or a GSE annual / sustainability report for claim substantiation.",
    href: routes.assessment,
  },
  {
    icon: FileSearch,
    title: "Investigate claims",
    body: "Trace every claim to its assessment, score calculation and quoted filing evidence.",
    href: routes.claims,
  },
  {
    icon: History,
    title: "Review history",
    body: "See assessments recorded by the running backend session for a company.",
    href: routes.history,
  },
];

const MEASURES = [
  "Whether evidence in the company's own filings or reports corroborates, qualifies, contradicts, or fails to substantiate each extracted claim.",
  "Whether high-materiality, quantified and sector-relevant claims are backed by stronger evidence than generic statements.",
  "How much of the sustainability reporting has retrievable supporting context (evidence coverage).",
];

const NOT_MEASURES = [
  "Total ESG performance or a complete ESG rating",
  "Physical environmental or social impact",
  "Proof that a company is or is not greenwashing",
  "An independent audit, assurance, or investment advice",
];

export default function OverviewPage() {
  return (
    <div className="space-y-8">
      <section
        aria-labelledby="intro-title"
        className="overflow-hidden rounded-xl bg-ink-900 text-white shadow-pop ring-1 ring-ink-800"
      >
        <div className="grid gap-8 p-6 sm:p-8 lg:grid-cols-[1.25fr_1fr] lg:p-10">
          <div>
            <p className="text-[12px] font-medium tracking-[0.14em] text-forest-200 uppercase">
              Corporate sustainability intelligence
            </p>
            <h1 id="intro-title" className="mt-3 font-serif text-[30px] leading-[1.15] font-semibold tracking-tight sm:text-[38px]">
              Test disclosed ESG claims against the evidence companies publish.
            </h1>
            <p className="mt-4 max-w-xl text-[15px] leading-relaxed text-ink-200">
              ESG Integrity Intelligence extracts sustainability claims from SEC 10-K filings and Ghana Stock Exchange
              reports, evaluates each one against retrieved disclosure evidence, and produces a transparent ESG Integrity
              Score with a full, claim-by-claim audit trail.
            </p>
            <div className="mt-6 flex flex-wrap gap-2 text-[12.5px] text-ink-200">
              <span className="rounded-full bg-white/[0.07] px-3 py-1 ring-1 ring-white/10">United States · SEC EDGAR</span>
              <span className="rounded-full bg-white/[0.07] px-3 py-1 ring-1 ring-white/10">Ghana · Ghana Stock Exchange</span>
              <span className="rounded-full bg-white/[0.07] px-3 py-1 ring-1 ring-white/10">Deterministic, versioned methodology</span>
            </div>
          </div>
          <div className="rounded-lg bg-surface p-5 text-text shadow-pop">
            <h2 className="text-[15px] font-semibold">Find a company</h2>
            <p className="mt-0.5 mb-4 text-[13px] text-text-muted">Choose a market and enter an exact ticker.</p>
            <TickerSearch />
          </div>
        </div>
      </section>

      <section aria-labelledby="workflow-title">
        <SectionHeading id="workflow-title">Assessment workflow</SectionHeading>
        <ol className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {WORKFLOW.map((step, i) => {
            const Icon = step.icon;
            return (
              <li key={step.title}>
                <Link
                  href={step.href}
                  className="group flex h-full flex-col rounded-lg border border-line bg-surface p-4 shadow-card transition-colors hover:border-forest-200"
                >
                  <span className="flex items-center justify-between">
                    <span className="flex size-8 items-center justify-center rounded-md bg-forest-50 text-forest-700">
                      <Icon aria-hidden className="size-4" />
                    </span>
                    <span className="tabular font-mono text-[12px] text-text-subtle">0{i + 1}</span>
                  </span>
                  <span className="mt-3 text-[14px] font-semibold text-text">{step.title}</span>
                  <span className="mt-1 flex-1 text-[13px] leading-relaxed text-text-muted">{step.body}</span>
                  <span className="mt-3 inline-flex items-center gap-1 text-[12.5px] font-medium text-forest-700">
                    Open
                    <ArrowRight aria-hidden className="size-3.5 transition-transform group-hover:translate-x-0.5" />
                  </span>
                </Link>
              </li>
            );
          })}
        </ol>
      </section>

      <div className="grid gap-6 xl:grid-cols-[1.4fr_1fr]">
        <Card>
          <CardHeader
            title="What the ESG Integrity Score measures"
            description="A 0–100 measure of the credibility and evidence substantiation of a company's disclosed sustainability claims."
            action={
              <ButtonLink href={routes.methodology} variant="secondary" size="sm">
                <BookOpenText aria-hidden />
                Methodology
              </ButtonLink>
            }
          />
          <CardBody className="grid gap-6 md:grid-cols-2">
            <div>
              <h3 className="flex items-center gap-2 text-[13px] font-semibold text-text">
                <ShieldCheck aria-hidden className="size-4 text-forest-600" />
                It evaluates
              </h3>
              <ul className="mt-2 space-y-2 text-[13px] leading-relaxed text-text-muted">
                {MEASURES.map((m) => (
                  <li key={m} className="flex gap-2">
                    <span aria-hidden className="mt-2 size-1 shrink-0 rounded-full bg-forest-500" />
                    {m}
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <h3 className="flex items-center gap-2 text-[13px] font-semibold text-text">
                <XCircle aria-hidden className="size-4 text-danger" />
                It is not
              </h3>
              <ul className="mt-2 space-y-2 text-[13px] leading-relaxed text-text-muted">
                {NOT_MEASURES.map((m) => (
                  <li key={m} className="flex gap-2">
                    <span aria-hidden className="mt-2 size-1 shrink-0 rounded-full bg-danger/70" />
                    {m}
                  </li>
                ))}
              </ul>
            </div>
          </CardBody>
          <div className="border-t border-line px-5 py-4">
            <h3 className="text-[13px] font-semibold text-text">Claim assessment categories</h3>
            <dl className="mt-3 grid gap-x-6 gap-y-3 md:grid-cols-2">
              {ASSESSMENT_ORDER.map((a) => (
                <div key={a}>
                  <dt>
                    <AssessmentBadge value={a} />
                  </dt>
                  <dd className="mt-1 text-[12.5px] leading-relaxed text-text-muted">{ASSESSMENT_DESCRIPTION[a]}</dd>
                </div>
              ))}
            </dl>
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Ghana Stock Exchange directory"
            description="Live listing data from the GSE listings API used by the backend."
            action={
              <ButtonLink href={withContext(routes.explorer, { market: "gh_gse" })} variant="ghost" size="sm">
                View all
                <ArrowRight aria-hidden />
              </ButtonLink>
            }
          />
          <CardBody>
            <GseDirectory limit={6} compact />
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
