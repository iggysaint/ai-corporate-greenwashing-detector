"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { ArrowDown, ArrowUp, ChevronRight, FileWarning, Search } from "lucide-react";
import type { AssessmentCategory, ClaimScoreDetail, EsgScoreBreakdown } from "@/lib/api/types";
import {
  ASSESSMENT_LABEL,
  ASSESSMENT_ORDER,
  claimTypeLabel,
  confidenceAdjustment,
  formatScore,
  formatSigned,
  formatWeight,
  pillarLabel,
} from "@/lib/format";
import { AssessmentBadge, Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/form";
import { Sheet } from "@/components/ui/sheet";
import { EmptyState } from "@/components/ui/states";
import { cn } from "@/lib/utils";
import { ClaimDetail } from "./claim-detail";

type SortKey = "claim_score" | "materiality_weight" | "evidence_quality_adjustment" | "assessment";

function ConfidenceSignal({ reasons }: { reasons: string[] }) {
  const c = confidenceAdjustment(reasons);
  if (c === "high") return <span className="text-supported">High (+3)</span>;
  if (c === "low") return <span className="text-unsub">Low (−3)</span>;
  return <span className="text-text-subtle">No adj.</span>;
}

function EvidenceCell({ claim }: { claim: ClaimScoreDetail }) {
  const n = claim.referenced_evidence.length;
  return n > 0 ? (
    <span className="tabular text-text">
      {n} <span className="text-text-subtle">quote{n === 1 ? "" : "s"}</span>
    </span>
  ) : (
    <span className="text-text-subtle">None</span>
  );
}

function ScoreCell({ claim }: { claim: ClaimScoreDetail }) {
  if (claim.assessment === "insufficient_evidence") return <span className="text-text-subtle italic">Excluded</span>;
  return <span className="tabular font-semibold text-text">{formatScore(claim.claim_score)}</span>;
}

function SortHeader({
  k,
  sort,
  onToggle,
  children,
  className,
}: {
  k: SortKey;
  sort: { key: SortKey; dir: "asc" | "desc" };
  onToggle: (k: SortKey) => void;
  children: React.ReactNode;
  className?: string;
}) {
  const active = sort.key === k;
  return (
    <th scope="col" aria-sort={active ? (sort.dir === "asc" ? "ascending" : "descending") : "none"} className={className}>
      <button
        type="button"
        onClick={() => onToggle(k)}
        className={cn("inline-flex items-center gap-1 font-medium uppercase hover:text-text", active && "text-text")}
      >
        {children}
        {active ? (
          sort.dir === "asc" ? <ArrowUp aria-hidden className="size-3" /> : <ArrowDown aria-hidden className="size-3" />
        ) : null}
      </button>
    </th>
  );
}

export function ClaimsExplorer({ data }: { data: EsgScoreBreakdown }) {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const selectedId = params.get("claim");

  const [pillar, setPillar] = useState("");
  const [assessment, setAssessment] = useState<"" | AssessmentCategory>("");
  const [claimType, setClaimType] = useState("");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<{ key: SortKey; dir: "asc" | "desc" }>({ key: "materiality_weight", dir: "desc" });

  const claims = data.claim_scores;
  const types = useMemo(() => Array.from(new Set(claims.map((c) => c.claim_type))).sort(), [claims]);
  const groups = useMemo(() => Array.from(new Set(claims.map((c) => c.category_group))).sort(), [claims]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const rows = claims.filter(
      (c) =>
        (!pillar || c.category_group === pillar) &&
        (!assessment || c.assessment === assessment) &&
        (!claimType || c.claim_type === claimType) &&
        (!needle || c.claim_text.toLowerCase().includes(needle) || c.category.toLowerCase().includes(needle)),
    );
    const dir = sort.dir === "asc" ? 1 : -1;
    return [...rows].sort((a, b) => {
      if (sort.key === "assessment") {
        return (ASSESSMENT_ORDER.indexOf(a.assessment) - ASSESSMENT_ORDER.indexOf(b.assessment)) * dir;
      }
      // Excluded (insufficient evidence) claims always sort last for numeric score.
      if (sort.key === "claim_score") {
        const ax = a.assessment === "insufficient_evidence";
        const bx = b.assessment === "insufficient_evidence";
        if (ax !== bx) return ax ? 1 : -1;
      }
      return (a[sort.key] - b[sort.key]) * dir || a.claim_id.localeCompare(b.claim_id);
    });
  }, [claims, pillar, assessment, claimType, query, sort]);

  const selected = selectedId ? (claims.find((c) => c.claim_id === selectedId) ?? null) : null;

  function openClaim(id: string | null) {
    const next = new URLSearchParams(params.toString());
    if (id) next.set("claim", id);
    else next.delete("claim");
    router.replace(`${pathname}?${next.toString()}`, { scroll: false });
  }

  function toggleSort(key: SortKey) {
    setSort((s) => (s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: "desc" }));
  }

  const filtersActive = Boolean(pillar || assessment || claimType || query);

  return (
    <div className="space-y-4">
      <div className="grid gap-2 rounded-lg border border-line bg-surface p-3 shadow-card sm:grid-cols-2 lg:grid-cols-[minmax(0,1.6fr)_repeat(3,minmax(0,1fr))]">
        <div className="relative sm:col-span-2 lg:col-span-1">
          <Search aria-hidden className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-text-subtle" />
          <Input
            aria-label="Search claim text or category"
            placeholder="Search claim text or category"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="pl-9"
          />
        </div>
        <Select aria-label="Filter by ESG pillar" value={pillar} onChange={(e) => setPillar(e.target.value)}>
          <option value="">All pillars</option>
          {groups.map((g) => (
            <option key={g} value={g}>
              {pillarLabel(g)}
            </option>
          ))}
        </Select>
        <Select
          aria-label="Filter by assessment"
          value={assessment}
          onChange={(e) => setAssessment(e.target.value as "" | AssessmentCategory)}
        >
          <option value="">All assessments</option>
          {ASSESSMENT_ORDER.map((a) => (
            <option key={a} value={a}>
              {ASSESSMENT_LABEL[a]}
            </option>
          ))}
        </Select>
        <Select aria-label="Filter by claim type" value={claimType} onChange={(e) => setClaimType(e.target.value)}>
          <option value="">All claim types</option>
          {types.map((t) => (
            <option key={t} value={t}>
              {claimTypeLabel(t)}
            </option>
          ))}
        </Select>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 text-[12.5px] text-text-muted">
        <p aria-live="polite">
          <span className="tabular font-medium text-text">{filtered.length}</span> of{" "}
          <span className="tabular">{claims.length}</span> scored claims
        </p>
        {filtersActive ? (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setPillar("");
              setAssessment("");
              setClaimType("");
              setQuery("");
            }}
          >
            Clear filters
          </Button>
        ) : null}
      </div>

      {claims.length === 0 ? (
        <EmptyState icon={FileWarning} title="No claims in this assessment">
          The backend returned no scored claims for this document.
        </EmptyState>
      ) : filtered.length === 0 ? (
        <EmptyState title="No claims match these filters">Adjust or clear the filters to see more claims.</EmptyState>
      ) : (
        <>
          {/* Desktop table */}
          <div className="hidden overflow-hidden rounded-lg border border-line bg-surface shadow-card lg:block">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-[13px]">
                <caption className="sr-only">Scored sustainability claims</caption>
                <thead className="border-b border-line bg-surface-muted text-[11px] tracking-wider text-text-subtle">
                  <tr>
                    <th scope="col" className="w-[38%] px-4 py-2.5 font-medium uppercase">Claim</th>
                    <th scope="col" className="px-3 py-2.5 font-medium uppercase">Pillar</th>
                    <th scope="col" className="px-3 py-2.5 font-medium uppercase">Type</th>
                    <SortHeader sort={sort} onToggle={toggleSort} k="assessment" className="px-3 py-2.5">Assessment</SortHeader>
                    <SortHeader sort={sort} onToggle={toggleSort} k="claim_score" className="px-3 py-2.5 text-right">Score</SortHeader>
                    <SortHeader sort={sort} onToggle={toggleSort} k="materiality_weight" className="px-3 py-2.5 text-right">Weight</SortHeader>
                    <SortHeader sort={sort} onToggle={toggleSort} k="evidence_quality_adjustment" className="px-3 py-2.5 text-right">Quality adj.</SortHeader>
                    <th scope="col" className="px-3 py-2.5 font-medium uppercase" title="Confidence adjustment applied by the scoring engine (derived from quality-adjustment reasons)">
                      Confidence
                    </th>
                    <th scope="col" className="px-3 py-2.5 font-medium uppercase">Evidence</th>
                    <th scope="col" className="w-8 px-2 py-2.5"><span className="sr-only">Open</span></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {filtered.map((c) => (
                    <tr
                      key={c.claim_id}
                      className={cn("cursor-pointer transition-colors hover:bg-surface-muted", selectedId === c.claim_id && "bg-forest-50/60")}
                      onClick={() => openClaim(c.claim_id)}
                    >
                      <td className="px-4 py-3">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            openClaim(c.claim_id);
                          }}
                          className="line-clamp-2 text-left leading-snug text-text hover:underline"
                        >
                          {c.claim_text}
                        </button>
                      </td>
                      <td className="px-3 py-3 whitespace-nowrap text-text-muted">{pillarLabel(c.category_group)}</td>
                      <td className="px-3 py-3 whitespace-nowrap text-text-muted">{claimTypeLabel(c.claim_type)}</td>
                      <td className="px-3 py-3"><AssessmentBadge value={c.assessment} /></td>
                      <td className="px-3 py-3 text-right"><ScoreCell claim={c} /></td>
                      <td className="tabular px-3 py-3 text-right font-mono text-[12.5px] text-text">
                        {formatWeight(c.materiality_weight)}
                        {!c.included_in_score ? <span className="block text-[11px] text-text-subtle">not counted</span> : null}
                      </td>
                      <td className="tabular px-3 py-3 text-right font-mono text-[12.5px] text-text">
                        {c.assessment === "insufficient_evidence" || c.assessment === "inconsistent"
                          ? <span className="text-text-subtle">n/a</span>
                          : formatSigned(c.evidence_quality_adjustment)}
                      </td>
                      <td className="px-3 py-3 text-[12.5px] whitespace-nowrap"><ConfidenceSignal reasons={c.quality_adjustment_reasons} /></td>
                      <td className="px-3 py-3 text-[12.5px] whitespace-nowrap"><EvidenceCell claim={c} /></td>
                      <td className="px-2 py-3"><ChevronRight aria-hidden className="size-4 text-text-subtle" /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Mobile / tablet cards */}
          <ul className="space-y-2 lg:hidden">
            {filtered.map((c) => (
              <li key={c.claim_id}>
                <button
                  type="button"
                  onClick={() => openClaim(c.claim_id)}
                  className="w-full rounded-lg border border-line bg-surface p-4 text-left shadow-card transition-colors hover:border-forest-200"
                >
                  <div className="flex flex-wrap items-center gap-1.5">
                    <AssessmentBadge value={c.assessment} />
                    <Badge tone="info">{pillarLabel(c.category_group)}</Badge>
                    <Badge>{claimTypeLabel(c.claim_type)}</Badge>
                  </div>
                  <p className="mt-2.5 line-clamp-3 text-[13.5px] leading-relaxed text-text">{c.claim_text}</p>
                  <dl className="mt-3 grid grid-cols-4 gap-2 text-[12px]">
                    <div>
                      <dt className="text-text-subtle">Score</dt>
                      <dd className="mt-0.5"><ScoreCell claim={c} /></dd>
                    </div>
                    <div>
                      <dt className="text-text-subtle">Weight</dt>
                      <dd className="tabular mt-0.5 font-mono text-text">{formatWeight(c.materiality_weight)}</dd>
                    </div>
                    <div>
                      <dt className="text-text-subtle">Confidence</dt>
                      <dd className="mt-0.5"><ConfidenceSignal reasons={c.quality_adjustment_reasons} /></dd>
                    </div>
                    <div>
                      <dt className="text-text-subtle">Evidence</dt>
                      <dd className="mt-0.5"><EvidenceCell claim={c} /></dd>
                    </div>
                  </dl>
                </button>
              </li>
            ))}
          </ul>
        </>
      )}

      <p className="text-[12px] leading-relaxed text-text-subtle">
        Confidence shows the adjustment the scoring engine applied for evaluator confidence (+3 high, −3 low, none for
        medium). The score breakdown does not include per-claim confidence directly; for SEC claims the full evaluation
        record can be loaded from the claim panel.
      </p>

      <Sheet
        open={Boolean(selected)}
        onOpenChange={(open) => !open && openClaim(null)}
        title={selected ? `${pillarLabel(selected.category_group)} · ${claimTypeLabel(selected.claim_type)} claim` : "Claim"}
        description={selected ? ASSESSMENT_LABEL[selected.assessment] : undefined}
      >
        {selected ? <ClaimDetail claim={selected} breakdown={data} /> : null}
      </Sheet>
    </div>
  );
}
