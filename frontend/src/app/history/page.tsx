import type { Metadata } from "next";
import { Suspense } from "react";
import { LoadingState } from "@/components/ui/states";
import { HistoryView } from "./history-view";

export const metadata: Metadata = { title: "Assessment History" };

export default function HistoryPage() {
  return (
    <Suspense fallback={<LoadingState label="Loading history…" />}>
      <HistoryView />
    </Suspense>
  );
}
