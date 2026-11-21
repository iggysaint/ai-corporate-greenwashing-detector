"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { fetchScoreBreakdown, type GseSourceOptions } from "@/lib/api/endpoints";
import { isApiError } from "@/lib/api/client";
import type { EsgScoreBreakdown, MarketId } from "@/lib/api/types";
import { isMarketId } from "@/lib/validation";

/**
 * Client-side workspace state: the selected market, the active company and the assessment results the
 * user has run in this browser tab. Results are kept in sessionStorage only (cleared when the tab closes),
 * which mirrors the backend's own in-memory history. Nothing here is a source of truth for scores: every
 * stored breakdown is an unmodified backend response.
 */

export interface ActiveCompany {
  market: MarketId;
  ticker: string;
  name: string;
}

export interface StoredAssessment {
  breakdown: EsgScoreBreakdown;
  /** GSE document parameters the assessment was requested with (empty for SEC / auto-selected). */
  sourceUrl: string | null;
  reportingPeriod: string | null;
  receivedAt: string;
}

/**
 * An assessment request in flight or failed. Runs live in this root provider (not in a page) so they
 * continue when the user navigates elsewhere; Next.js hides inactive pages and runs their effect cleanups.
 */
export type AssessmentRun =
  | { status: "running"; startedAt: number; sourceUrl: string | null; reportingPeriod: string | null }
  | { status: "error"; error: unknown; sourceUrl: string | null; reportingPeriod: string | null };

interface WorkspaceState {
  market: MarketId;
  setMarket: (m: MarketId) => void;
  activeCompany: ActiveCompany | null;
  setActiveCompany: (c: ActiveCompany | null) => void;
  assessments: Record<string, StoredAssessment>;
  saveAssessment: (market: MarketId, ticker: string, a: StoredAssessment) => void;
  getAssessment: (market: MarketId, ticker: string) => StoredAssessment | null;
  runs: Record<string, AssessmentRun>;
  startAssessment: (market: MarketId, ticker: string, source?: GseSourceOptions) => void;
  cancelAssessment: (market: MarketId, ticker: string) => void;
  hydrated: boolean;
}

const WorkspaceContext = createContext<WorkspaceState | null>(null);

const KEY = "esg-integrity.workspace.v1";

export function assessmentKey(market: MarketId, ticker: string) {
  return `${market}:${ticker.toUpperCase()}`;
}

interface Persisted {
  market?: string;
  activeCompany?: ActiveCompany | null;
  assessments?: Record<string, StoredAssessment>;
}

function load(): Persisted | null {
  try {
    const raw = window.sessionStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as Persisted) : null;
  } catch {
    return null;
  }
}

function persist(value: Persisted) {
  try {
    window.sessionStorage.setItem(KEY, JSON.stringify(value));
  } catch {
    // Storage full or unavailable: keep assessments for older companies out and retry with current only.
    try {
      window.sessionStorage.setItem(KEY, JSON.stringify({ market: value.market, activeCompany: value.activeCompany }));
    } catch {
      /* storage unavailable (private mode); state remains in memory for this page view */
    }
  }
}

export function WorkspaceProvider({ children }: { children: React.ReactNode }) {
  const [market, setMarketState] = useState<MarketId>("us_sec");
  const [activeCompany, setActiveCompanyState] = useState<ActiveCompany | null>(null);
  const [assessments, setAssessments] = useState<Record<string, StoredAssessment>>({});
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    const saved = load();
    /* eslint-disable react-hooks/set-state-in-effect -- one-time hydration from sessionStorage after mount */
    if (saved) {
      if (isMarketId(saved.market)) setMarketState(saved.market);
      if (saved.activeCompany && isMarketId(saved.activeCompany.market)) setActiveCompanyState(saved.activeCompany);
      if (saved.assessments && typeof saved.assessments === "object") setAssessments(saved.assessments);
    }
    setHydrated(true);
    /* eslint-enable react-hooks/set-state-in-effect */
  }, []);

  useEffect(() => {
    if (hydrated) persist({ market, activeCompany, assessments });
  }, [hydrated, market, activeCompany, assessments]);

  const setMarket = useCallback((m: MarketId) => setMarketState(m), []);
  const setActiveCompany = useCallback((c: ActiveCompany | null) => {
    setActiveCompanyState((prev) =>
      prev && c && prev.market === c.market && prev.ticker === c.ticker && prev.name === c.name ? prev : c,
    );
    if (c) setMarketState(c.market);
  }, []);
  const saveAssessment = useCallback((m: MarketId, ticker: string, a: StoredAssessment) => {
    setAssessments((prev) => ({ ...prev, [assessmentKey(m, ticker)]: a }));
  }, []);
  const getAssessment = useCallback(
    (m: MarketId, ticker: string) => assessments[assessmentKey(m, ticker)] ?? null,
    [assessments],
  );

  const [runs, setRuns] = useState<Record<string, AssessmentRun>>({});
  const controllers = useRef(new Map<string, AbortController>());

  const startAssessment = useCallback(
    (m: MarketId, ticker: string, source: GseSourceOptions = {}) => {
      const key = assessmentKey(m, ticker);
      if (controllers.current.has(key)) return; // already running
      const controller = new AbortController();
      controllers.current.set(key, controller);
      const sourceUrl = m === "gh_gse" ? (source.sourceUrl ?? null) : null;
      const reportingPeriod = m === "gh_gse" ? (source.reportingPeriod ?? null) : null;
      setRuns((prev) => ({ ...prev, [key]: { status: "running", startedAt: Date.now(), sourceUrl, reportingPeriod } }));

      fetchScoreBreakdown(m, ticker, { sourceUrl, reportingPeriod }, { signal: controller.signal }).then(
        (breakdown) => {
          controllers.current.delete(key);
          saveAssessment(m, ticker, { breakdown, sourceUrl, reportingPeriod, receivedAt: new Date().toISOString() });
          setActiveCompanyState({ market: m, ticker: breakdown.ticker, name: breakdown.company_name });
          setRuns((prev) => {
            const next = { ...prev };
            delete next[key];
            return next;
          });
        },
        (error: unknown) => {
          controllers.current.delete(key);
          setRuns((prev) => {
            const next = { ...prev };
            if (isApiError(error) && error.kind === "aborted") delete next[key];
            else next[key] = { status: "error", error, sourceUrl, reportingPeriod };
            return next;
          });
        },
      );
    },
    [saveAssessment],
  );

  const cancelAssessment = useCallback((m: MarketId, ticker: string) => {
    controllers.current.get(assessmentKey(m, ticker))?.abort();
  }, []);

  const value = useMemo(
    () => ({
      market,
      setMarket,
      activeCompany,
      setActiveCompany,
      assessments,
      saveAssessment,
      getAssessment,
      runs,
      startAssessment,
      cancelAssessment,
      hydrated,
    }),
    [market, setMarket, activeCompany, setActiveCompany, assessments, saveAssessment, getAssessment, runs, startAssessment, cancelAssessment, hydrated],
  );

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspace(): WorkspaceState {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) throw new Error("useWorkspace must be used within WorkspaceProvider");
  return ctx;
}
