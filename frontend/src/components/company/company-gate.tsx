"use client";

import { Building2 } from "lucide-react";
import type { MarketId } from "@/lib/api/types";
import { useCompanyContext } from "@/lib/hooks/use-company-context";
import { routes } from "@/lib/routes";
import { ButtonLink } from "@/components/ui/button";
import { EmptyState, LoadingState, Notice } from "@/components/ui/states";

/** Renders children only when the URL identifies a valid market + ticker; otherwise an honest empty state. */
export function CompanyGate({
  children,
  purpose,
}: {
  children: (ctx: { market: MarketId; ticker: string }) => React.ReactNode;
  purpose: string;
}) {
  const ctx = useCompanyContext();
  if (ctx.status === "pending") return <LoadingState label="Restoring workspace…" />;
  if (ctx.status === "invalid") {
    return (
      <div className="space-y-4">
        <Notice tone="warn" title="Invalid company link">
          {ctx.error}
        </Notice>
        <ButtonLink href={routes.explorer} variant="secondary">
          Open Company Explorer
        </ButtonLink>
      </div>
    );
  }
  if (ctx.status === "none") {
    return (
      <EmptyState
        icon={Building2}
        title="No company selected"
        action={<ButtonLink href={routes.explorer}>Find a company</ButtonLink>}
      >
        Select a US SEC or Ghana Stock Exchange company in the Company Explorer to {purpose}.
      </EmptyState>
    );
  }
  return <>{children({ market: ctx.market, ticker: ctx.ticker })}</>;
}
