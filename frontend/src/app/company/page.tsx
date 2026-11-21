import type { Metadata } from "next";
import { Suspense } from "react";
import { LoadingState } from "@/components/ui/states";
import { CompanyView } from "./company-view";

export const metadata: Metadata = { title: "Company Profile" };

export default function CompanyPage() {
  return (
    <Suspense fallback={<LoadingState label="Loading company…" />}>
      <CompanyView />
    </Suspense>
  );
}
