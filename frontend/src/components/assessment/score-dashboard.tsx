import Link from "next/link";
import { ArrowRight, CircleAlert, CircleCheck, FileText, Scale, ShieldAlert } from "lucide-react";
import type { EsgScoreBreakdown } from "@/lib/api/types";
import { formatDateTime, formatWeight, humanize, PILLARS } from "@/lib/format";
import { routes, withContext } from "@/lib/routes";
import { safeExternalUrl } from "@/lib/validation";
import { Badge, ConfidenceBadge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader, Field } from "@/components/ui/card";
import { ScoreRing } from "@/components/charts/score-ring";
import { Meter } from "@/components/charts/meter";
import { DistributionBar } from "@/components/charts/distribution-bar";
import { ExternalLink } from "@/components/company/external-link";
import { PillarCard } from "./pillar-card";

/** Claim IDs appear in backend factor strings as "[claim_…]"; link them to the claim in the explorer. */
function FactorText({ text, market, ticker }: { text: string; market: EsgScoreBreakdown["market"]; ticker: string }) {
  const parts = text.split(/(\[[A-Za-z0-9_.:-]+\])/g);
  return (
    <>
      {parts.map((p, i) => {
        const m = /^\[([A-Za-z0-9_.:-]+)\]$/.exec(p);
        if (!m) return <span key={i}>{p}</span>;
        return (
          <Link
            key={i}
            href={withContext(routes.claims, { market, ticker }, { claim: m[1] })}
            className="font-mono text-[11.5px] break-all text-forest-700 hover:underline"
          >
            view claim
          </Link>
        );
      })}
    </>
  );
}

export function Disclaimer({ text }: { text: string }) {
  return (
    <aside
      aria-label="Methodology and scope disclaimer"
      className="flex items-start gap-3 rounded-lg border border-warn/25 bg-warn-bg px-4 py-3.5"
    >
      <ShieldAlert aria-hidden className="mt-0.5 size-4 shrink-0 text-warn" />
      <div className="text-[13px] leading-relaxed">
        <p className="font-semibold text-text">Scope of this score</p>
        <p className="mt-0.5 text-text-muted">{text}</p>
      </div>
    </aside>
  );
}

