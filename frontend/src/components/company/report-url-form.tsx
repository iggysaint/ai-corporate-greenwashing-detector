"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Gauge } from "lucide-react";
import { routes, withContext } from "@/lib/routes";
import { validateReportingPeriod, validateReportUrl } from "@/lib/validation";
import { Button } from "@/components/ui/button";
import { FormField, Input } from "@/components/ui/form";

/**
 * Submit a public report URL for a GSE assessment. Validation here is for usability only; the backend
 * enforces SSRF protection, blocked file types and size limits, and its errors are shown verbatim.
 */
export function ReportUrlForm({ ticker, submitLabel = "Assess this report" }: { ticker: string; submitLabel?: string }) {
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [period, setPeriod] = useState("");
  const [urlError, setUrlError] = useState<string | null>(null);
  const [periodError, setPeriodError] = useState<string | null>(null);

  return (
    <form
      noValidate
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        const u = validateReportUrl(url);
        const p = validateReportingPeriod(period);
        setUrlError(u.ok ? null : u.error);
        setPeriodError(p.ok ? null : p.error);
        if (!u.ok || !p.ok) return;
        router.push(
          withContext(
            routes.assessment,
            { market: "gh_gse", ticker },
            { source_url: u.value, reporting_period: p.value, run: "1" },
          ),
        );
      }}
    >
      <FormField
        label="Public report URL"
        error={urlError}
        hint="Direct link to a publicly hosted HTML or PDF annual, integrated or sustainability report."
      >
        {({ id, describedBy, invalid }) => (
          <Input
            id={id}
            type="url"
            inputMode="url"
            aria-describedby={describedBy}
            aria-invalid={invalid}
            placeholder="https://www.example.com/annual-report-2024.pdf"
            value={url}
            onChange={(e) => {
              setUrl(e.target.value);
              if (urlError) setUrlError(null);
            }}
            autoComplete="off"
            spellCheck={false}
          />
        )}
      </FormField>
      <FormField label="Reporting period (optional)" error={periodError} hint="For example 2024 or FY2024, as stated in the report.">
        {({ id, describedBy, invalid }) => (
          <Input
            id={id}
            aria-describedby={describedBy}
            aria-invalid={invalid}
            placeholder="2024"
            value={period}
            maxLength={20}
            onChange={(e) => {
              setPeriod(e.target.value);
              if (periodError) setPeriodError(null);
            }}
            className="sm:max-w-48"
          />
        )}
      </FormField>
      <Button type="submit">
        <Gauge aria-hidden />
        {submitLabel}
      </Button>
    </form>
  );
}
