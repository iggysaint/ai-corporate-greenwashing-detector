/**
 * Minimal typed HTTP client for the FastAPI backend.
 *
 * - Base URL comes from NEXT_PUBLIC_API_BASE_URL (public by design: the browser calls the API directly,
 *   and the backend's CORS_ALLOW_ORIGINS must include this frontend's origin).
 * - Every request has a timeout and accepts an external AbortSignal.
 * - Failures are never swallowed: callers always receive an ApiError describing what happened.
 */

import type { BackendErrorBody, ValidationIssue } from "./types";

const DEFAULT_BASE_URL = "http://127.0.0.1:8000";

/** Standard lookups (company metadata, listings, history). */
export const STANDARD_TIMEOUT_MS = 60_000;

function readTimeout(raw: string | undefined, fallback: number): number {
  const parsed = raw ? Number.parseInt(raw, 10) : Number.NaN;
  return Number.isFinite(parsed) && parsed >= 60_000 ? parsed : fallback;
}

/**
 * Full assessments download and parse a filing/report and evaluate every claim; on a cold backend this
 * can take several minutes. Configurable, never below 60 s.
 */
export const ANALYSIS_TIMEOUT_MS = readTimeout(process.env.NEXT_PUBLIC_ANALYSIS_TIMEOUT_MS, 300_000);

export function getApiBaseUrl(): string {
  const raw = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  const base = raw && raw.length > 0 ? raw : DEFAULT_BASE_URL;
  return base.replace(/\/+$/, "");
}

export type ApiErrorKind = "http" | "network" | "timeout" | "aborted" | "parse";

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  /** HTTP status, or 0 when no response was received. */
  readonly status: number;
  /** Machine-readable `error` code from the backend's exception handlers, when provided. */
  readonly code: string | null;
  /** Field-level problems from FastAPI request validation (422), when provided. */
  readonly issues: ValidationIssue[];
  readonly url: string;

  constructor(init: {
    kind: ApiErrorKind;
    message: string;
    status?: number;
    code?: string | null;
    issues?: ValidationIssue[];
    url: string;
  }) {
    super(init.message);
    this.name = "ApiError";
    this.kind = init.kind;
    this.status = init.status ?? 0;
    this.code = init.code ?? null;
    this.issues = init.issues ?? [];
    this.url = init.url;
  }
}

export function isApiError(value: unknown): value is ApiError {
  return value instanceof ApiError;
}

export type QueryValue = string | number | boolean | null | undefined;

export interface RequestOptions {
  method?: "GET" | "POST";
  query?: Record<string, QueryValue>;
  signal?: AbortSignal;
  timeoutMs?: number;
}

/** Encode one path segment (tickers, claim IDs) so user input can never alter the route. */
export function seg(value: string): string {
  return encodeURIComponent(value);
}

export function buildUrl(path: string, query?: Record<string, QueryValue>): string {
  const url = new URL(`${getApiBaseUrl()}${path.startsWith("/") ? path : `/${path}`}`);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value === undefined || value === null) continue;
      const str = String(value).trim();
      if (str.length === 0) continue;
      url.searchParams.set(key, str);
    }
  }
  return url.toString();
}

