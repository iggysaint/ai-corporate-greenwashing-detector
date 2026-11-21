/**
 * Typed wrappers for the existing FastAPI routes. Paths mirror app/api/*.py (all mounted under /api/v1).
 * No endpoint here fabricates or substitutes data: each returns exactly what the backend sends.
 */

import { ANALYSIS_TIMEOUT_MS, request, seg } from "./client";
import type {
  EsgScoreBreakdown,
  EsgScoreHistory,
  GseCompanyDetailResponse,
  GseCompanyListResponse,
  HealthResponse,
  MarketId,
  SecCompany,
  SecDocumentMetadataResponse,
  SecFilingsResponse,
  SecLatestFilingResponse,
  SingleClaimEvaluationResponse,
} from "./types";

const V1 = "/api/v1";

type Opts = { signal?: AbortSignal };

/** Optional document selection for GSE scoring (documented query parameters). */
export interface GseSourceOptions {
  sourceUrl?: string | null;
  reportingPeriod?: string | null;
}

export const api = {
  health: (o: Opts = {}) => request<HealthResponse>("/health", { ...o, timeoutMs: 10_000 }),

  // ── US SEC ────────────────────────────────────────────────
  secCompany: (ticker: string, o: Opts = {}) =>
    request<SecCompany>(`${V1}/companies/${seg(ticker)}`, o),

  secFilings: (ticker: string, o: Opts = {}) =>
    request<SecFilingsResponse>(`${V1}/companies/${seg(ticker)}/filings`, o),

  secLatestFiling: (ticker: string, o: Opts = {}) =>
    request<SecLatestFilingResponse>(`${V1}/companies/${seg(ticker)}/filings/latest`, o),

  /** Downloads and parses the latest 10-K on the backend; can be slow on first call. */
  secDocumentMetadata: (ticker: string, o: Opts = {}) =>
    request<SecDocumentMetadataResponse>(`${V1}/companies/${seg(ticker)}/filings/latest/document`, {
      ...o,
      timeoutMs: ANALYSIS_TIMEOUT_MS,
    }),

  secScoreBreakdown: (ticker: string, o: Opts = {}) =>
    request<EsgScoreBreakdown>(`${V1}/companies/${seg(ticker)}/score/breakdown`, {
      ...o,
      timeoutMs: ANALYSIS_TIMEOUT_MS,
    }),

  secScoreHistory: (ticker: string, o: Opts = {}) =>
    request<EsgScoreHistory>(`${V1}/companies/${seg(ticker)}/score/history`, o),

  /** Per-claim evaluation (confidence, caveat text, evaluation mode). Served from the backend cache once scored. */
  secClaimEvaluation: (ticker: string, claimId: string, o: Opts = {}) =>
    request<SingleClaimEvaluationResponse>(
      `${V1}/companies/${seg(ticker)}/claims/${seg(claimId)}/evaluation`,
      { ...o, timeoutMs: ANALYSIS_TIMEOUT_MS },
    ),

  // ── Ghana GSE ─────────────────────────────────────────────
  gseCompanies: (o: Opts = {}) => request<GseCompanyListResponse>(`${V1}/gse/companies`, o),

  gseCompany: (ticker: string, o: Opts = {}) =>
    request<GseCompanyDetailResponse>(`${V1}/gse/companies/${seg(ticker)}`, o),

  gseScoreBreakdown: (ticker: string, source: GseSourceOptions = {}, o: Opts = {}) =>
    request<EsgScoreBreakdown>(`${V1}/gse/companies/${seg(ticker)}/score/breakdown`, {
      ...o,
      query: { source_url: source.sourceUrl, reporting_period: source.reportingPeriod },
      timeoutMs: ANALYSIS_TIMEOUT_MS,
    }),

  gseScoreHistory: (ticker: string, o: Opts = {}) =>
    request<EsgScoreHistory>(`${V1}/gse/companies/${seg(ticker)}/score/history`, o),
};

/** Market-agnostic helpers used by shared screens. */
export function fetchScoreBreakdown(
  market: MarketId,
  ticker: string,
  source: GseSourceOptions = {},
  o: Opts = {},
): Promise<EsgScoreBreakdown> {
  return market === "gh_gse" ? api.gseScoreBreakdown(ticker, source, o) : api.secScoreBreakdown(ticker, o);
}

export function fetchScoreHistory(market: MarketId, ticker: string, o: Opts = {}): Promise<EsgScoreHistory> {
  return market === "gh_gse" ? api.gseScoreHistory(ticker, o) : api.secScoreHistory(ticker, o);
}
