import { formatPercent } from "@/lib/format";
import { cn } from "@/lib/utils";

/** Horizontal 0–100 meter with an explicit, hatched "not available" state for null values. */
export function Meter({
  label,
  value,
  description,
  tone = "forest",
  unavailableText = "Not available",
  className,
}: {
  label: string;
  value: number | null;
  description?: React.ReactNode;
  tone?: "forest" | "ink";
  unavailableText?: string;
  className?: string;
}) {
  const display = formatPercent(value);
  const pct = value === null ? 0 : Math.max(0, Math.min(100, value));
  return (
    <div className={cn("min-w-0", className)}>
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-[13px] font-medium text-text">{label}</span>
        <span className={cn("tabular text-[15px] font-semibold", display ? "text-text" : "text-[13px] font-medium text-text-subtle italic")}>
          {display ?? unavailableText}
        </span>
      </div>
      <div
        className={cn("mt-2 h-2 overflow-hidden rounded-full", value === null ? "hatch bg-insufficient-bg" : "bg-black/[0.07]")}
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={value ?? undefined}
        aria-valuetext={display ?? unavailableText}
      >
        {value !== null ? (
          <div
            className={cn("h-full rounded-full", tone === "forest" ? "bg-forest-600" : "bg-ink-700")}
            style={{ width: `${pct}%` }}
          />
        ) : null}
      </div>
      {description ? <p className="mt-1.5 text-[12.5px] leading-relaxed text-text-muted">{description}</p> : null}
    </div>
  );
}
