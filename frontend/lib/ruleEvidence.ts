/**
 * Rule evidence interpretation — turns the QC pipeline's per-rule output into a
 * description the reviewer UI can render *honestly*.
 *
 * The pipeline emits, per rule, a document-tagged evidence list:
 *   ["appraisal: 123 Main St (95%, p4)", "contract: 123 Main Street (90%)"]
 * Each entry says WHICH document a value came from. Some rules carry two
 * documents (a cross-document comparison), some carry one (a presence / format
 * check on a single document), and some carry none (the value could not be
 * located). The UI must reflect exactly that — never imply a comparison that did
 * not happen, and never mislabel which document a value came from.
 *
 * Nothing here is rule-specific or hardcoded per rule id: the document a value
 * belongs to and whether a comparison occurred are derived from the evidence the
 * pipeline produced. The only static table is the human-readable name for each
 * document token, and unknown tokens fall back to a title-cased version so new
 * document types render sensibly without a code change.
 */

import type { QCRuleResult } from "@/lib/api";

// Presentation translation only (P-10: translate raw signals for the reviewer).
const DOC_LABELS: Record<string, string> = {
  appraisal: "Appraisal report",
  subject: "Appraisal report",
  report: "Appraisal report",
  engagement: "Engagement letter",
  order: "Order form",
  contract: "Sales contract",
  sales_contract: "Sales contract",
};

export function documentLabel(token: string): string {
  const key = token.trim().toLowerCase().replace(/\s+/g, "_");
  if (DOC_LABELS[key]) return DOC_LABELS[key];
  // Unknown document token — present it readably instead of dropping it.
  return token
    .trim()
    .replace(/_/g, " ")
    .replace(/\b\w/g, c => c.toUpperCase());
}

/**
 * The Java backend substitutes sentinel tokens (e.g. `__NO_APPRAISAL_VALUE__`)
 * when a rule has no value for a slot. Treat any such token as empty so the UI
 * shows nothing rather than the raw placeholder. Matches both the current
 * `__NO_..._VALUE__` form and the older `__NO_..._VALUE` form defensively.
 */
export function cleanRuleValue(v?: string | null): string | undefined {
  if (!v) return undefined;
  const trimmed = v.trim();
  if (/^__NO_[A-Z0-9_]+?_VALUE__?$/.test(trimmed)) return undefined;
  return trimmed.length ? trimmed : undefined;
}

export interface EvidenceSource {
  document: string; // raw token: appraisal | engagement | contract | ...
  label: string; // human-readable document name
  comparable?: string; // "Comp 1" | "Subject" — which property this value is for
  value: string;
  confidence?: number; // 0..1
  page?: number;
  method?: string; // how the value was extracted, when the pipeline reports it
}

// "<doc>: <value> (<conf>%, p<page>)" — page is optional; value may itself
// contain colons/parens, so the trailing "(NN%[, pN])" is anchored at the end.
const EVIDENCE_RE = /^\s*([^:]+?)\s*:\s*([\s\S]*?)\s*\((\d+)%(?:,\s*p(\d+))?\)\s*$/;

function parseEvidenceEntry(entry: string): EvidenceSource | null {
  if (!entry || typeof entry !== "string") return null;
  const m = entry.match(EVIDENCE_RE);
  if (m) {
    const [, doc, value, conf, page] = m;
    const v = cleanRuleValue(value);
    if (!v) return null;
    return {
      document: doc.trim().toLowerCase(),
      label: documentLabel(doc),
      value: v,
      confidence: Number(conf) / 100,
      page: page ? Number(page) : undefined,
    };
  }
  // Fallback: "<doc>: <value>" with no trailing confidence/page meta.
  const colon = entry.indexOf(": ");
  if (colon > 0) {
    const v = cleanRuleValue(entry.slice(colon + 2));
    if (!v) return null;
    const doc = entry.slice(0, colon);
    return { document: doc.trim().toLowerCase(), label: documentLabel(doc), value: v };
  }
  return null;
}

