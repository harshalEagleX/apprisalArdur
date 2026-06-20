/**
 * Single source of truth for QC rule status + severity presentation.
 *
 * Rule status and severity drive colour, review-routing, and the blocking
 * acknowledgment gate in several places (RuleCard, the verify page, future
 * dashboards). Keeping the normaliser, the review-like set, and the style maps
 * here — rather than copied per component — guarantees they can never drift
 * apart (e.g. a new "hold" style added in one place but not the other).
 */

/** Visual treatment per normalised status. */
export interface StatusStyle {
  border: string;
  bg: string;
  text: string;
}

export const STATUS_STYLE: Record<string, StatusStyle> = {
  pass:               { border: "border-green-500/20", bg: "bg-green-950/10", text: "text-green-200" },
  fail:               { border: "border-red-500/20",   bg: "bg-red-950/10",   text: "text-red-200" },
  verify:             { border: "border-amber-500/20", bg: "bg-amber-950/5",  text: "text-amber-200" },
  review:             { border: "border-amber-500/20", bg: "bg-amber-950/10", text: "text-amber-200" },
  extraction_failed:  { border: "border-amber-500/20", bg: "bg-amber-950/10", text: "text-amber-200" },
  ocr_low_confidence: { border: "border-amber-500/20", bg: "bg-amber-950/10", text: "text-amber-200" },
  source_missing:     { border: "border-amber-500/20", bg: "bg-amber-950/10", text: "text-amber-200" },
  system_error:       { border: "border-red-500/20",   bg: "bg-red-950/10",   text: "text-red-200" },
  cross_doc_mismatch: { border: "border-red-500/20",   bg: "bg-red-950/10",   text: "text-red-200" },
  hold:               { border: "border-red-500/30",   bg: "bg-red-950/15",   text: "text-red-200" },
  skipped:            { border: "border-white/8",      bg: "bg-white/[0.03]", text: "text-slate-400" },
  not_executed:       { border: "border-white/8",      bg: "bg-white/[0.03]", text: "text-slate-400" },
  not_applicable:     { border: "border-white/8",      bg: "bg-white/[0.03]", text: "text-slate-400" },
  MANUAL_PASS:        { border: "border-green-500/20", bg: "bg-green-950/10", text: "text-green-200" },
};

export const SEV_STYLE: Record<string, string> = {
  BLOCKING: "bg-red-950/50 border-red-500/25 text-red-200",
  STANDARD: "bg-[#161B22] border-white/10 text-slate-400",
  ADVISORY: "bg-[#161B22]/70 border-white/10 text-slate-500",
};

/**
 * Statuses that require reviewer attention (not a clean pass/fail-only set).
 * A single canonical list so "what counts as needing review" is defined once.
 */
export const REVIEW_LIKE_STATUSES: readonly string[] = [
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

/** Style for a status, falling back to the neutral "verify" treatment. */
export function statusStyle(status: string): StatusStyle {
  return STATUS_STYLE[ruleStatus(status)] ?? STATUS_STYLE.verify;
}

/** Style for a severity, falling back to STANDARD. */
export function severityStyle(severity: string | null | undefined): string {
  return SEV_STYLE[severity ?? "STANDARD"] ?? SEV_STYLE.STANDARD;
}
