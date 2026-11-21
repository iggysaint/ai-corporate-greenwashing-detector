"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { ArrowRight, Search } from "lucide-react";
import type { MarketId } from "@/lib/api/types";
import { MARKETS } from "@/lib/format";
import { routes, withContext } from "@/lib/routes";
import { validateTicker } from "@/lib/validation";
import { useWorkspace } from "@/components/providers/workspace-provider";
import { Button } from "@/components/ui/button";
import { FormField, Input, Segmented } from "@/components/ui/form";

const EXAMPLES: Record<MarketId, string[]> = {
  us_sec: ["AAPL", "MSFT", "GOOGL"],
  gh_gse: ["MTNGH", "GCB", "SCB"],
};

/**
 * Exact-ticker lookup. There is no autocomplete endpoint, so input is validated locally against the
 * backend's ticker rules and resolved on the company profile.
 */
export function TickerSearch({ showMarket = true, autoFocus }: { showMarket?: boolean; autoFocus?: boolean }) {
  const router = useRouter();
  const { market, setMarket } = useWorkspace();
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);

  function submit(raw: string) {
    const result = validateTicker(raw, market);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setError(null);
    router.push(withContext(routes.company, { market, ticker: result.value }));
  }

  return (
    <form
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        submit(value);
      }}
      className="space-y-3"
    >
      {showMarket ? (
        <Segmented<MarketId>
          label="Market"
          value={market}
          onChange={(m) => {
            setMarket(m);
            setError(null);
          }}
          options={[
            { value: "us_sec", label: "US · SEC EDGAR" },
            { value: "gh_gse", label: "Ghana · GSE" },
          ]}
        />
      ) : null}
      <FormField
        label={`${MARKETS[market].country} ticker symbol`}
        error={error}
        hint={market === "us_sec" ? "Exact ticker as listed with the SEC." : "Exact GSE ticker, or browse the directory."}
      >
        {({ id, describedBy, invalid }) => (
          <div className="flex gap-2">
            <div className="relative min-w-0 flex-1">
              <Search aria-hidden className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-text-subtle" />
              <Input
                id={id}
                aria-describedby={describedBy}
                aria-invalid={invalid}
                value={value}
                autoFocus={autoFocus}
                onChange={(e) => {
                  setValue(e.target.value.toUpperCase());
                  if (error) setError(null);
                }}
                placeholder={market === "us_sec" ? "e.g. AAPL" : "e.g. MTNGH"}
                autoComplete="off"
                autoCapitalize="characters"
                spellCheck={false}
                maxLength={12}
                className="pl-9 font-mono uppercase placeholder:font-sans placeholder:normal-case"
              />
            </div>
            <Button type="submit">
              Open
              <ArrowRight aria-hidden />
            </Button>
          </div>
        )}
      </FormField>
      <div className="flex flex-wrap items-center gap-1.5 text-[12.5px] text-text-muted">
        <span>Examples:</span>
        {EXAMPLES[market].map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => {
              setValue(t);
              submit(t);
            }}
            className="rounded border border-line bg-surface px-1.5 py-0.5 font-mono text-[12px] text-text hover:border-forest-200 hover:bg-forest-50"
          >
            {t}
          </button>
        ))}
      </div>
    </form>
  );
}
