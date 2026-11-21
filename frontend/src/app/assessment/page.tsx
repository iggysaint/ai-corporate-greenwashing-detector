import type { Metadata } from "next";
import { Suspense } from "react";
import { LoadingState } from "@/components/ui/states";
import { AssessmentView } from "./assessment-view";

export const metadata: Metadata = { title: "ESG Integrity Assessment" };

export default function AssessmentPage() {
  return (
    <Suspense fallback={<LoadingState label="Loading assessment…" />}>
      <AssessmentView />
    </Suspense>
  );
}
