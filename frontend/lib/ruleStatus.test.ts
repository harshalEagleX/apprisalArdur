import { describe, it, expect } from "vitest";
import { ruleStatus, isReviewLikeStatus } from "@/lib/ruleStatus";

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

describe("isReviewLikeStatus — unknown input", () => {
  it("treats an unrecognised status as not needing review", () => {
    expect(isReviewLikeStatus("nonsense")).toBe(false);
  });
  it("handles a nullish status without throwing", () => {
    expect(isReviewLikeStatus(undefined as unknown as string)).toBe(false);
  });
});
