import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, buildUrl, describeError, request } from "./client";
import { api, fetchScoreBreakdown } from "./endpoints";

function mockFetch(status: number, body: unknown) {
  const fn = vi.fn(async () => new Response(typeof body === "string" ? body : JSON.stringify(body), { status }));
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("buildUrl", () => {
  it("drops empty and null query values and encodes the rest", () => {
    const url = new URL(buildUrl("/api/v1/x", { a: "1 2", b: null, c: undefined, d: "  ", e: "https://x.y/?q=1&r=2" }));
    expect(url.searchParams.get("a")).toBe("1 2");
    expect(url.searchParams.has("b")).toBe(false);
    expect(url.searchParams.has("c")).toBe(false);
    expect(url.searchParams.has("d")).toBe(false);
    expect(url.searchParams.get("e")).toBe("https://x.y/?q=1&r=2");
  });
});

describe("endpoints", () => {
  it("encodes ticker path segments so input cannot change the route", async () => {
    const fetchFn = mockFetch(200, {});
    await api.secCompany("A/../../health");
    const called = String((fetchFn.mock.calls[0] as unknown[])[0]);
    expect(called).toContain("/api/v1/companies/A%2F..%2F..%2Fhealth");
  });

  it("passes GSE source_url and reporting_period as query parameters", async () => {
    const fetchFn = mockFetch(200, {});
    await fetchScoreBreakdown("gh_gse", "MTNGH", { sourceUrl: "https://example.com/r.pdf", reportingPeriod: "2024" });
    const url = new URL(String((fetchFn.mock.calls[0] as unknown[])[0]));
    expect(url.pathname).toBe("/api/v1/gse/companies/MTNGH/score/breakdown");
    expect(url.searchParams.get("source_url")).toBe("https://example.com/r.pdf");
    expect(url.searchParams.get("reporting_period")).toBe("2024");
  });

  it("routes SEC scoring to the companies endpoint without GSE parameters", async () => {
    const fetchFn = mockFetch(200, {});
    await fetchScoreBreakdown("us_sec", "AAPL", { sourceUrl: "https://ignored" });
    const url = new URL(String((fetchFn.mock.calls[0] as unknown[])[0]));
    expect(url.pathname).toBe("/api/v1/companies/AAPL/score/breakdown");
    expect(url.search).toBe("");
  });
});

describe("request error handling", () => {
  it("preserves null values in successful responses", async () => {
    mockFetch(200, { esg_integrity_score: null, environmental_score: null, substantiation_rate: null });
    const data = await request<Record<string, unknown>>("/x");
    expect(data.esg_integrity_score).toBeNull();
    expect(data.environmental_score).toBeNull();
  });

  it.each([
    [400, "invalid_gse_ticker", "Invalid request"],
    [404, "company_not_found", "Not found"],
    [422, "gse_document_source_required", "Report URL required"],
    [502, "gse_document_retrieval_error", "Upstream source failed"],
    [503, "sec_rate_limit", "Service temporarily unavailable"],
  ])("maps HTTP %i (%s) to a typed error", async (status, code, title) => {
    mockFetch(status, { detail: "backend message", error: code });
    const err = await request("/x").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    const e = err as ApiError;
    expect(e.kind).toBe("http");
    expect(e.status).toBe(status);
    expect(e.code).toBe(code);
    expect(e.message).toBe("backend message");
    expect(describeError(e).title).toBe(title);
  });

  it("formats FastAPI request-validation 422 details", async () => {
    mockFetch(422, { detail: [{ loc: ["query", "max_passages"], msg: "Input should be less than 200", type: "x" }] });
    const e = (await request("/x").catch((x: unknown) => x)) as ApiError;
    expect(e.status).toBe(422);
    expect(e.message).toBe("max_passages: Input should be less than 200");
    expect(e.issues).toHaveLength(1);
  });

  it("reports network failures as unreachable, not as empty data", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("Failed to fetch"))));
    const e = (await request("/x").catch((x: unknown) => x)) as ApiError;
    expect(e.kind).toBe("network");
    expect(describeError(e).title).toBe("Analysis API unreachable");
  });

  it("times out long requests", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (_url: string, init: RequestInit) =>
          new Promise((_resolve, reject) => {
            init.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
          }),
      ),
    );
    const e = (await request("/x", { timeoutMs: 20 }).catch((x: unknown) => x)) as ApiError;
    expect(e.kind).toBe("timeout");
  });

  it("distinguishes caller cancellation from timeouts", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (_url: string, init: RequestInit) =>
          new Promise((_resolve, reject) => {
            init.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
          }),
      ),
    );
    const controller = new AbortController();
    const p = request("/x", { signal: controller.signal }).catch((x: unknown) => x);
    controller.abort();
    expect(((await p) as ApiError).kind).toBe("aborted");
  });

  it("rejects non-JSON success bodies", async () => {
    mockFetch(200, "<html>proxy page</html>");
    const e = (await request("/x").catch((x: unknown) => x)) as ApiError;
    expect(e.kind).toBe("parse");
  });
});
