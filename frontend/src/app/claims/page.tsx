import type { Metadata } from "next";
import { Suspense } from "react";
import { LoadingState } from "@/components/ui/states";
import { ClaimsView } from "./claims-view";

export const metadata: Metadata = { title: "Claims & Evidence" };

export default function ClaimsPage() {
  return (
    <Suspense fallback={<LoadingState label="Loading claims…" />}>
      <ClaimsView />
    </Suspense>
  );
}
