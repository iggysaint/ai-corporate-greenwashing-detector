"use client";

import { Check, Minus, Quote, ScanSearch } from "lucide-react";
import { api } from "@/lib/api/endpoints";
import type { ClaimScoreDetail, EsgScoreBreakdown, SingleClaimEvaluationResponse } from "@/lib/api/types";
import {
  ASSESSMENT_DESCRIPTION,
  claimTypeLabel,
  CONFIDENCE_LABEL,
  formatDateTime,
  formatScore,
  formatSigned,
  formatWeight,
  humanize,
  pillarLabel,
} from "@/lib/format";
import { useApiMutation } from "@/lib/hooks/use-api";
import { AssessmentBadge, Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ErrorState, Spinner } from "@/components/ui/states";
import { cn } from "@/lib/utils";

function Section({ title, children, className }: { title: string; children: React.ReactNode; className?: string }) {
  return (
    <section className={cn("border-b border-line px-5 py-5 last:border-b-0", className)}>
      <h3 className="mb-3 text-[11.5px] font-semibold tracking-wider text-text-subtle uppercase">{title}</h3>
      {children}
    </section>
  );
}

function Row({ label, value, strong }: { label: React.ReactNode; value: React.ReactNode; strong?: boolean }) {
  return (
    <div className={cn("flex items-baseline justify-between gap-4 py-1.5 text-[13px]", strong && "border-t border-line pt-2.5 font-semibold")}>
      <dt className={strong ? "text-text" : "text-text-muted"}>{label}</dt>
      <dd className="tabular text-right font-mono text-text">{value}</dd>
    </div>
  );
}

