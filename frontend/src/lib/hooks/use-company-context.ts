"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect } from "react";
import type { MarketId } from "@/lib/api/types";
import { useWorkspace } from "@/components/providers/workspace-provider";
import { isMarketId, validateTicker } from "@/lib/validation";

export type CompanyContextResult =
  | { status: "pending" }
  | { status: "none" }
  | { status: "invalid"; error: string }
  | { status: "ready"; market: MarketId; ticker: string };

/**
 * Resolve the company a page is about from the URL (?market=&ticker=). When the URL has no company but
 * the workspace has an active one, the URL is updated to carry it, so every screen stays linkable.
 */
export function useCompanyContext(): CompanyContextResult {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const { activeCompany, hydrated } = useWorkspace();

  const rawMarket = params.get("market");
  const rawTicker = params.get("ticker");
  const hasUrlContext = Boolean(rawMarket || rawTicker);

  useEffect(() => {
    if (!hasUrlContext && hydrated && activeCompany) {
      const next = new URLSearchParams(params.toString());
      next.set("market", activeCompany.market);
      next.set("ticker", activeCompany.ticker);
      router.replace(`${pathname}?${next.toString()}`);
    }
  }, [hasUrlContext, hydrated, activeCompany, params, pathname, router]);

  if (!hasUrlContext) {
    if (!hydrated || activeCompany) return { status: "pending" };
    return { status: "none" };
  }
  if (!isMarketId(rawMarket)) return { status: "invalid", error: "The link does not specify a supported market." };
  const t = validateTicker(rawTicker ?? "", rawMarket);
  if (!t.ok) return { status: "invalid", error: t.error };
  return { status: "ready", market: rawMarket, ticker: t.value };
}
