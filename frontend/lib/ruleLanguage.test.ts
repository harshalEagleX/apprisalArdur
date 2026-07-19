/**
 * Rejection wording shown to the reviewer.
 *
 * The contract that matters: the ENGINE owns rejection language. The local
 * fallback is a development stopgap and must never quietly replace real engine
 * text, never invent a rule-specific finding, and never name a document the
 * evidence did not actually come from.
 */
import { describe, expect, it } from "vitest";

import { buildSourceLabel, failRejectionLanguage } from "@/lib/ruleLanguage";
import type { QCRuleResult } from "@/lib/api";

function rule(over: Partial<QCRuleResult> = {}): QCRuleResult {
  return {
    id: 1,
    ruleId: "S-1",
    ruleName: "Subject address",
    status: "fail",
    message: "values differ",
    reviewRequired: true,
    ...over,
  } as QCRuleResult;
}

describe("buildSourceLabel", () => {
  it("is empty when no evidence was located", () => {
    expect(buildSourceLabel(rule({ evidence: [] }))).toBe("");
  });

  it("names a single document", () => {
    expect(buildSourceLabel(rule({ evidence: ["appraisal: X (90%)"] })))
      .toBe("the appraisal report");
  });

  it("joins two documents with 'and'", () => {
    const s = buildSourceLabel(rule({
      evidence: ["appraisal: X (90%)", "contract: Y (90%)"],
    }));
    expect(s).toBe("the appraisal report and the sales contract");
  });

  it("de-duplicates when several values share one document", () => {
    const s = buildSourceLabel(rule({
      evidence: ["appraisal: X (90%)", "appraisal: Y (90%)"],
    }));
    expect(s).toBe("the appraisal report");
  });

  it("never names the engagement letter when the value came from the contract", () => {
    // The whole point of deriving this from evidence rather than rule id.
    const s = buildSourceLabel(rule({ evidence: ["contract: 395,000 (90%)"] }));
    expect(s).toContain("sales contract");
    expect(s).not.toContain("engagement");
  });
});

describe("failRejectionLanguage", () => {
  it("uses the engine's rejectionText verbatim and flags it as non-fallback", () => {
    const r = failRejectionLanguage(rule({
      rejectionText: "Please provide the missing exposure time.",
    }));
    expect(r.text).toBe("Please provide the missing exposure time.");
    expect(r.isFallback).toBe(false);
  });

  it("trims engine text but keeps it authoritative", () => {
    const r = failRejectionLanguage(rule({ rejectionText: "  Fix the address.  " }));
    expect(r.text).toBe("Fix the address.");
    expect(r.isFallback).toBe(false);
  });

  it("falls back and MARKS the fallback when the engine supplied nothing", () => {
    // isFallback is the signal that the engine has a gap — it must not be
    // silently indistinguishable from real rejection language.
    const r = failRejectionLanguage(rule({ rejectionText: "" }));
    expect(r.isFallback).toBe(true);
    expect(r.text.length).toBeGreaterThan(0);
  });

  it("treats whitespace-only engine text as absent", () => {
    expect(failRejectionLanguage(rule({ rejectionText: "   " })).isFallback).toBe(true);
  });

  it.each([
    ["S-1", "Subject property"],
    ["C-2", "Contract section"],
    ["N-3", "Neighborhood"],
    ["SCA-4", "Sales comparison"],
    ["FHA-5", "FHA requirement"],
    ["COM-6", "Commentary"],
    ["ADD-7", "Addendum"],
  ])("frames %s by its section", (ruleId, expected) => {
    const r = failRejectionLanguage(rule({ ruleId, rejectionText: undefined }));
    expect(r.text).toContain(expected);
    expect(r.isFallback).toBe(true);
  });

  it("uses a generic frame for an unknown rule prefix", () => {
    const r = failRejectionLanguage(rule({
      ruleId: "ZZZ-9", ruleName: "Some rule", message: "went wrong",
      rejectionText: undefined,
    }));
    expect(r.text).toContain("Some rule");
    expect(r.text).toContain("went wrong");
  });

  it("includes the page number when the rule has one", () => {
    const r = failRejectionLanguage(rule({
      ruleId: "S-1", pdfPage: 7, rejectionText: undefined,
      evidence: ["appraisal: X (90%)"],
    }));
    expect(r.text).toContain("page 7");
  });

  it("omits the page clause when there is no page", () => {
    const r = failRejectionLanguage(rule({
      ruleId: "S-1", pdfPage: 0, rejectionText: undefined,
    }));
    expect(r.text).not.toContain("page ");
  });

  it("never throws on a sparse rule", () => {
    expect(() => failRejectionLanguage({ id: 1 } as QCRuleResult)).not.toThrow();
  });
});