// One evidence element may arrive as a structured object (current API), a
// preformatted string (legacy rows), or — defensively — anything else.
function coerceSource(entry: unknown): EvidenceSource | null {
  if (typeof entry === "string") return parseEvidenceEntry(entry);
  if (entry && typeof entry === "object") {
    const o = entry as Record<string, unknown>;
    const doc = typeof o.document === "string" ? o.document : "";
    const rawValue =
      typeof o.value === "string" ? o.value : o.value == null ? undefined : String(o.value);
    const value = cleanRuleValue(rawValue);
    if (!doc || !value) return null;
    return {
      document: doc.trim().toLowerCase(),
      label: documentLabel(doc),
      comparable: typeof o.comparable === "string" && o.comparable ? o.comparable : undefined,
      value,
      confidence: typeof o.confidence === "number" ? o.confidence : undefined,
      page: typeof o.page === "number" ? o.page : undefined,
      method: typeof o.method === "string" ? o.method : undefined,
    };
  }
  return null;
}

/**
 * Resolve the rule's evidence into document-tagged sources. Prefers the
 * structured evidence list (which preserves the true source document of every
 * value); only when that is absent does it fall back to the flattened
 * appraisal/engagement value fields — and even then it never claims the second
 * value is "engagement" vs "contract" (the pipeline collapses both into one
 * slot), labelling it generically so the UI cannot mislead the reviewer.
 */
export function parseEvidence(rule: QCRuleResult): EvidenceSource[] {
  const raw = rule.evidence as unknown;
  let entries: unknown[] = [];
  if (Array.isArray(raw)) {
    entries = raw;
  } else if (typeof raw === "string" && raw.trim()) {
    // Legacy: evidence delivered as a JSON-string blob rather than an array.
    try {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) entries = parsed;
    } catch {
      /* not JSON — leave entries empty and use the flattened fallback below */
    }
  }

  const parsed = entries
    .map(coerceSource)
    .filter((s): s is EvidenceSource => s != null);

  // De-dup identical entries so repeated evidence doesn't double-render — but key
  // on the comparable too, so two different comps that happen to share a value
  // (e.g. two comps both "6000 sf") are NOT collapsed into one.
  const seen = new Set<string>();
  const sources = parsed.filter(s => {
    const k = `${s.comparable ?? ""}::${s.document}::${s.value}`;
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  });
  if (sources.length > 0) return sources;

  // Fallback: flattened value fields (used when no structured evidence exists).
  const fb: EvidenceSource[] = [];
  const appraisal = cleanRuleValue(rule.appraisalValue) ?? cleanRuleValue(rule.extractedValue ?? undefined);
  if (appraisal) {
    fb.push({ document: "appraisal", label: documentLabel("appraisal"), value: appraisal });
  }
  const supporting = cleanRuleValue(rule.engagementValue) ?? cleanRuleValue(rule.expectedValue ?? undefined);
  if (supporting) {
    // Could be engagement OR contract — the flattened field can't say which.
    fb.push({ document: "supporting", label: "Supporting document", value: supporting });
  }
  return fb;
}

/**
 * Flatten a rule's evidence into a plain searchable string (document + value
 * per source). Used where a free-text search corpus is built over rules, since
 * `rule.evidence` is now structured rather than a string.
 */
export function evidenceText(rule: QCRuleResult): string {
  return parseEvidence(rule)
    .map(s => `${s.document} ${s.value}`)
    .join(" ");
}

export type EvidenceMode = "compare" | "single" | "none";

export interface EvidenceModel {
  mode: EvidenceMode;
  sources: EvidenceSource[];
  /** Plain-language description of what this rule looked at. */
  headline: string;
}

/**
 * Decide how to present a rule's evidence:
 *   - "compare" — two or more values from documents that were checked against
 *     each other (e.g. Appraisal report ↔ Sales contract).
 *   - "single"  — one value from one document (a presence/format check); there
 *     is nothing to compare it against.
 *   - "none"    — no value located; only the rule message is meaningful.
 */
export function buildEvidenceModel(rule: QCRuleResult): EvidenceModel {
  const sources = parseEvidence(rule);
  if (sources.length === 0) {
    return { mode: "none", sources, headline: "" };
  }
  if (sources.length === 1) {
    return {
      mode: "single",
      sources,
      headline: `${sources[0].label} — single-document check, nothing to compare`,
    };
  }
  const labels = Array.from(new Set(sources.map(s => s.label)));
  const headline =
    labels.length >= 2
      ? `Comparing ${labels.join(" ↔ ")}`
      : `Comparing values within ${labels[0]}`;
  return { mode: "compare", sources, headline };
}