/** Full traceable record for a single claim, using only fields returned by the score breakdown. */
export function ClaimDetail({ claim, breakdown }: { claim: ClaimScoreDetail; breakdown: EsgScoreBreakdown }) {
  const md = breakdown.methodology_details ?? {};
  const band = md.assessment_bands?.[claim.assessment];
  const typeWeight = md.claim_type_materiality?.[claim.claim_type];
  const quantMult = md.quantified_multiplier;
  const sectorMult = md.sector_priority_multiplier;
  const excluded = claim.assessment === "insufficient_evidence";

  return (
    <div>
      <Section title="Claim">
        <blockquote className="border-l-2 border-forest-500 pl-4 text-[14.5px] leading-relaxed whitespace-pre-line text-text">
          {claim.claim_text}
        </blockquote>
        <div className="mt-4 flex flex-wrap gap-1.5">
          <Badge tone="info">{pillarLabel(claim.category_group)}</Badge>
          <Badge>{humanize(claim.category)}</Badge>
          <Badge>{claimTypeLabel(claim.claim_type)}</Badge>
          {claim.is_quantified ? <Badge tone="forest">Quantified</Badge> : null}
          {claim.sector_priority_match ? <Badge tone="forest">Sector priority</Badge> : null}
        </div>
        <dl className="mt-4 grid grid-cols-1 gap-2 text-[12px] sm:grid-cols-2">
          <div>
            <dt className="text-text-subtle">Claim ID</dt>
            <dd className="font-mono break-all text-text-muted">{claim.claim_id}</dd>
          </div>
          <div>
            <dt className="text-text-subtle">Evaluation ID</dt>
            <dd className="font-mono break-all text-text-muted">{claim.evaluation_id}</dd>
          </div>
        </dl>
        {breakdown.source_document_references.length > 0 ? (
          <p className="mt-3 text-[12px] leading-relaxed text-text-muted">
            <span className="text-text-subtle">Source: </span>
            {breakdown.source_document_references[0]}
          </p>
        ) : null}
      </Section>

      <Section title="Assessment">
        <div className="flex flex-wrap items-center gap-3">
          <AssessmentBadge value={claim.assessment} className="text-[13px]" />
          <span className="text-[12.5px] text-text-muted">{ASSESSMENT_DESCRIPTION[claim.assessment]}</span>
        </div>
        <p className="mt-3 text-[13.5px] leading-relaxed whitespace-pre-line text-text">{claim.reasoning}</p>
      </Section>

      <Section title="Claim score calculation">
        {excluded ? (
          <p className="text-[13px] leading-relaxed text-text-muted">
            Excluded from scoring: no relevant evidence was retrieved. This claim reduces evidence coverage instead of
            lowering the score.
          </p>
        ) : (
          <dl>
            <Row label="Base score for assessment" value={formatScore(claim.base_score)} />
            <Row label="Evidence-quality adjustment" value={formatSigned(claim.evidence_quality_adjustment)} />
            {band ? (
              <Row
                label="Permitted band"
                value={band.min === band.max ? `fixed ${band.min}` : `${band.min} – ${band.max}`}
              />
            ) : null}
            <Row label="Claim score" value={formatScore(claim.claim_score)} strong />
          </dl>
        )}
        {claim.quality_adjustment_reasons.length > 0 ? (
          <ul className="mt-3 space-y-1 rounded-md bg-surface-muted px-3 py-2.5 text-[12.5px] text-text-muted ring-1 ring-line">
            {claim.quality_adjustment_reasons.map((r) => (
              <li key={r} className="font-mono text-[12px]">
                {r}
              </li>
            ))}
          </ul>
        ) : !excluded ? (
          <p className="mt-3 text-[12.5px] text-text-subtle">No evidence-quality adjustments applied.</p>
        ) : null}
      </Section>

      <Section title="Materiality">
        <dl>
          <Row
            label={`Claim type weight (${claimTypeLabel(claim.claim_type)})`}
            value={typeWeight !== undefined ? formatWeight(typeWeight) : "—"}
          />
          <Row
            label={
              <span className="inline-flex items-center gap-1.5">
                {claim.is_quantified ? <Check aria-hidden className="size-3.5 text-supported" /> : <Minus aria-hidden className="size-3.5" />}
                Quantified multiplier
              </span>
            }
            value={claim.is_quantified && quantMult !== undefined ? `× ${formatWeight(quantMult)}` : "× 1.0"}
          />
          <Row
            label={
              <span className="inline-flex items-center gap-1.5">
                {claim.sector_priority_match ? <Check aria-hidden className="size-3.5 text-supported" /> : <Minus aria-hidden className="size-3.5" />}
                Sector-priority multiplier
              </span>
            }
            value={claim.sector_priority_match && sectorMult !== undefined ? `× ${formatWeight(sectorMult)}` : "× 1.0"}
          />
          <Row label="Materiality weight" value={formatWeight(claim.materiality_weight)} strong />
          <Row label="Effective weight after damping" value={formatWeight(claim.effective_weight)} />
          <Row label="Included in pillar & overall score" value={claim.included_in_score ? "Yes" : "No"} />
        </dl>
        {!claim.included_in_score && !excluded && claim.category_group !== "environmental" && claim.category_group !== "social" && claim.category_group !== "governance" ? (
          <p className="mt-2 text-[12.5px] text-text-muted">Not mapped to an E, S or G pillar, so excluded from scores.</p>
        ) : null}
      </Section>

      <Section title={`Supporting evidence (${claim.referenced_evidence.length})`}>
        {claim.referenced_evidence.length === 0 ? (
          <p className="text-[13px] text-text-subtle italic">
            No validated evidence citation for this assessment
            {claim.referenced_evidence_ids.length > 0 ? ` (IDs: ${claim.referenced_evidence_ids.join(", ")})` : ""}.
          </p>
        ) : (
          <ol className="space-y-4">
            {claim.referenced_evidence.map((ev, i) => (
              <li key={`${ev.evidence_id}-${i}`} className="rounded-md border border-line bg-surface-muted">
                <div className="flex flex-wrap items-center gap-2 border-b border-line px-3.5 py-2 text-[12px]">
                  <span className="tabular font-mono text-text-subtle">#{i + 1}</span>
                  <Badge tone={ev.relationship === "supporting" ? "forest" : ev.relationship === "contradicting" ? "danger" : "neutral"}>
                    {humanize(ev.relationship)}
                  </Badge>
                  <span className="text-text-muted">
                    Section <span className="font-mono text-text">{ev.section_id}</span>
                  </span>
                  <span className="ml-auto flex items-center gap-2 text-text-muted">
                    Relevance
                    <span className="h-1.5 w-16 overflow-hidden rounded-full bg-black/[0.08]" aria-hidden>
                      <span className="block h-full rounded-full bg-forest-600" style={{ width: `${Math.round(ev.relevance_score * 100)}%` }} />
                    </span>
                    <span className="tabular font-mono text-text">{ev.relevance_score.toFixed(2)}</span>
                  </span>
                </div>
                <figure className="px-3.5 py-3">
                  <Quote aria-hidden className="mb-1 size-3.5 text-text-subtle" />
                  <blockquote className="text-[13px] leading-relaxed whitespace-pre-line text-text">{ev.quote}</blockquote>
                  <figcaption className="mt-2 font-mono text-[11.5px] break-all text-text-subtle">{ev.evidence_id}</figcaption>
                </figure>
              </li>
            ))}
          </ol>
        )}
      </Section>

      <Section title="Caveats & limitations">
        <p className="text-[13px] text-text">
          <span className="tabular font-semibold">{claim.caveats_count}</span>{" "}
          <span className="text-text-muted">caveat{claim.caveats_count === 1 ? "" : "s"} noted by the evaluator.</span>
        </p>
        {breakdown.market === "us_sec" ? (
          <EvaluationRecord ticker={breakdown.ticker} claimId={claim.claim_id} />
        ) : (
          <p className="mt-2 text-[12.5px] leading-relaxed text-text-muted">
            The GSE score breakdown reports the caveat count but not the caveat text or per-claim evaluator confidence.
          </p>
        )}
      </Section>
    </div>
  );
}

