import { formatScore } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * Overall 0–100 score as a ring. A null score renders an explicitly dashed, empty ring with
 * "Insufficient data" — never a zero.
 */
export function ScoreRing({
  score,
  size = 168,
  label = "ESG Integrity Score",
  className,
}: {
  score: number | null;
  size?: number;
  label?: string;
  className?: string;
}) {
  const stroke = 12;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const value = score === null ? null : Math.max(0, Math.min(100, score));
  const display = formatScore(value);
  const offset = value === null ? c : c * (1 - value / 100);

  return (
    <figure
      className={cn("relative inline-flex shrink-0 items-center justify-center", className)}
      style={{ width: size, height: size }}
    >
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="currentColor"
          strokeWidth={stroke}
          className="text-black/[0.07]"
          strokeDasharray={value === null ? "4 6" : undefined}
        />
        {value !== null ? (
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke="currentColor"
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={c}
            strokeDashoffset={offset}
            className="text-forest-600 transition-[stroke-dashoffset] duration-700"
          />
        ) : null}
      </svg>
      <figcaption className="absolute inset-0 flex flex-col items-center justify-center text-center">
        <span className="sr-only">{label}: </span>
        {display !== null ? (
          <>
            <span className="tabular font-serif text-[44px] leading-none font-semibold text-text">{display}</span>
            <span className="mt-1 text-[12px] text-text-subtle">out of 100</span>
          </>
        ) : (
          <>
            <span className="text-[15px] font-semibold text-text-muted">Insufficient</span>
            <span className="text-[15px] font-semibold text-text-muted">data</span>
            <span className="mt-1 text-[11px] text-text-subtle">no score computed</span>
          </>
        )}
      </figcaption>
    </figure>
  );
}
