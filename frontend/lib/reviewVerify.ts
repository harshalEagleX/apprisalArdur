/**
 * Pure domain logic for the reviewer "verify" surface.
 *
 * This was previously declared inline inside `app/reviewer/verify/[id]/page.tsx`,
 * mixing ~130 lines of non-JSX logic into the component file. Extracting it here
 * keeps the page presentational and makes this logic unit-testable.
 */
import type { QCRuleResult } from "@/lib/api";

export type Decision = "PASS" | "FAIL";

// "attention" = the default working view: failures + items needing review, passes hidden.
// Passes are opt-in (the "Pass" tab) — they almost never need reviewer action and only add noise.
export type Filter = "attention" | "all" | "fail" | "verify" | "pass";
export const FILTERS: Filter[] = ["attention", "fail", "verify", "pass", "all"];

export const ZOOM_MIN = 0.6;
export const ZOOM_MAX = 1.8;
export const ZOOM_STEP = 0.1;
export const VIEWER_SCROLL_KEYS = new Set(["ArrowDown", "ArrowUp", "ArrowRight", "ArrowLeft", "PageDown", "PageUp"]);

export function clampZoom(value: number): number {
  return Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, Math.round(value * 10) / 10));
}

export type RuleFocus = {
  ruleId: string; page: number; documentType: string; note: string;
  bbox?: { x: number; y: number; w: number; h: number } | null;
  located: boolean;
};
export type ReviewProgress = { pending: number; canSubmit: boolean; totalToVerify: number };
export type DecisionEvent = {
  ruleResultId: number; decision: Decision; savedAt: string; status: string;
  reviewerVerified?: boolean | null; overridePending?: boolean; reviewerComment?: string;
};

// Reviewer rule groups, in report order, with a friendly label.
const SECTION_ORDER = [
  "SUBJECT", "CONTRACT", "NEIGHBORHOOD", "SITE", "IMPROVEMENTS",
  "SALES_COMPARISON", "RECONCILIATION", "COST_APPROACH", "INCOME",
  "SIGNATURE", "ADDENDUM", "PHOTOS", "SKETCH", "MAPS", "DOCUMENTS",
  "FHA", "USDA", "GLOBAL", "OTHER",
];
export function sectionRank(s?: string): number {
  const i = SECTION_ORDER.indexOf(s ?? "OTHER");
  return i < 0 ? SECTION_ORDER.length : i;
}
export function sectionLabel(s?: string): string {
  return (s ?? "OTHER").replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
}

const SCA_GROUP_LABELS: Record<string, string> = {
  "SCA-3": "Comp address",
  "SCA-4": "Proximity",
  "SCA-5": "Data source",
  "SCA-6": "Verification source",
  "SCA-7": "Concession adjustment",
  "SCA-8": "Date of sale",
  "SCA-9": "Location",
  "SCA-10": "Property rights",
  "SCA-11": "Site size",
  "SCA-12": "View",
  "SCA-13": "Design / style",
  "SCA-14": "Quality rating",
  "SCA-16": "Condition rating",
  "SCA-17": "Room count & GLA",
  "SCA-18": "Basement",
  "SCA-19": "Functional utility",
  "SCA-20": "Heating / cooling",
  "SCA-21": "Garage / carport",
  "SCA-22": "Porch/patio/deck",
  "SCA-23": "Listing adjustment",
  "SCA-24": "Unique design",
  "SCA-25": "New construction comp",
  "SCA-26": "GLA bracketing",
  "SCA-NET": "Net adjustment %",
  "SCA-GROSS": "Gross adjustment %",
  "SCA-ZF": "Zero-difference adjustment",
  "SCA-AC": "Adjustment consistency",
  "SCA-DC": "Date currency",
  "SCA-FLIP": "Comp resale window",
  "SCA-PR": "Sale price bracket",
};

export function ruleGroupKey(rule: QCRuleResult): string {
  return `${rule.section ?? "OTHER"}::${rule.ruleId}`;
}

export function shouldGroupRule(rule: QCRuleResult, count: number): boolean {
  return count > 1 && rule.ruleId.toUpperCase().startsWith("SCA-");
}

export function groupLabelForRule(rule: QCRuleResult): string {
  const id = rule.ruleId.toUpperCase();
  const configured = SCA_GROUP_LABELS[id];
  if (configured) return configured;
  const name = rule.ruleName?.trim();
  if (!name || name.toUpperCase().endsWith(id)) return "Comparable check";
  return name.replace(/^Sales Comparison\s+[—-]\s*/i, "");
}

export type RuleRenderItem = {
  key: string;
  section?: string;
  rules: QCRuleResult[];
  grouped: boolean;
  label?: string;   // override group title (e.g. a whole section collapsed as N/A)
};

export function isNotApplicable(rule: QCRuleResult): boolean {
  return rule.status?.toLowerCase() === "not_applicable";
}

export function focusForRule(rule: QCRuleResult): RuleFocus {
  const backendPage = typeof rule.pdfPage === "number" && rule.pdfPage > 0 ? rule.pdfPage : null;
  // A box is real only when all four are numbers AND it has positive area. The
  // backend stores 0,0,0,0 to mean "page known, exact box unavailable" (the
  // value could not be located precisely), which must scroll to the page
  // WITHOUT drawing a zero-size highlight — per the MIRA page-level-only rule.
  const hasBox =
    [rule.bboxX, rule.bboxY, rule.bboxW, rule.bboxH].every(v => typeof v === "number") &&
    (rule.bboxW as number) > 0 && (rule.bboxH as number) > 0;
  if (!backendPage) {
    return { ruleId: rule.ruleId, page: 1, documentType: "APPRAISAL", note: "Location not yet extracted", bbox: null, located: false };
  }
  return {
    ruleId: rule.ruleId, page: backendPage, documentType: "APPRAISAL",
    note: hasBox ? "OCR evidence location" : "Page located; field box unavailable",
    bbox: hasBox ? { x: rule.bboxX as number, y: rule.bboxY as number, w: rule.bboxW as number, h: rule.bboxH as number } : null,
    located: true,
  };
}

export function safeReviewerQueuePath(value: string | null): string {
  if (!value) return "/reviewer/queue";
  try {
    const decoded = decodeURIComponent(value);
    return decoded.startsWith("/reviewer/queue") ? decoded : "/reviewer/queue";
  } catch {
    return value.startsWith("/reviewer/queue") ? value : "/reviewer/queue";
  }
}
