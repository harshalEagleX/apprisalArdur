/**
 * Rule finding / rejection language — the SINGLE source of truth for the human
 * sentence shown when a rule fails, used by both the active review card and the
 * submitted summary so the same rule never reads differently between screens.
 *
 * Contract (stable from development through production):
 *   1. If the Python rule engine supplied `rejectionText`, show it verbatim.
 *      The engine is the authoritative author of rule language; the frontend
 *      must never paraphrase or compete with it.
 *   2. Only when the engine has NOT supplied text does a development fallback
 *      run — and it logs which rule id is missing engine text, so the warning
 *      log becomes the task list for the Python team.
 *
 * Path to production: as the engine fills `rejectionText` for every FAIL-capable
 * rule, the fallback simply stops being reached (phase 2). In production the
 * fallback can be deleted outright (phase 3) with no other change — every caller
 * already reads the engine field first.
 */

import type { QCRuleResult } from "@/lib/api";
import { parseEvidence } from "@/lib/ruleEvidence";

const isDev = process.env.NODE_ENV !== "production";
const warnedRuleIds = new Set<string>();

function warnMissingEngineText(rule: QCRuleResult): void {
  if (!isDev) return;
  const id = rule.ruleId ?? "(unknown)";
  if (warnedRuleIds.has(id)) return;
  warnedRuleIds.add(id);
  // This list IS the backlog: every rule logged here needs rejection_text
  // implemented in the Python engine. Do not silence it by changing the chain.
  console.warn(
    `[qc] Rule ${id} has no engine-supplied rejectionText — using the frontend ` +
      `development fallback. Implement rejection_text for this rule in the Python engine.`
  );
}

/**
 * Name the documents this rule drew values from, lower-cased for mid-sentence
 * use. Derived from the rule's evidence so the wording never claims "engagement
 * letter" when the value actually came from the contract.
 */
export function buildSourceLabel(rule: QCRuleResult): string {
  const labels = Array.from(new Set(parseEvidence(rule).map(s => s.label.toLowerCase())));
  if (labels.length === 0) return "";
  if (labels.length === 1) return `the ${labels[0]}`;
  const last = labels[labels.length - 1];
  return `the ${labels.slice(0, -1).join(", ")} and the ${last}`;
}

// Generic, section-level framing around the engine's `message`. This is a
// DEVELOPMENT placeholder only — it does not invent rule-specific findings, it
// wraps the engine message so an incomplete rule still reads as a sentence. Any
// rule-specific phrasing (e.g. refinance contract-section handling) belongs in
// the Python engine, not here.
function sectionFallback(rule: QCRuleResult): string {
  const prefix = (rule.ruleId ?? "").split("-")[0].toUpperCase();
  const page = rule.pdfPage ? ` (page ${rule.pdfPage})` : "";
  const sourceLabel = buildSourceLabel(rule);
  const message = rule.message ?? "";

  switch (prefix) {
    case "S":
      return `Subject property information does not match. ${message} Please verify ${sourceLabel}${page} and correct the discrepancy.`;
    case "C":
      return `Contract section issue detected. ${message} Please review the contract documentation${page} and ensure all required fields are completed accurately.`;
    case "N":
      return `Neighborhood analysis issue. ${message} The appraisal report${page} requires correction or additional supporting commentary.`;
    case "SCA":
      return `Sales comparison issue. ${message} Please review the comparable sales in the appraisal report${page}.`;
    case "FHA":
      return `FHA requirement not met. ${message} Please review the appraisal report${page} to ensure FHA compliance.`;
    case "COM":
      return `Commentary is insufficient. ${message} The appraisal report${page} must provide specific, property-referenced analysis rather than generic language.`;
    case "ADD":
      return `Addendum issue detected. ${message} Please review ${sourceLabel}${page} for the required information.`;
    default:
      return `${rule.ruleName}: ${message}${sourceLabel ? ` Please verify ${sourceLabel}${page}.` : ""}`;
  }
}

export interface RuleLanguage {
  text: string;
  /** true when the engine supplied no rejectionText and the dev fallback ran. */
  isFallback: boolean;
}

/**
 * The rejection sentence for a FAIL rule. Engine `rejectionText` wins; the
 * development fallback runs only when it is absent (and logs the gap).
 */
export function failRejectionLanguage(rule: QCRuleResult): RuleLanguage {
  const engine = rule.rejectionText?.trim();
  if (engine) return { text: engine, isFallback: false };
  warnMissingEngineText(rule);
  return { text: sectionFallback(rule), isFallback: true };
}
