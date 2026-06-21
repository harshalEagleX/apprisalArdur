import { describe, it, expect } from "vitest";
import { ruleStatus, isReviewLikeStatus, statusStyle, severityStyle, STATUS_STYLE, SEV_STYLE } from "@/lib/ruleStatus";

describe("ruleStatus", () => {
  it("lowercases ordinary statuses", () => {
    expect(ruleStatus("FAIL")).toBe("fail");
  });
  it("preserves the MANUAL_PASS sentinel in upper case", () => {
    expect(ruleStatus("manual_pass")).toBe("MANUAL_PASS");
  });
  it("handles a nullish status without throwing", () => {
    expect(ruleStatus(undefined as unknown as string)).toBe("");
  });
});

describe("isReviewLikeStatus", () => {
  it("is true for statuses needing reviewer action", () => {
    expect(isReviewLikeStatus("VERIFY")).toBe(true);
    expect(isReviewLikeStatus("cross_doc_mismatch")).toBe(true);
  });
  it("is false for terminal pass/fail", () => {
    expect(isReviewLikeStatus("pass")).toBe(false);
    expect(isReviewLikeStatus("fail")).toBe(false);
  });
});

describe("style fallbacks", () => {
  it("falls back to the verify style for unknown statuses", () => {
    expect(statusStyle("nonsense")).toBe(STATUS_STYLE.verify);
  });
  it("falls back to STANDARD severity for unknown/nullish severity", () => {
    expect(severityStyle(null)).toBe(SEV_STYLE.STANDARD);
    expect(severityStyle("nonsense")).toBe(SEV_STYLE.STANDARD);
  });
});
