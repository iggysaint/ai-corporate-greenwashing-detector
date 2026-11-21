import { describe, expect, it } from "vitest";
import { confidenceAdjustment, formatPercent, formatScore, formatSigned } from "./format";
import { safeExternalUrl, validateReportingPeriod, validateReportUrl, validateTicker } from "./validation";

describe("validateTicker", () => {
  it("normalises and accepts SEC tickers including class shares", () => {
    expect(validateTicker(" aapl ", "us_sec")).toEqual({ ok: true, value: "AAPL" });
    expect(validateTicker("brk-b", "us_sec")).toEqual({ ok: true, value: "BRK-B" });
    expect(validateTicker("BRK.B", "us_sec")).toEqual({ ok: true, value: "BRK.B" });
  });
  it("rejects invalid input per market rules", () => {
    expect(validateTicker("", "us_sec").ok).toBe(false);
    expect(validateTicker("@@@", "us_sec").ok).toBe(false);
    expect(validateTicker("TOOLONGTICKER", "us_sec").ok).toBe(false);
    expect(validateTicker("BRK-B", "gh_gse").ok).toBe(false);
    expect(validateTicker("mtngh", "gh_gse")).toEqual({ ok: true, value: "MTNGH" });
  });
});

describe("validateReportUrl", () => {
  it("accepts public http(s) URLs", () => {
    expect(validateReportUrl("https://mtn.com.gh/report.pdf").ok).toBe(true);
  });
  it("rejects non-http schemes, credentials and bare hosts", () => {
    expect(validateReportUrl("javascript:alert(1)").ok).toBe(false);
    expect(validateReportUrl("file:///etc/passwd").ok).toBe(false);
    expect(validateReportUrl("https://user:pw@example.com/a.pdf").ok).toBe(false);
    expect(validateReportUrl("http://localhost/a.pdf").ok).toBe(false);
    expect(validateReportUrl("not a url").ok).toBe(false);
  });
});

describe("validateReportingPeriod", () => {
  it("allows empty and short labels only", () => {
    expect(validateReportingPeriod("")).toEqual({ ok: true, value: "" });
    expect(validateReportingPeriod("FY2024").ok).toBe(true);
    expect(validateReportingPeriod("<script>").ok).toBe(false);
  });
});

describe("safeExternalUrl", () => {
  it("only returns http(s) links", () => {
    expect(safeExternalUrl("https://www.sec.gov/x.htm")).toBe("https://www.sec.gov/x.htm");
    expect(safeExternalUrl("javascript:alert(1)")).toBeNull();
    expect(safeExternalUrl("SEC EDGAR Form 10-K, accession 000")).toBeNull();
    expect(safeExternalUrl(null)).toBeNull();
  });
});

describe("formatting of missing values", () => {
  it("never turns null into zero", () => {
    expect(formatScore(null)).toBeNull();
    expect(formatPercent(null)).toBeNull();
    expect(formatScore(0)).toBe("0");
    expect(formatPercent(73)).toBe("73%");
  });
  it("formats signed adjustments", () => {
    expect(formatSigned(3)).toBe("+3");
    expect(formatSigned(-6)).toBe("−6");
    expect(formatSigned(0)).toBe("0");
  });
});

describe("confidenceAdjustment", () => {
  it("reads only the backend's explicit confidence reasons", () => {
    expect(confidenceAdjustment(["+3: high evaluation confidence", "+3: mean cited-evidence relevance 0.45 >= 0.40"])).toBe("high");
    expect(confidenceAdjustment(["-3: low evaluation confidence"])).toBe("low");
    expect(confidenceAdjustment(["-3: no validated evidence citation"])).toBeNull();
    expect(confidenceAdjustment([])).toBeNull();
  });
});
