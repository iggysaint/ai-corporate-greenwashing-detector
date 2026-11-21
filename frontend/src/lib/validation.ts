import type { MarketId } from "./api/types";

/** Mirrors app/services/sec_service.py::TICKER_REGEX (applied after upper-casing). */
const SEC_TICKER = /^[A-Z0-9.-]{1,10}$/;
/** Mirrors app/services/gse_service.py::normalize_gse_ticker. */
const GSE_TICKER = /^[A-Z0-9]{1,10}$/;

export type ValidationResult = { ok: true; value: string } | { ok: false; error: string };

export function normalizeTicker(raw: string): string {
  return raw.trim().toUpperCase();
}

export function validateTicker(raw: string, market: MarketId): ValidationResult {
  const value = normalizeTicker(raw);
  if (!value) return { ok: false, error: "Enter a ticker symbol." };
  if (market === "gh_gse") {
    return GSE_TICKER.test(value)
      ? { ok: true, value }
      : { ok: false, error: "GSE tickers are 1–10 letters or digits (e.g. MTNGH)." };
  }
  return SEC_TICKER.test(value)
    ? { ok: true, value }
    : { ok: false, error: "US tickers are 1–10 letters, digits, dots or hyphens (e.g. AAPL, BRK.B)." };
}

export function isMarketId(value: string | null | undefined): value is MarketId {
  return value === "us_sec" || value === "gh_gse";
}

const MAX_URL_LENGTH = 2048;

/**
 * Client-side sanity check for user-supplied report URLs. This is a usability guard only;
 * the backend remains the security boundary (SSRF protection, extension and size checks).
 */
export function validateReportUrl(raw: string): ValidationResult {
  const value = raw.trim();
  if (!value) return { ok: false, error: "Enter the public URL of an annual or sustainability report." };
  if (value.length > MAX_URL_LENGTH) return { ok: false, error: "URL is too long." };
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    return { ok: false, error: "Enter a complete URL beginning with https://" };
  }
  if (parsed.protocol !== "https:" && parsed.protocol !== "http:") {
    return { ok: false, error: "Only http(s) URLs are accepted." };
  }
  if (parsed.username || parsed.password) {
    return { ok: false, error: "URLs containing credentials are not accepted." };
  }
  if (!parsed.hostname.includes(".")) {
    return { ok: false, error: "Use a publicly reachable host name." };
  }
  return { ok: true, value: parsed.toString() };
}

/** Reporting period is free text on the backend (e.g. "2024", "FY2024"); keep it short and printable. */
export function validateReportingPeriod(raw: string): ValidationResult {
  const value = raw.trim();
  if (!value) return { ok: true, value: "" };
  if (value.length > 20 || !/^[\w\s./-]+$/.test(value)) {
    return { ok: false, error: "Use a short period label such as 2024 or FY2024." };
  }
  return { ok: true, value };
}

/** Only render external links whose scheme is http(s); anything else is shown as plain text. */
export function safeExternalUrl(raw: string | null | undefined): string | null {
  if (!raw) return null;
  try {
    const parsed = new URL(raw);
    return parsed.protocol === "https:" || parsed.protocol === "http:" ? parsed.toString() : null;
  } catch {
    return null;
  }
}
