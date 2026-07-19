/**
 * Evidence interpretation — the code that decides WHAT THE REVIEWER SEES.
 *
 * This module was at 0% coverage, which is the wrong place to have none: a bug
 * here mislabels which document a value came from, or implies a comparison that
 * never happened. Both are exactly the kind of thing that makes a reviewer stop
 * trusting the tool. Its own docstring says it must "never imply a comparison
 * that did not happen, and never mislabel which document a value came from" —
 * these tests hold it to that.
 */
import { describe, expect, it } from "vitest";

import {
  buildEvidenceModel,
  cleanRuleValue,
  documentLabel,
  evidenceText,
  parseEvidence,
} from "@/lib/ruleEvidence";
import type { QCRuleResult } from "@/lib/api";

/**
 * Minimal rule; every field the module reads is overridable.
 *
 * `evidence` is typed loosely on purpose: parseEvidence accepts THREE shapes at
 * runtime — a structured array, legacy "doc: value (95%)" strings, and a
 * JSON-string blob — and the tests must be able to feed all three.
 */
type RuleOverrides = Partial<Omit<QCRuleResult, "evidence">> & { evidence?: unknown };

function rule(over: RuleOverrides = {}): QCRuleResult {
  return {
    id: 1,
    ruleId: "S-1",
    ruleName: "Subject address",
    status: "fail",
    message: "mismatch",
    reviewRequired: true,
    ...over,
  } as unknown as QCRuleResult;
}

// ── documentLabel ───────────────────────────────────────────────────────────

describe("documentLabel", () => {
  it("maps every known document token to its reviewer-facing name", () => {
    expect(documentLabel("appraisal")).toBe("Appraisal report");
    expect(documentLabel("subject")).toBe("Appraisal report");
    expect(documentLabel("report")).toBe("Appraisal report");
    expect(documentLabel("engagement")).toBe("Engagement letter");
    expect(documentLabel("order")).toBe("Order form");
    expect(documentLabel("contract")).toBe("Sales contract");
    expect(documentLabel("sales_contract")).toBe("Sales contract");
  });

  it("is case- and whitespace-insensitive", () => {
    expect(documentLabel("  APPRAISAL  ")).toBe("Appraisal report");
    expect(documentLabel("Sales Contract")).toBe("Sales contract");
  });

  it("title-cases an unknown token instead of dropping it", () => {
    // A new document type must render sensibly with no code change.
    expect(documentLabel("flood_cert")).toBe("Flood Cert");
    expect(documentLabel("tax_bill")).toBe("Tax Bill");
  });
});

// ── cleanRuleValue: backend sentinels must never reach the screen ───────────

describe("cleanRuleValue", () => {
  it("strips the backend's no-value sentinels", () => {
    expect(cleanRuleValue("__NO_APPRAISAL_VALUE__")).toBeUndefined();
    expect(cleanRuleValue("__NO_EXTRACTED_VALUE__")).toBeUndefined();
    expect(cleanRuleValue("__NO_EXPECTED_VALUE__")).toBeUndefined();
    expect(cleanRuleValue("__NO_ENGAGEMENT_VALUE")).toBeUndefined(); // older form
  });

  it("treats empty and nullish as absent", () => {
    expect(cleanRuleValue("")).toBeUndefined();
    expect(cleanRuleValue("   ")).toBeUndefined();
    expect(cleanRuleValue(null)).toBeUndefined();
    expect(cleanRuleValue(undefined)).toBeUndefined();
  });

  it("keeps a real value and trims it", () => {
    expect(cleanRuleValue("  123 Main St  ")).toBe("123 Main St");
    // must NOT be mistaken for a sentinel
    expect(cleanRuleValue("__NOT_A_SENTINEL")).toBe("__NOT_A_SENTINEL");
    expect(cleanRuleValue("0")).toBe("0");
  });
});

// ── parseEvidence: string form ──────────────────────────────────────────────