/** SEC only: fetch the stored evaluation for caveat text, confidence and provenance on demand. */
function EvaluationRecord({ ticker, claimId }: { ticker: string; claimId: string }) {
  const q = useApiMutation((signal) => api.secClaimEvaluation(ticker, claimId, { signal }));
  if (q.status === "success") return <EvaluationBody data={q.data} />;
  return (
    <div className="mt-3 space-y-3">
      {q.status === "error" ? <ErrorState error={q.error} compact /> : null}
      <Button variant="secondary" size="sm" onClick={() => q.run()} disabled={q.status === "loading"}>
        {q.status === "loading" ? <Spinner className="text-current" /> : <ScanSearch aria-hidden />}
        {q.status === "loading" ? "Loading evaluation…" : "Load caveat text & evaluator confidence"}
      </Button>
      <p className="text-[12px] text-text-subtle">From GET /companies/{"{ticker}"}/claims/{"{claim_id}"}/evaluation.</p>
    </div>
  );
}

function EvaluationBody({ data }: { data: SingleClaimEvaluationResponse }) {
  const ev = data.evaluation;
  return (
    <div className="mt-3 space-y-3">
      <dl className="grid grid-cols-2 gap-3 text-[12.5px] sm:grid-cols-3">
        <div>
          <dt className="text-text-subtle">Evaluator confidence</dt>
          <dd className="mt-0.5 font-medium text-text">{CONFIDENCE_LABEL[ev.confidence]}</dd>
        </div>
        <div>
          <dt className="text-text-subtle">Evaluation mode</dt>
          <dd className="mt-0.5 font-medium text-text">{ev.evaluation_mode === "llm" ? "LLM-assisted" : "Rule-based"}</dd>
        </div>
        <div>
          <dt className="text-text-subtle">Model</dt>
          <dd className="mt-0.5 font-mono text-text">{ev.model_name ?? "—"}</dd>
        </div>
        <div className="col-span-2 sm:col-span-3">
          <dt className="text-text-subtle">Evaluated</dt>
          <dd className="mt-0.5 text-text">{formatDateTime(ev.created_at)}</dd>
        </div>
      </dl>
      {ev.caveats.length > 0 ? (
        <ul className="space-y-1.5">
          {ev.caveats.map((c) => (
            <li key={c} className="flex gap-2 text-[13px] leading-relaxed text-text">
              <span aria-hidden className="mt-[8px] size-1 shrink-0 rounded-full bg-unsub" />
              {c}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-[12.5px] text-text-subtle italic">No caveats recorded.</p>
      )}
    </div>
  );
}
