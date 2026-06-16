/**
 * Pipeline-stage display names — the SINGLE source of truth for how a pipeline
 * stage is shown to users, keyed by the STABLE stage key the backend emits
 * (DocStatStage.stage).
 *
 * Why derive from the key at render time: the backend also persists a label
 * snapshot (doc_stat_stage.label) captured when the document was processed. If the
 * UI rendered that stored string, every wording change would need a database
 * backfill and historical rows would drift. By mapping the stable key -> label
 * here, a wording change updates EVERY view — historical and new — instantly, with
 * no backfill. The stored label is used only as a fallback for a key this map does
 * not yet know.
 *
 * Keep the keys in step with the backend stage keys in
 * ocr-service/app/qc/transaction.py (_emit) — those are the contract.
 */
export const STAGE_LABELS: Record<string, string> = {
  extract_appraisal: "Reading the appraisal report",
  sca_grid: "Comparable sales grid",
  sca_llm: "Comparable sales analysis",
  subject_llm: "Subject & contract details",
  sketch: "Floor plan & living area",
  photos: "Property photographs",
  locate: "Preparing review highlights",
  extract_engagement: "Reading the engagement letter",
  extract_contract: "Reading the sales contract",
  rules: "Running quality checks",
  extraction: "Reading the documents",
  done: "Finishing up",
};

/** Humanize an unknown key (snake_case -> Title Case) so nothing renders raw. */
function humanize(key: string): string {
  return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * Display name for a pipeline stage.
 * @param stageKey   the stable key from DocStatStage.stage
 * @param storedLabel optional persisted label, used only when the key is unknown
 */
export function stageLabel(stageKey?: string | null, storedLabel?: string | null): string {
  if (stageKey && STAGE_LABELS[stageKey]) return STAGE_LABELS[stageKey];
  if (storedLabel && storedLabel.trim()) return storedLabel;
  return stageKey ? humanize(stageKey) : "—";
}
