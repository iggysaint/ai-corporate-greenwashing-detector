import type { MarketId } from "./api/types";

export interface CompanyContext {
  market: MarketId;
  ticker: string;
}

/** Query-string carrier for the selected market and company, so context survives navigation and reloads. */
export function withContext(path: string, ctx: Partial<CompanyContext> | null, extra?: Record<string, string>) {
  const params = new URLSearchParams();
  if (ctx?.market) params.set("market", ctx.market);
  if (ctx?.ticker) params.set("ticker", ctx.ticker);
  if (extra) for (const [k, v] of Object.entries(extra)) if (v) params.set(k, v);
  const qs = params.toString();
  return qs ? `${path}?${qs}` : path;
}

export const routes = {
  overview: "/",
  explorer: "/explorer",
  company: "/company",
  assessment: "/assessment",
  claims: "/claims",
  history: "/history",
  methodology: "/methodology",
} as const;
