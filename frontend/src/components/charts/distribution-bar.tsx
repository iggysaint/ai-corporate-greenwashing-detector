import type { AssessmentCategory } from "@/lib/api/types";
import { ASSESSMENT_LABEL, ASSESSMENT_ORDER } from "@/lib/format";
import { ASSESSMENT_STYLE } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

/**
 * Stacked bar of claim assessment counts. Insufficient-evidence claims are hatched to show they are
 * excluded from scoring rather than scored low. A table-like legend carries exact counts so colour is
 * never the only channel.
 */
export function DistributionBar({
  counts,
  className,
  showLegend = true,
}: {
  counts: Record<AssessmentCategory, number>;
  className?: string;
  showLegend?: boolean;
}) {
  const total = ASSESSMENT_ORDER.reduce((sum, k) => sum + (counts[k] ?? 0), 0);
  return (
    <div className={cn("min-w-0", className)}>
      {total === 0 ? (
        <div className="hatch h-3 rounded-full bg-insufficient-bg" aria-label="No assessed claims" role="img" />
      ) : (
        <div
          className="flex h-3 overflow-hidden rounded-full bg-black/[0.05]"
          role="img"
          aria-label={ASSESSMENT_ORDER.map((k) => `${ASSESSMENT_LABEL[k]}: ${counts[k] ?? 0}`).join(", ")}
        >
          {ASSESSMENT_ORDER.map((k) => {
            const n = counts[k] ?? 0;
            if (!n) return null;
            return (
              <div
                key={k}
                className={cn("h-full border-r-2 border-surface last:border-r-0", ASSESSMENT_STYLE[k].bar)}
                style={{ width: `${(n / total) * 100}%` }}
              />
            );
          })}
        </div>
      )}
      {showLegend ? (
        <ul className="mt-3 grid grid-cols-1 gap-x-6 gap-y-1.5 sm:grid-cols-2">
          {ASSESSMENT_ORDER.map((k) => {
            const n = counts[k] ?? 0;
            const Icon = ASSESSMENT_STYLE[k].icon;
            return (
              <li key={k} className="flex items-center justify-between gap-3 text-[13px]">
                <span className="flex min-w-0 items-center gap-2 text-text-muted">
                  <span aria-hidden className={cn("size-2.5 shrink-0 rounded-sm", ASSESSMENT_STYLE[k].bar)} />
                  <Icon aria-hidden className={cn("size-3.5 shrink-0", ASSESSMENT_STYLE[k].className, "bg-transparent")} />
                  <span className="truncate">{ASSESSMENT_LABEL[k]}</span>
                </span>
                <span className="tabular font-medium text-text">
                  {n}
                  {total > 0 ? (
                    <span className="ml-1.5 font-normal text-text-subtle">{Math.round((n / total) * 100)}%</span>
                  ) : null}
                </span>
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}
