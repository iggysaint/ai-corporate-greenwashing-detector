"use client";

import { CompanyGate } from "@/components/company/company-gate";
import { SecProfile } from "@/components/company/sec-profile";
import { GseProfile } from "@/components/company/gse-profile";

export function CompanyView() {
  return (
    <CompanyGate purpose="view its profile">
      {({ market, ticker }) =>
        market === "us_sec" ? <SecProfile key={ticker} ticker={ticker} /> : <GseProfile key={ticker} ticker={ticker} />
      }
    </CompanyGate>
  );
}
