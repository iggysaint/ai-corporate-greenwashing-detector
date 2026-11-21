"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { ChevronRight, Search } from "lucide-react";
import { api } from "@/lib/api/endpoints";
import type { GseCompany } from "@/lib/api/types";
import { useApiQuery } from "@/lib/hooks/use-api";
import { routes, withContext } from "@/lib/routes";
import { Input, Select } from "@/components/ui/form";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/states";

/** Directory of GSE-listed companies from GET /api/v1/gse/companies, with local filtering. */
export function GseDirectory({ limit, compact }: { limit?: number; compact?: boolean }) {
  const q = useApiQuery("gse-companies", (signal) => api.gseCompanies({ signal }));
  const [query, setQuery] = useState("");
  const [sector, setSector] = useState("");

  const companies = useMemo(() => q.data?.companies ?? [], [q.data]);
  const sectors = useMemo(
    () => Array.from(new Set(companies.map((c) => c.sector).filter((s): s is string => Boolean(s)))).sort(),
    [companies],
  );
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return companies
      .filter((c) => (sector ? c.sector === sector : true))
      .filter((c) =>
        needle ? c.ticker.toLowerCase().includes(needle) || c.company_name.toLowerCase().includes(needle) : true,
      )
      .sort((a, b) => a.ticker.localeCompare(b.ticker));
  }, [companies, query, sector]);

  if (q.status === "error") return <ErrorState error={q.error} onRetry={q.reload} />;
  if (q.status !== "success") {
    return (
      <div className="space-y-2" role="status" aria-label="Loading GSE companies">
        {Array.from({ length: compact ? 4 : 8 }).map((_, i) => (
          <Skeleton key={i} className="h-11 w-full" />
        ))}
      </div>
    );
  }

  const shown = limit ? filtered.slice(0, limit) : filtered;

  return (
    <div className="space-y-3">
      {!compact ? (
        <div className="flex flex-col gap-2 sm:flex-row">
          <div className="relative min-w-0 flex-1">
            <Search aria-hidden className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-text-subtle" />
            <Input
              aria-label="Filter GSE companies by ticker or name"
              placeholder="Filter by ticker or company name"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="pl-9"
            />
          </div>
          {sectors.length > 0 ? (
            <Select aria-label="Filter by sector" value={sector} onChange={(e) => setSector(e.target.value)} className="sm:w-56">
              <option value="">All sectors</option>
              {sectors.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </Select>
          ) : null}
        </div>
      ) : null}

      {!compact ? (
        <p className="text-[12.5px] text-text-muted" aria-live="polite">
          Showing <span className="tabular font-medium text-text">{shown.length}</span> of{" "}
          <span className="tabular">{q.data.total_count}</span> listed companies returned by the GSE listings API.
        </p>
      ) : null}

      {shown.length === 0 ? (
        <EmptyState title={companies.length === 0 ? "No companies returned" : "No matching companies"}>
          {companies.length === 0
            ? "The GSE listings source returned an empty list."
            : "Adjust the filter or sector to see more companies."}
        </EmptyState>
      ) : (
        <ul className="divide-y divide-line overflow-hidden rounded-lg border border-line bg-surface">
          {shown.map((c) => (
            <GseRow key={c.ticker} company={c} />
          ))}
        </ul>
      )}
    </div>
  );
}

function GseRow({ company }: { company: GseCompany }) {
  return (
    <li>
      <Link
        href={withContext(routes.company, { market: "gh_gse", ticker: company.ticker })}
        className="group flex items-center gap-4 px-4 py-3 transition-colors hover:bg-surface-muted focus-visible:bg-surface-muted"
      >
        <span className="w-20 shrink-0 font-mono text-[13px] font-medium text-text">{company.ticker}</span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[14px] font-medium text-text">{company.company_name}</span>
          <span className="block truncate text-[12.5px] text-text-muted">
            {[company.sector, company.industry].filter(Boolean).join(" · ") || "Sector not reported"}
          </span>
        </span>
        <ChevronRight aria-hidden className="size-4 shrink-0 text-text-subtle transition-transform group-hover:translate-x-0.5" />
      </Link>
    </li>
  );
}
