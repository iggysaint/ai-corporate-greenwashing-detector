import type { Metadata } from "next";
import { Suspense } from "react";
import { LoadingState } from "@/components/ui/states";
import { ExplorerView } from "./explorer-view";

export const metadata: Metadata = { title: "Company Explorer" };

export default function ExplorerPage() {
  return (
    <Suspense fallback={<LoadingState label="Loading explorer…" />}>
      <ExplorerView />
    </Suspense>
  );
}
