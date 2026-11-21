import type {
  AssessmentCategory,
  ConfidenceLevel,
  DocumentSourceType,
  MarketId,
  PillarKey,
} from "./api/types";

export const MARKETS: Record<MarketId, { label: string; short: string; source: string; country: string }> = {
  us_sec: { label: "United States — SEC EDGAR", short: "US · SEC", source: "SEC EDGAR", country: "United States" },
  gh_gse: { label: "Ghana — Ghana Stock Exchange", short: "GH · GSE", source: "Ghana Stock Exchange", country: "Ghana" },
};

export const PILLARS: PillarKey[] = ["environmental", "social", "governance"];

export const PILLAR_LABEL: Record<string, string> = {
  environmental: "Environmental",
  social: "Social",
  governance: "Governance",
};

export function pillarLabel(group: string): string {
  return PILLAR_LABEL[group] ?? "Unmapped";
}

export const ASSESSMENT_ORDER: AssessmentCategory[] = [
  "supported",
  "partially_supported",
  "unsubstantiated",
  "inconsistent",
  "insufficient_evidence",
];

export const ASSESSMENT_LABEL: Record<AssessmentCategory, string> = {
  supported: "Supported",
  partially_supported: "Partially Supported",
  unsubstantiated: "Unsubstantiated",
  inconsistent: "Inconsistent",
  insufficient_evidence: "Insufficient Evidence",
};

/** Short definitions taken from app/models/evaluation.py::AssessmentCategory docstrings. */
export const ASSESSMENT_DESCRIPTION: Record<AssessmentCategory, string> = {
  supported: "Directly corroborated by affirmative disclosure evidence.",
  partially_supported: "Partly corroborated; evidence highlights material caveats, limitations, or partial scope.",
  unsubstantiated: "Relevant context exists but does not substantiate the assertion. Not a finding that the claim is false.",
  inconsistent: "Disclosed metrics, dates, or facts contradict the claim.",
  insufficient_evidence: "No relevant evidence passages were retrieved. Excluded from the score.",
};

export const CONFIDENCE_LABEL: Record<ConfidenceLevel, string> = {
  high: "High",
  medium: "Medium",
  low: "Low",
  insufficient: "Insufficient",
};

export const SOURCE_TYPE_LABEL: Record<DocumentSourceType, string> = {
  sec_10k: "SEC 10-K",
  annual_report: "Annual report",
  sustainability_report: "Sustainability report",
  integrated_report: "Integrated report",
  investor_presentation: "Investor presentation",
  unknown: "Document",
};

export const CLAIM_TYPE_LABEL: Record<string, string> = {
  achievement: "Achievement",
  target: "Target",
  current_state: "Current state",
  policy: "Policy",
  general: "General",
};

export function claimTypeLabel(t: string): string {
  return CLAIM_TYPE_LABEL[t] ?? humanize(t);
}

export function humanize(value: string): string {
  if (!value) return "";
  const s = value.replace(/[_-]+/g, " ").trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/** Format a 0–100 score. Null stays null so callers must render an explicit "no data" state. */
export function formatScore(value: number | null | undefined): string | null {
  if (value === null || value === undefined || Number.isNaN(value)) return null;
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

export function formatPercent(value: number | null | undefined): string | null {
  const s = formatScore(value);
  return s === null ? null : `${s}%`;
}

export function formatSigned(value: number): string {
  if (value === 0) return "0";
  const abs = Number.isInteger(value) ? Math.abs(value).toString() : Math.abs(value).toFixed(1);
  return value > 0 ? `+${abs}` : `−${abs}`;
}

export function formatWeight(value: number): string {
  return Number.isInteger(value) ? value.toFixed(1) : String(Number(value.toFixed(3)));
}

export function formatDateTime(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat("en-GB", {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(d);
}

export function formatDate(value: string | null | undefined): string | null {
  if (!value) return null;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return new Intl.DateTimeFormat("en-GB", { year: "numeric", month: "short", day: "2-digit", timeZone: "UTC" }).format(d);
}

export function formatNumber(value: number | null | undefined): string | null {
  if (value === null || value === undefined) return null;
  return new Intl.NumberFormat("en-US").format(value);
}

export function formatElapsed(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

/**
 * The breakdown does not return per-claim confidence directly. The only backend signal is the
 * quality-adjustment reason ("+3: high evaluation confidence" / "-3: low evaluation confidence").
 * Returns the adjustment that was applied, or null when none was recorded.
 */
export function confidenceAdjustment(reasons: string[]): "high" | "low" | null {
  for (const r of reasons) {
    const lower = r.toLowerCase();
    if (lower.includes("high evaluation confidence")) return "high";
    if (lower.includes("low evaluation confidence")) return "low";
  }
  return null;
}
