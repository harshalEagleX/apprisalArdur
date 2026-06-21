import { describe, it, expect } from "vitest";
import type { QCRuleResult } from "@/lib/api";
import {
  clampZoom, ZOOM_MIN, ZOOM_MAX,
  sectionRank, sectionLabel,
  ruleGroupKey, shouldGroupRule, groupLabelForRule,
  isNotApplicable, focusForRule, safeReviewerQueuePath,
} from "@/lib/reviewVerify";

// Minimal rule factory — only the fields the functions under test read.
function rule(partial: Partial<QCRuleResult>): QCRuleResult {
  return { ruleId: "X-1", ...partial } as QCRuleResult;
}

describe("clampZoom", () => {
  it("clamps below the minimum", () => {
    expect(clampZoom(0.1)).toBe(ZOOM_MIN);
  });
  it("clamps above the maximum", () => {
    expect(clampZoom(5)).toBe(ZOOM_MAX);
  });
  it("rounds to one decimal place inside the range", () => {
    expect(clampZoom(1.23)).toBe(1.2);
  });
});

describe("sectionRank / sectionLabel", () => {
  it("orders known sections by report order", () => {
    expect(sectionRank("SUBJECT")).toBeLessThan(sectionRank("CONTRACT"));
  });
  it("ranks an unknown section past every known one (including OTHER)", () => {
    expect(sectionRank("MADE_UP")).toBeGreaterThan(sectionRank("OTHER"));
  });
  it("treats an undefined section as OTHER", () => {
    expect(sectionRank(undefined)).toBe(sectionRank("OTHER"));
  });
  it("de-underscores labels and uppercases each word's first letter", () => {
    expect(sectionLabel("SALES_COMPARISON")).toBe("SALES COMPARISON");
    expect(sectionLabel(undefined)).toBe("OTHER");
  });
});

describe("rule grouping", () => {
  it("keys a group by section + ruleId", () => {
    expect(ruleGroupKey(rule({ ruleId: "SCA-4", section: "SALES_COMPARISON" })))
      .toBe("SALES_COMPARISON::SCA-4");
  });
  it("only groups SCA rules that appear more than once", () => {
    expect(shouldGroupRule(rule({ ruleId: "SCA-4" }), 3)).toBe(true);
    expect(shouldGroupRule(rule({ ruleId: "SCA-4" }), 1)).toBe(false);
    expect(shouldGroupRule(rule({ ruleId: "S-1" }), 3)).toBe(false);
  });
  it("uses the configured friendly label when available", () => {
    expect(groupLabelForRule(rule({ ruleId: "SCA-4" }))).toBe("Proximity");
  });
  it("falls back to a generic label when the name just echoes the id", () => {
    expect(groupLabelForRule(rule({ ruleId: "SCA-99", ruleName: "SCA-99" })))
      .toBe("Comparable check");
  });
});

describe("isNotApplicable", () => {
  it("is true for the not_applicable status, case-insensitively", () => {
    expect(isNotApplicable(rule({ status: "NOT_APPLICABLE" }))).toBe(true);
    expect(isNotApplicable(rule({ status: "FAIL" }))).toBe(false);
  });
});

describe("focusForRule", () => {
  it("marks the rule unlocated when no page is known", () => {
    const f = focusForRule(rule({ ruleId: "S-1" }));
    expect(f.located).toBe(false);
    expect(f.page).toBe(1);
    expect(f.bbox).toBeNull();
  });
  it("returns a real bbox only when it has positive area", () => {
    const f = focusForRule(rule({ pdfPage: 3, bboxX: 1, bboxY: 2, bboxW: 4, bboxH: 5 }));
    expect(f.located).toBe(true);
    expect(f.page).toBe(3);
    expect(f.bbox).toEqual({ x: 1, y: 2, w: 4, h: 5 });
  });
  it("treats a zero-area box as page-only (no highlight)", () => {
    const f = focusForRule(rule({ pdfPage: 3, bboxX: 0, bboxY: 0, bboxW: 0, bboxH: 0 }));
    expect(f.located).toBe(true);
    expect(f.bbox).toBeNull();
  });
});

describe("safeReviewerQueuePath", () => {
  it("defaults to the queue when empty", () => {
    expect(safeReviewerQueuePath(null)).toBe("/reviewer/queue");
  });
  it("allows decoded reviewer-queue paths through", () => {
    expect(safeReviewerQueuePath(encodeURIComponent("/reviewer/queue?view=failures")))
      .toBe("/reviewer/queue?view=failures");
  });
  it("rejects any other destination (open-redirect guard)", () => {
    expect(safeReviewerQueuePath("/admin")).toBe("/reviewer/queue");
    expect(safeReviewerQueuePath("https://evil.test")).toBe("/reviewer/queue");
  });
});
