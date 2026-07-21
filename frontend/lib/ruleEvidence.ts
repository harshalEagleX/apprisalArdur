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
  // `__?` required at least one trailing underscore, so the older bare
  // `__NO_ENGAGEMENT_VALUE` form this function documents as handled actually
  // slipped through and rendered the raw placeholder to the reviewer.
  // `_{0,2}` accepts the bare, single- and double-underscore forms.
  if (/^__NO_[A-Z0-9_]+?_VALUE_{0,2}$/.test(trimmed)) return undefined;
  return trimmed.length ? trimmed : undefined;
}

export interface EvidenceSource {
  document: string; // raw token: appraisal | engagement | contract | ...
  label: string; // human-readable document name
  /** Humanized bound-field name ("Sale price", "Comp 2 GLA") — SHALqc rows only. */
  fieldLabel?: string;
  comparable?: string; // "Comp 1" | "Subject" — which property this value is for
  value: string;
  /** The verbatim snippet the judge cited, when it differs from the value. */
  quote?: string;
  confidence?: number; // 0..1
  page?: number;
  /** Normalized {x,y,w,h} page fractions for click-to-locate, when available. */
  bbox?: { x: number; y: number; w: number; h: number } | null;
  method?: string; // provenance badge (XML / Report / Order form / AI-read), when reported
}

/**
 * "comp_2_sale_price" → "Comp 2 sale price". Presentation only — the raw label
 * stays the identifier everywhere else. Tokens of ≤3 letters render uppercased
 * (gla → GLA, apn → APN) since they are acronyms on the form.
 */
export function humanizeFieldLabel(raw: string): string {
  const words = raw.trim().split(/_+/).filter(Boolean).map(w =>
    /^[a-z]{1,3}$/.test(w) && !/^(per|of|to|the|and|for|in|on)$/.test(w) ? w.toUpperCase() : w
  );
  const joined = words.join(" ");
  return joined.charAt(0).toUpperCase() + joined.slice(1);
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

// One evidence element may arrive as a SHALqc-native row (label + source +
// page/bbox), a structured document-tagged object (older API), a preformatted
// string (legacy rows), or — defensively — anything else.
function coerceSource(entry: unknown): EvidenceSource | null {
  if (typeof entry === "string") return parseEvidenceEntry(entry);
  if (!entry || typeof entry !== "object") return null;
  const o = entry as Record<string, unknown>;
  const rawValue =
    typeof o.value === "string" ? o.value : o.value == null ? undefined : String(o.value);
  const value = cleanRuleValue(rawValue);
  if (!value) return null;

  const doc = typeof o.document === "string" ? o.document : "";
  if (doc) {
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

  // SHALqc-native evidence row: {label, value, quote?, page?, bbox?, source,
  // source_badge}. The bound-label + provenance say what the value IS and where
  // it came from — without this branch the row rendered as a bare value with an
  // empty header.
  const fieldRaw = typeof o.label === "string" ? o.label.trim() : "";
  if (!fieldRaw) return null;
  const srcTok = typeof o.source === "string" ? o.source.toLowerCase() : "";
  const document = srcTok.includes("engagement") ? "engagement"
    : srcTok.includes("contract") ? "contract"
    : "appraisal";
  const b = o.bbox as Record<string, unknown> | null | undefined;
  const bbox =
    b && typeof b === "object" &&
    typeof b.x === "number" && typeof b.y === "number" &&
    typeof b.w === "number" && typeof b.h === "number" && b.w > 0 && b.h > 0
      ? { x: b.x, y: b.y, w: b.w, h: b.h }
      : null;
  const quote = typeof o.quote === "string" && o.quote.trim() ? o.quote.trim() : undefined;
  return {
    document,
    label: documentLabel(document),
    fieldLabel: humanizeFieldLabel(fieldRaw),
    value,
    quote: quote !== value ? quote : undefined,
    confidence: typeof o.confidence === "number" ? o.confidence : undefined,
    page: typeof o.page === "number" && o.page > 0 ? o.page : undefined,
    bbox,
    method: typeof o.source_badge === "string" && o.source_badge ? o.source_badge : undefined,
  };
}

/**
 * Coerce a rule-detail `sources` array (any of the three shapes) into renderable
 * evidence sources — the expanded finding row's label+value cards.
 */
export function coerceEvidenceSources(entries: unknown[] | null | undefined): EvidenceSource[] {
  return (entries ?? [])
    .map(coerceSource)
    .filter((s): s is EvidenceSource => s != null);
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
