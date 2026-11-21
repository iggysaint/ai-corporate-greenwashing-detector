import { CircleCheck, CircleDashed, CircleHelp, CircleMinus, CircleX } from "lucide-react";
import type { AssessmentCategory, ConfidenceLevel } from "@/lib/api/types";
import { ASSESSMENT_LABEL, CONFIDENCE_LABEL } from "@/lib/format";
import { cn } from "@/lib/utils";

type Tone = "neutral" | "forest" | "warn" | "danger" | "info" | "ink";

const tones: Record<Tone, string> = {
  neutral: "bg-insufficient-bg text-insufficient border-transparent",
  forest: "bg-forest-50 text-forest-700 border-forest-100",
  warn: "bg-warn-bg text-warn border-transparent",
  danger: "bg-danger-bg text-danger border-transparent",
  info: "bg-info-bg text-info border-transparent",
  ink: "bg-ink-900 text-white border-transparent",
};

export function Badge({
  tone = "neutral",
  className,
  children,
}: {
  tone?: Tone;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[12px] leading-5 font-medium whitespace-nowrap",
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export const ASSESSMENT_STYLE: Record<
  AssessmentCategory,
  { className: string; bar: string; icon: typeof CircleCheck }
> = {
  supported: { className: "bg-supported-bg text-supported", bar: "bg-supported", icon: CircleCheck },
  partially_supported: { className: "bg-partial-bg text-partial", bar: "bg-partial", icon: CircleMinus },
  unsubstantiated: { className: "bg-unsub-bg text-unsub", bar: "bg-unsub", icon: CircleHelp },
  inconsistent: { className: "bg-inconsistent-bg text-inconsistent", bar: "bg-inconsistent", icon: CircleX },
  insufficient_evidence: {
    className: "bg-insufficient-bg text-insufficient",
    bar: "bg-insufficient-bg hatch",
    icon: CircleDashed,
  },
};

export function AssessmentBadge({ value, className }: { value: AssessmentCategory; className?: string }) {
  const style = ASSESSMENT_STYLE[value];
  const Icon = style.icon;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[12px] leading-5 font-medium whitespace-nowrap",
        style.className,
        className,
      )}
    >
      <Icon aria-hidden className="size-3.5" />
      {ASSESSMENT_LABEL[value]}
    </span>
  );
}

const confidenceTone: Record<ConfidenceLevel, Tone> = {
  high: "forest",
  medium: "info",
  low: "warn",
  insufficient: "neutral",
};

export function ConfidenceBadge({ value }: { value: ConfidenceLevel }) {
  return (
    <Badge tone={confidenceTone[value]}>
      <span className="sr-only">Confidence: </span>
      {CONFIDENCE_LABEL[value]} confidence
    </Badge>
  );
}
