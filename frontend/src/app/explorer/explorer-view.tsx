"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useRef } from "react";
import { Info } from "lucide-react";
import { useWorkspace } from "@/components/providers/workspace-provider";
import { GseDirectory } from "@/components/company/gse-directory";
import { TickerSearch } from "@/components/company/ticker-search";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { Notice } from "@/components/ui/states";
import { MARKETS } from "@/lib/format";
import { isMarketId } from "@/lib/validation";

export function ExplorerView() {
  const params = useSearchParams();
  const { market, setMarket, hydrated } = useWorkspace();
  const applied = useRef(false);

  // A ?market= deep link selects the market once the workspace has hydrated.
  useEffect(() => {
    if (!hydrated || applied.current) return;
    applied.current = true;
    const m = params.get("market");
    if (isMarketId(m)) setMarket(m);
  }, [hydrated, params, setMarket]);

  return (
    <div>
      <PageHeader
        eyebrow={<span>{MARKETS[market].label}</span>}
        title="Company Explorer"
        description={
          market === "us_sec"
            ? "Identify a US-listed company through SEC EDGAR by its exact ticker symbol. The profile shows verified SEC metadata and the latest annual filing."
            : "Browse companies listed on the Ghana Stock Exchange. Each profile shows available corporate documents and accepts a public report URL where none is on file."
        }
      />

      {market === "us_sec" ? (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]">
          <Card>
            <CardHeader title="Look up a US company" description="Uses GET /api/v1/companies/{ticker} against SEC EDGAR." />
            <CardBody>
              <TickerSearch showMarket={false} autoFocus />
            </CardBody>
          </Card>
          <Notice title="Exact tickers only">
            The SEC integration resolves exact ticker symbols; there is no name search or autocomplete. Class shares use
            the SEC form, e.g. <span className="font-mono">BRK-B</span>.
          </Notice>
        </div>
      ) : (
        <div className="space-y-4">
          <Card>
            <CardHeader
              title="Ghana Stock Exchange listings"
              description="Select a company to view its profile and available reports."
            />
            <CardBody>
              <GseDirectory />
            </CardBody>
          </Card>
          <p className="flex items-start gap-2 text-[12.5px] leading-relaxed text-text-muted">
            <Info aria-hidden className="mt-0.5 size-3.5 shrink-0" />
            GSE has no centralised filing repository comparable to EDGAR. Verified public reports exist only for some
            issuers; for others you can submit a public annual or sustainability report URL on the company profile.
          </p>
        </div>
      )}
    </div>
  );
}
