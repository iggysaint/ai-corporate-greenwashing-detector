"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { isApiError } from "@/lib/api/client";

export type AsyncState<T> =
  | { status: "idle"; data: null; error: null }
  | { status: "loading"; data: T | null; error: null }
  | { status: "success"; data: T; error: null }
  | { status: "error"; data: null; error: unknown };

/**
 * Run an API call when `key` changes (null key = do nothing). Previous in-flight requests are aborted,
 * so a slow earlier response can never overwrite a newer one. Errors are surfaced, never swallowed.
 */
export function useApiQuery<T>(
  key: string | null,
  fetcher: (signal: AbortSignal) => Promise<T>,
): AsyncState<T> & { reload: () => void } {
  const [nonce, setNonce] = useState(0);
  const requestId = key === null ? null : `${key}#${nonce}`;
  // Settled result, tagged with the request it belongs to; anything else is "loading".
  const [settled, setSettled] = useState<{ id: string; ok: true; data: T } | { id: string; ok: false; error: unknown } | null>(
    null,
  );
  const fetcherRef = useRef(fetcher);
  useEffect(() => {
    fetcherRef.current = fetcher;
  });

  useEffect(() => {
    if (requestId === null) return;
    const controller = new AbortController();
    fetcherRef.current(controller.signal).then(
      (data) => {
        if (!controller.signal.aborted) setSettled({ id: requestId, ok: true, data });
      },
      (error: unknown) => {
        if (controller.signal.aborted) return;
        if (isApiError(error) && error.kind === "aborted") return;
        setSettled({ id: requestId, ok: false, error });
      },
    );
    return () => controller.abort();
  }, [requestId]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);

  let state: AsyncState<T>;
  if (requestId === null) state = { status: "idle", data: null, error: null };
  else if (!settled || settled.id !== requestId) state = { status: "loading", data: null, error: null };
  else if (settled.ok) state = { status: "success", data: settled.data, error: null };
  else state = { status: "error", data: null, error: settled.error };
  return { ...state, reload };
}

/**
 * Imperative variant for user-triggered, potentially long operations (assessments).
 * Exposes elapsed time and explicit cancellation.
 */
export function useApiMutation<TArgs extends unknown[], T>(fn: (signal: AbortSignal, ...args: TArgs) => Promise<T>) {
  const [state, setState] = useState<AsyncState<T>>({ status: "idle", data: null, error: null });
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const controllerRef = useRef<AbortController | null>(null);
  const fnRef = useRef(fn);
  useEffect(() => {
    fnRef.current = fn;
  });

  useEffect(() => () => controllerRef.current?.abort(), []);

  const run = useCallback(async (...args: TArgs): Promise<T | null> => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setStartedAt(Date.now());
    setState({ status: "loading", data: null, error: null });
    try {
      const data = await fnRef.current(controller.signal, ...args);
      if (controller.signal.aborted) return null;
      setState({ status: "success", data, error: null });
      return data;
    } catch (error) {
      if (controller.signal.aborted && isApiError(error) && error.kind === "aborted") {
        setState({ status: "idle", data: null, error: null });
        return null;
      }
      setState({ status: "error", data: null, error });
      return null;
    } finally {
      if (controllerRef.current === controller) setStartedAt(null);
    }
  }, []);

  const cancel = useCallback(() => {
    controllerRef.current?.abort();
  }, []);

  const reset = useCallback(() => setState({ status: "idle", data: null, error: null }), []);

  return { ...state, run, cancel, reset, startedAt };
}

/** Ticks every second while `active`, for elapsed-time displays during long requests. */
export function useNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [active]);
  return now;
}
