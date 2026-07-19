/**
 * Pipeline-stage display names.
 *
 * The design point this protects: the label is derived from the STABLE backend
 * key at render time, so a wording change updates historical rows too with no
 * database backfill. The persisted label is a fallback for unknown keys ONLY —
 * if that precedence ever inverts, old rows silently freeze at old wording.
 */
import { describe, expect, it } from "vitest";

import { STAGE_LABELS, stageLabel } from "@/lib/stageLabels";

describe("stageLabel", () => {
  it("maps every known stage key", () => {
    for (const [key, label] of Object.entries(STAGE_LABELS)) {
      expect(stageLabel(key)).toBe(label);
    }
  });

  it("prefers the mapped label OVER a stale stored one", () => {
    // This is the whole reason the map exists — a stored snapshot must never win.
    expect(stageLabel("rules", "Old Wording From 2024")).toBe("Running quality checks");
  });

  it("uses the stored label only when the key is unknown", () => {
    expect(stageLabel("brand_new_stage", "Doing the new thing")).toBe("Doing the new thing");
  });

  it("humanizes an unknown key when there is no stored label", () => {
    expect(stageLabel("flood_cert_read")).toBe("Flood Cert Read");
  });

  it("ignores a blank stored label and humanizes instead", () => {
    expect(stageLabel("some_stage", "   ")).toBe("Some Stage");
  });

  it("renders an em dash rather than nothing when there is no key at all", () => {
    expect(stageLabel()).toBe("—");
    expect(stageLabel(null)).toBe("—");
    expect(stageLabel("")).toBe("—");
  });

  it("covers the stages the backend actually emits", () => {
    // Guards against a key being dropped from the map during a refactor.
    for (const key of ["extract_appraisal", "extract_engagement", "extract_contract",
                       "sca_grid", "sca_llm", "subject_llm", "sketch", "photos",
                       "locate", "rules", "extraction", "done"]) {
      expect(STAGE_LABELS[key], `missing stage key: ${key}`).toBeTruthy();
    }
  });
});