export function ScoreDashboard({ data }: { data: EsgScoreBreakdown }) {
  const scored = data.score_status === "scored" && data.esg_integrity_score !== null;
  const md = data.materiality_summary ?? {};
  const counts = {
    supported: data.supported_claims,
    partially_supported: data.partially_supported_claims,
    unsubstantiated: data.unsubstantiated_claims,
    inconsistent: data.inconsistent_claims,
    insufficient_evidence: data.insufficient_evidence_claims,
  };
  const pillarFallback = {
    environmental: data.environmental_score,
    social: data.social_score,
    governance: data.governance_score,
  };
  const totalEvaluations = data.rule_based_evaluations + data.llm_evaluations;

  return (
    <div className="space-y-6">
      <Disclaimer text={data.disclaimer} />

      <Card>
        <div className="grid gap-8 p-5 md:p-6 lg:grid-cols-[auto_minmax(0,1fr)_minmax(0,18rem)] lg:items-center">
          <div className="flex justify-center lg:justify-start">
            <ScoreRing score={data.esg_integrity_score} />
          </div>
          <div className="min-w-0 space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={scored ? "forest" : "neutral"}>{scored ? "Scored" : "Insufficient data"}</Badge>
              <ConfidenceBadge value={data.confidence} />
              <Badge tone="neutral" className="font-mono">
                Methodology v{data.methodology_version}
              </Badge>
            </div>
            <h2 className="font-serif text-[22px] leading-snug font-semibold text-text">
              {scored
                ? "ESG Integrity Score"
                : "No overall score: too few assessable claims"}
            </h2>
            <p className="max-w-2xl text-[13.5px] leading-relaxed text-text-muted">
              {scored
                ? "Weighted substantiation of the company's assessable Environmental, Social and Governance claims, based on evidence retrieved from the source document."
                : `An overall score requires at least ${data.methodology_details?.min_assessable_claims ?? 3} assessable E/S/G claims. Missing data is reported as a gap, never as a zero.`}
            </p>
            <dl className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-3">
              <Field label="Reporting period" value={data.reporting_period} />
              <Field label="Assessed" value={formatDateTime(data.assessment_timestamp)} />
              <Field
                label="Claims assessed"
                value={
                  <span className="tabular">
                    {data.total_claims_assessed}
                    <span className="text-text-subtle"> of {data.total_claims_extracted} extracted</span>
                  </span>
                }
              />
            </dl>
          </div>
          <div className="space-y-5 rounded-lg bg-surface-muted p-4 ring-1 ring-line">
            <Meter
              label="Evidence coverage"
              value={data.evidence_coverage}
              description="Share of assessed claims for which relevant evidence was found. Data availability, not corroboration."
            />
            <Meter
              label="Substantiation rate"
              value={data.substantiation_rate}
              tone="ink"
              unavailableText="No assessable claims"
              description="Share of assessable claims rated supported or partially supported."
            />
          </div>
        </div>
      </Card>

      <section aria-labelledby="pillars-title">
        <h2 id="pillars-title" className="mb-3 text-[12px] font-semibold tracking-wider text-text-subtle uppercase">
          ESG pillars
        </h2>
        <div className="grid gap-4 md:grid-cols-3">
          {PILLARS.map((p) => (
            <PillarCard key={p} pillar={p} dimension={data.dimensions?.[p]} fallbackScore={pillarFallback[p]} />
          ))}
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-2">
        <Card>
          <CardHeader
            title="Claim assessment distribution"
            description="All assessed claims. Insufficient-evidence claims (hatched) are excluded from the score."
            action={
              <Link
                href={withContext(routes.claims, { market: data.market, ticker: data.ticker })}
                className="inline-flex items-center gap-1 text-[13px] font-medium text-forest-700 hover:underline"
              >
                Explore claims <ArrowRight aria-hidden className="size-3.5" />
              </Link>
            }
          />
          <CardBody className="space-y-4">
            <DistributionBar counts={counts} />
            <dl className="grid grid-cols-2 gap-x-6 gap-y-3 border-t border-line pt-4 sm:grid-cols-4">
              <Field label="Unmapped to E/S/G" value={String(data.unmapped_claims)} />
              <Field label="Duplicates ignored" value={String(data.duplicate_evaluations_ignored)} />
              <Field label="LLM evaluations" value={String(data.llm_evaluations)} />
              <Field label="Rule-based evaluations" value={String(data.rule_based_evaluations)} />
            </dl>
            {totalEvaluations > 0 && data.llm_evaluations === 0 ? (
              <p className="text-[12.5px] leading-relaxed text-text-muted">
                All evaluations used the deterministic rule-based engine (no LLM configured on the backend).
              </p>
            ) : null}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Materiality context" description="Sector profile and weighting applied in this run." />
          <CardBody className="space-y-4">
            <dl className="grid grid-cols-2 gap-x-6 gap-y-4">
              <Field label="Sector" value={typeof md.sector === "string" ? md.sector : null} />
              <Field label="Industry" value={typeof md.industry === "string" ? md.industry : null} />
              <Field
                label="Matched sector profile"
                value={typeof md.matched_sector_profile === "string" ? humanize(md.matched_sector_profile) : "None (1.0× for all claims)"}
              />
              <Field
                label="Sector-priority claims"
                value={typeof md.sector_priority_matches === "number" ? String(md.sector_priority_matches) : null}
              />
              <Field
                label="Quantified claims"
                value={typeof md.quantified_claims === "number" ? String(md.quantified_claims) : null}
              />
              <Field
                label="Multipliers"
                value={
                  data.methodology_details?.quantified_multiplier !== undefined
                    ? `Quantified ${formatWeight(data.methodology_details.quantified_multiplier)}× · Sector ${formatWeight(
                        data.methodology_details.sector_priority_multiplier ?? 1,
                      )}×`
                    : null
                }
              />
            </dl>
            {data.methodology_details?.confidence_capped_for_rule_based ? (
              <p className="flex items-start gap-2 text-[12.5px] leading-relaxed text-text-muted">
                <Scale aria-hidden className="mt-0.5 size-3.5 shrink-0" />
                Confidence capped at medium because every evaluation was rule-based.
              </p>
            ) : null}
          </CardBody>
        </Card>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Card>
          <CardHeader title="Positive factors" description="Evidence strengthening integrity, as reported by the scoring engine." />
          <CardBody>
            {data.main_positive_factors.length === 0 ? (
              <p className="text-[13px] text-text-subtle italic">No positive factors reported.</p>
            ) : (
              <ul className="space-y-3">
                {data.main_positive_factors.map((f) => (
                  <li key={f} className="flex gap-2.5 text-[13px] leading-relaxed text-text">
                    <CircleCheck aria-hidden className="mt-0.5 size-4 shrink-0 text-supported" />
                    <span className="min-w-0">
                      <FactorText text={f} market={data.market} ticker={data.ticker} />
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Main concerns" description="Contradictions, unverified claims and data gaps, as reported by the scoring engine." />
          <CardBody>
            {data.main_concerns.length === 0 ? (
              <p className="text-[13px] text-text-subtle italic">No concerns reported.</p>
            ) : (
              <ul className="space-y-3">
                {data.main_concerns.map((f) => (
                  <li key={f} className="flex gap-2.5 text-[13px] leading-relaxed text-text">
                    <CircleAlert aria-hidden className="mt-0.5 size-4 shrink-0 text-unsub" />
                    <span className="min-w-0">
                      <FactorText text={f} market={data.market} ticker={data.ticker} />
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader title="Source documents" description="Documents evaluated in this assessment." />
        <CardBody>
          {data.source_document_references.length === 0 ? (
            <p className="text-[13px] text-text-subtle italic">No source document references returned.</p>
          ) : (
            <ul className="space-y-2">
              {data.source_document_references.map((ref) => (
                <li key={ref} className="flex items-start gap-2.5 text-[13px] text-text">
                  <FileText aria-hidden className="mt-0.5 size-4 shrink-0 text-text-subtle" />
                  {safeExternalUrl(ref) ? <ExternalLink href={ref} /> : <span className="break-words">{ref}</span>}
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