describe("parseEvidence — legacy string entries", () => {
  it("parses document, value, confidence and page", () => {
    const [s] = parseEvidence(rule({ evidence: ["appraisal: 123 Main St (95%, p4)"] }));
    expect(s).toMatchObject({
      document: "appraisal",
      label: "Appraisal report",
      value: "123 Main St",
      confidence: 0.95,
      page: 4,
    });
  });

  it("parses an entry with confidence but no page", () => {
    const [s] = parseEvidence(rule({ evidence: ["contract: 123 Main Street (90%)"] }));
    expect(s.confidence).toBe(0.9);
    expect(s.page).toBeUndefined();
  });

  it("keeps colons and parens that belong to the VALUE", () => {
    // the trailing (NN%, pN) is anchored at the end, so inner punctuation survives
    const [s] = parseEvidence(rule({ evidence: ["appraisal: Unit 4: Apt (rear) (88%, p2)"] }));
    expect(s.value).toBe("Unit 4: Apt (rear)");
    expect(s.confidence).toBe(0.88);
  });

  it("falls back to '<doc>: <value>' with no meta", () => {
    const [s] = parseEvidence(rule({ evidence: ["engagement: Acme Lending"] }));
    expect(s).toMatchObject({ document: "engagement", value: "Acme Lending" });
    expect(s.confidence).toBeUndefined();
  });

  it("drops entries whose value is a sentinel or unparseable", () => {
    expect(parseEvidence(rule({ evidence: ["appraisal: __NO_APPRAISAL_VALUE__ (95%)"] }))).toEqual([]);
    expect(parseEvidence(rule({ evidence: ["no colon here"] }))).toEqual([]);
    expect(parseEvidence(rule({ evidence: [""] }))).toEqual([]);
  });
});

// ── parseEvidence: structured form ──────────────────────────────────────────

describe("parseEvidence — structured entries", () => {
  it("reads the full structured shape", () => {
    const [s] = parseEvidence(rule({
      evidence: [{ document: "appraisal", value: "1,850", comparable: "Comp 1",
                   confidence: 0.9, page: 3, method: "xml" }],
    }));
    expect(s).toMatchObject({
      document: "appraisal", label: "Appraisal report", value: "1,850",
      comparable: "Comp 1", confidence: 0.9, page: 3, method: "xml",
    });
  });

  it("coerces a non-string value rather than dropping it", () => {
    const [s] = parseEvidence(rule({ evidence: [{ document: "appraisal", value: 1850 }] }));
    expect(s.value).toBe("1850");
  });

  it("drops an entry with no document or no value", () => {
    expect(parseEvidence(rule({ evidence: [{ value: "x" }] }))).toEqual([]);
    expect(parseEvidence(rule({ evidence: [{ document: "appraisal" }] }))).toEqual([]);
    expect(parseEvidence(rule({ evidence: [null, 42, true] }))).toEqual([]);
  });

  it("parses evidence delivered as a JSON string blob (legacy rows)", () => {
    const blob = JSON.stringify([{ document: "contract", value: "395,000" }]);
    const [s] = parseEvidence(rule({ evidence: blob }));
    expect(s).toMatchObject({ document: "contract", value: "395,000" });
  });

  it("survives a non-JSON string without throwing", () => {
    expect(() => parseEvidence(rule({ evidence: "{not json" }))).not.toThrow();
  });
});

// ── de-duplication ──────────────────────────────────────────────────────────

describe("parseEvidence — de-duplication", () => {
  it("collapses identical repeated evidence", () => {
    const out = parseEvidence(rule({
      evidence: ["appraisal: 123 Main St (95%)",
                 "appraisal: 123 Main St (95%)"],
    }));
    expect(out).toHaveLength(1);
  });

  it("does NOT collapse two comps that happen to share a value", () => {
    // The comparable is part of the key precisely so "Comp 1: 6000 sf" and
    // "Comp 2: 6000 sf" both survive — collapsing them would hide a real row.
    const out = parseEvidence(rule({
      evidence: [
        { document: "appraisal", value: "6000 sf", comparable: "Comp 1" },
        { document: "appraisal", value: "6000 sf", comparable: "Comp 2" },
      ],
    }));
    expect(out).toHaveLength(2);
  });
});

