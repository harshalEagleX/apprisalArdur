/**
 * Single source of truth for QC rule status semantics.
 *
 * This module owns *meaning*, not colour: how a raw backend status string is
 * normalised, and which statuses count as "needs a reviewer". Presentation lives
 * with the components that render it (StatusBadge, FindingRow) — the style maps
 * that used to sit here had no importers and had already drifted from both.
 */

/**
 * Statuses that require reviewer attention (not a clean pass/fail-only set).
 * A single canonical list so "what counts as needing review" is defined once.
 */
const REVIEW_LIKE_STATUSES: readonly string[] = [
  "verify",
  "review",
  "hold",
  "extraction_failed",
  "ocr_low_confidence",
  "source_missing",
  "system_error",
  "cross_doc_mismatch",
] as const;

/**
 * Normalise a raw status string: lowercase, except the sentinel "MANUAL_PASS"
 * which is preserved in upper case because it keys its own style + semantics.
 */
export function ruleStatus(status: string): string {
  const normalized = (status ?? "").toLowerCase();
  return normalized === "manual_pass" ? "MANUAL_PASS" : normalized;
}

/** True when the (raw or normalised) status needs reviewer action. */
export function isReviewLikeStatus(status: string): boolean {
  return REVIEW_LIKE_STATUSES.includes(ruleStatus(status));
}

