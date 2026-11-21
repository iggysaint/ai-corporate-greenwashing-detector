import { CircleDashed } from "lucide-react";
import type { DimensionalScore, PillarKey } from "@/lib/api/types";
import { formatPercent, formatScore, PILLAR_LABEL } from "@/lib/format";
import { ConfidenceBadge } from "@/components/ui/badge";
import { DistributionBar } from "@/components/charts/distribution-bar";
import { cn } from "@/lib/utils";

const ACCENT: Record<PillarKey, string> = {
  environmental: "bg-forest-600",
  social: "bg-ink-600",
  governance: "bg-[#6b5b2e]",
};

/**
 * One ESG pillar. A null score is rendered as "Insufficient Data" with a dashed frame — never as 0.
 */
export function PillarCard({
  pillar,
  dimension,
  fallbackScore,
}: {
  pillar: PillarKey;
  dimension: DimensionalScore | undefined;
  fallbackScore: number | null;
}) {
  const score = dimension ? dimension.score : fallbackScore;
  const display = formatScore(score);
  const missing = display === null;

  return (
    <section
      aria-labelledby={`pillar-${pillar}`}
      className={cn(
        "flex flex-col rounded-lg border bg-surface shadow-card",
        missing ? "border-dashed border-line-strong" : "border-line",
      )}
    >
      <div className="flex items-start justify-between gap-3 px-5 pt-4">
        <h3 id={`pillar-${pillar}`} className="flex items-center gap-2 text-[13px] font-semibold tracking-wide text-text uppercase">
          <span aria-hidden className={cn("size-2 rounded-full", ACCENT[pillar])} />
          {PILLAR_LABEL[pillar]}
        </h3>
        {dimension ? <ConfidenceBadge value={dimension.confidence} /> : null}
      </div>

      <div className="px-5 pt-3 pb-4">
        {missing ? (
          <div className="flex items-center gap-3">
            <CircleDashed aria-hidden className="size-7 text-text-subtle" />
            <div>
              <p className="text-[17px] font-semibold text-text-muted">Insufficient Data</p>
              <p className="text-[12px] text-text-subtle">Not scored — a data gap, not a zero.</p>
            </div>
          </div>
        ) : (
          <div>
            <p className="flex items-baseline gap-1.5">
              <span className="tabular font-serif text-[38px] leading-none font-semibold text-text">{display}</span>
              <span className="text-[13px] text-text-subtle">/ 100</span>
            </p>
            <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-black/[0.07]" aria-hidden>
              <div className={cn("h-full rounded-full", ACCENT[pillar])} style={{ width: `${score}%` }} />
            </div>
          </div>
        )}
      </div>

      {dimension ? (
        <div className="space-y-4 border-t border-line px-5 py-4">
          <dl className="grid grid-cols-3 gap-3 text-[12px]">
            <div>
              <dt className="text-text-subtle">Assessable</dt>
              <dd className="tabular mt-0.5 text-[14px] font-semibold text-text">
                {dimension.assessable_claims_count}
                <span className="font-normal text-text-subtle"> / {dimension.claims_count}</span>
              </dd>
            </div>
            <div>
              <dt className="text-text-subtle">Coverage</dt>
              <dd className="tabular mt-0.5 text-[14px] font-semibold text-text">{formatPercent(dimension.evidence_coverage)}</dd>
            </div>
            <div>
              <dt className="text-text-subtle" title="Normalised weight in the overall score">
                Weight used
              </dt>
              <dd className="tabular mt-0.5 text-[14px] font-semibold text-text">
                {Math.round(dimension.effective_weight * 100)}%
                <span className="font-normal text-text-subtle"> of {Math.round(dimension.weight * 100)}%</span>
              </dd>
            </div>
          </dl>
          <DistributionBar
            showLegend={false}
            counts={{
              supported: dimension.supported_count,
              partially_supported: dimension.partially_supported_count,
              unsubstantiated: dimension.unsubstantiated_count,
              inconsistent: dimension.inconsistent_count,
              insufficient_evidence: dimension.insufficient_evidence_count,
            }}
          />
          {dimension.key_factors.length > 0 ? (
            <ul className="space-y-1.5 text-[12.5px] leading-relaxed text-text-muted">
              {dimension.key_factors.map((f) => (
                <li key={f} className="flex gap-2">
                  <span aria-hidden className="mt-[7px] size-1 shrink-0 rounded-full bg-text-subtle" />
                  {f}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : (
        <p className="mt-auto border-t border-line px-5 py-4 text-[12.5px] text-text-subtle">
          Pillar detail not included in this response.
        </p>
      )}
    </section>
  );
}