// ── flattened fallback ──────────────────────────────────────────────────────

describe("parseEvidence — flattened fallback", () => {
  it("uses appraisal/engagement values when there is no structured evidence", () => {
    const out = parseEvidence(rule({
      evidence: [], appraisalValue: "123 Main St", engagementValue: "123 Main Street",
    }));
    expect(out.map(s => s.value)).toEqual(["123 Main St", "123 Main Street"]);
  });

  it("never claims the second value is engagement rather than contract", () => {
    // The flattened field cannot say which document it came from, so the label
    // must stay generic — mislabelling it would mislead the reviewer.
    const [, second] = parseEvidence(rule({
      evidence: [], appraisalValue: "A", engagementValue: "B",
    }));
    expect(second.document).toBe("supporting");
    expect(second.label).toBe("Supporting document");
  });

  it("falls back to extracted/expected when the primary fields are empty", () => {
    const out = parseEvidence(rule({
      evidence: [], extractedValue: "found-x", expectedValue: "want-y",
    }));
    expect(out.map(s => s.value)).toEqual(["found-x", "want-y"]);
  });

  it("returns nothing when every source is a sentinel", () => {
    expect(parseEvidence(rule({
      evidence: [], appraisalValue: "__NO_APPRAISAL_VALUE__",
      engagementValue: "__NO_ENGAGEMENT_VALUE__",
    }))).toEqual([]);
  });

  it("prefers structured evidence over the flattened fallback", () => {
    const out = parseEvidence(rule({
      evidence: ["contract: from-structured (90%)"],
      appraisalValue: "from-flattened",
    }));
    expect(out).toHaveLength(1);
    expect(out[0].value).toBe("from-structured");
  });
});

// ── the presentation decision ───────────────────────────────────────────────

describe("buildEvidenceModel", () => {
  it("reports 'none' when nothing was located", () => {
    const m = buildEvidenceModel(rule({ evidence: [] }));
    expect(m.mode).toBe("none");
    expect(m.headline).toBe("");
  });

  it("reports 'single' and says there is nothing to compare", () => {
    const m = buildEvidenceModel(rule({ evidence: ["appraisal: 123 Main St (95%)"] }));
    expect(m.mode).toBe("single");
    expect(m.headline).toContain("nothing to compare");
  });

  it("reports 'compare' across two documents and names both", () => {
    const m = buildEvidenceModel(rule({
      evidence: ["appraisal: 123 Main St (95%)", "contract: 123 Main Street (90%)"],
    }));
    expect(m.mode).toBe("compare");
    expect(m.headline).toContain("Appraisal report");
    expect(m.headline).toContain("Sales contract");
  });

  it("says 'within' when both values came from the SAME document", () => {
    // Two comps inside the appraisal is not a cross-document comparison, and
    // the wording must not imply one.
    const m = buildEvidenceModel(rule({
      evidence: [
        { document: "appraisal", value: "1,850", comparable: "Comp 1" },
        { document: "appraisal", value: "2,140", comparable: "Comp 2" },
      ],
    }));
    expect(m.mode).toBe("compare");
    expect(m.headline).toContain("within");
  });
});

describe("evidenceText", () => {
  it("flattens document + value into a search corpus", () => {
    const t = evidenceText(rule({
      evidence: ["appraisal: 123 Main St (95%)", "contract: 123 Main Street (90%)"],
    }));
    expect(t).toContain("appraisal 123 Main St");
    expect(t).toContain("contract 123 Main Street");
  });

  it("is empty when there is no evidence", () => {
    expect(evidenceText(rule({ evidence: [] }))).toBe("");
  });
});