function messageFromBody(body: BackendErrorBody | null, status: number): {
  message: string;
  issues: ValidationIssue[];
} {
  if (body && typeof body.detail === "string" && body.detail.trim()) {
    return { message: body.detail, issues: [] };
  }
  if (body && Array.isArray(body.detail)) {
    const issues = body.detail;
    const text = issues
      .map((i) => {
        const field = (i.loc ?? []).filter((p) => p !== "query" && p !== "path" && p !== "body").join(".");
        return field ? `${field}: ${i.msg ?? "invalid value"}` : (i.msg ?? "invalid value");
      })
      .join("; ");
    return { message: text || "The request was rejected by validation.", issues };
  }
  return { message: `The server responded with HTTP ${status}.`, issues: [] };
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", query, signal, timeoutMs = STANDARD_TIMEOUT_MS } = options;
  const url = buildUrl(path, query);

  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  const onExternalAbort = () => controller.abort();
  if (signal) {
    if (signal.aborted) controller.abort();
    else signal.addEventListener("abort", onExternalAbort, { once: true });
  }

  let response: Response;
  try {
    response = await fetch(url, {
      method,
      headers: { Accept: "application/json" },
      signal: controller.signal,
      cache: "no-store",
    });
  } catch (err) {
    if (timedOut) {
      throw new ApiError({
        kind: "timeout",
        message: `The request did not complete within ${Math.round(timeoutMs / 1000)} seconds.`,
        url,
      });
    }
    if (controller.signal.aborted) {
      throw new ApiError({ kind: "aborted", message: "The request was cancelled.", url });
    }
    throw new ApiError({
      kind: "network",
      message:
        `Could not reach the analysis API at ${getApiBaseUrl()}. Check that the FastAPI server is running ` +
        `and that its CORS_ALLOW_ORIGINS includes this site's origin.` +
        (err instanceof Error && err.message ? ` (${err.message})` : ""),
      url,
    });
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", onExternalAbort);
  }

  const text = await response.text();
  let body: unknown = null;
  if (text.length > 0) {
    try {
      body = JSON.parse(text);
    } catch {
      if (response.ok) {
        throw new ApiError({
          kind: "parse",
          status: response.status,
          message: "The server returned a response that is not valid JSON.",
          url,
        });
      }
    }
  }

  if (!response.ok) {
    const errorBody = (body && typeof body === "object" ? body : null) as BackendErrorBody | null;
    const { message, issues } = messageFromBody(errorBody, response.status);
    throw new ApiError({
      kind: "http",
      status: response.status,
      code: errorBody && typeof errorBody.error === "string" ? errorBody.error : null,
      message,
      issues,
      url,
    });
  }

  return body as T;
}

/** User-facing headline and guidance for an error, keyed by HTTP status and backend error code. */
export function describeError(error: unknown): { title: string; message: string; hint: string | null } {
  if (!isApiError(error)) {
    return {
      title: "Unexpected error",
      message: error instanceof Error ? error.message : String(error),
      hint: null,
    };
  }
  switch (error.kind) {
    case "network":
      return { title: "Analysis API unreachable", message: error.message, hint: null };
    case "timeout":
      return {
        title: "Request timed out",
        message: error.message,
        hint: "Large filings and PDF reports can take several minutes on a cold server. Try again; completed work is cached by the backend.",
      };
    case "aborted":
      return { title: "Request cancelled", message: error.message, hint: null };
    case "parse":
      return { title: "Unreadable response", message: error.message, hint: null };
    case "http":
      break;
  }

  const code = error.code;
  if (code === "gse_document_source_required") {
    return {
      title: "Report URL required",
      message: error.message,
      hint: "This issuer has no verified public report on file. Provide a public annual or sustainability report URL to run the assessment.",
    };
  }
  if (code === "ssrf_security_violation") {
    return {
      title: "URL not permitted",
      message: error.message,
      hint: "The backend blocks private, local and otherwise unsafe addresses. Use a publicly hosted report URL.",
    };
  }

  switch (error.status) {
    case 400:
      return { title: "Invalid request", message: error.message, hint: "Check the ticker symbol or the submitted URL." };
    case 403:
      return { title: "Request blocked", message: error.message, hint: null };
    case 404:
      return { title: "Not found", message: error.message, hint: "Verify the ticker symbol and selected market." };
    case 422:
      return { title: "Request could not be processed", message: error.message, hint: null };
    case 502:
      return {
        title: "Upstream source failed",
        message: error.message,
        hint: "The filing or report source could not be retrieved or parsed. The source may be temporarily unavailable.",
      };
    case 503:
      return {
        title: "Service temporarily unavailable",
        message: error.message,
        hint: "An upstream data provider is rate-limiting or unreachable. Wait a moment and retry.",
      };
    default:
      return { title: `Server error (HTTP ${error.status})`, message: error.message, hint: null };
  }
}
