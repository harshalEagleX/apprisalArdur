# Bbox provenance + version-namespaced field registry — phased plan

Status: **design, not yet built.** Everything else from the 2026-07-16 cross-read
audit (F1–F7, F9–F11, F2, and the §4 findings-not-verdicts role contract) is
shipped and tested (211 green). This document is the remaining greenfield piece:
per-value provenance, caption/cell-region anchoring (kills **F8**), and a
version-namespaced field registry + vendor adapter. It touches the extraction
core, so it gets a spec and its own acceptance gates before code.

## What already exists (do not rebuild)

| Piece | Where | State |
|---|---|---|
| Location quality L1–L5 (exact/region/page/none) | `app/locate/back_locator.py` | Built. **L3 "region" is stubbed** — the docstring says it "needs the template map". That template map is Phase 2 below. |
| Per-field bbox `{x,y,w,h}` + page | `ExtractedField.bbox/.page` (`app/extraction/result.py`) | Built; PDF/grid/checkbox witnesses carry it, XML values get located by the back-locator. |
| Evidence rows with page/bbox on every card | `packet_v2._value_entry`, `validate_v2._located_evidence`, `run._card` | Built. Frontend auto-scroll already reads these. |
| Form-type detection | `xml_extractor._FORM_TYPE_MAP` (`AppraisalFormType` → `form_type` field) | Built; `form_type` is an extracted field (not schema-validated). Covers 1004/1073/1025/1004c/1004d/2055/va. |
| Plausibility gate (suppress → MISSING) | `extraction/plausibility.py` | Built; F2 (person-name) + F7 (caption `(s)`) guards just added. This is where "no provenance → null" already lands. |

**Missing:** `source_path` (XPath) + `anchor_text` on provenance; the L3 cell-region
template map; column anchoring for the comp grid (F8); a version-namespaced
registry keyed by `(uad_version, form_type, field_id)`; a vendor adapter.

## Phase 0 — provenance data contract (additive, low risk)

Thread the two missing provenance fields end-to-end. No behavior change; enables
everything after.

- `ExtractedField`: add `source_path: Optional[str]` (XML XPath the value was read
  from — the xml_extractor already walks the tree, capture the path) and
  `anchor_text: Optional[str]` (the caption token the back-locator matched near).
- `packet_v2._value_entry`: pass both into the value entry.
- `run._card` / `validate_v2._located_evidence`: include both in each evidence row.
- Java `ShalqcResponseMapper` + DTO + frontend chip: render `source_path` on hover.
- **Gate:** every XML-sourced value on a card carries `source_path`; no regression
  in existing evidence tests.

## Phase 1 — version-namespaced field registry (config asset + loader)

The registry is the L2 layer from the architecture note. Key by
`(uad_version, form_type, field_id)`, **never bare field name**, so 2.6 and 3.6
orders coexist through the 2026-11-02 → 2027-05-03 transition.

- New `config/field_registry/uad26/<FORM>.yaml` (start with FNM1004; the 5-XML
  sample is all 1004 except one 1004c). Each field: `{canonical_label, urar_page,
  urar_section, cell_region (template bbox, fractional), caption_text (stop-text),
  datatype, uad_enum_ref, xml_reliability_per_vendor}`.
- New `app/registry/loader.py`: `field(uad_version, form_type, field_id)`; falls
  back to a generic 2.6GSE slice for an unknown vendor; **unknown form_type →
  route order to manual with a banner, never half-run** (analysis §3).
- Seed only the fields that actually vary across forms + the caption/cell-region
  data the anchoring needs — do NOT boil the ocean; grow per acceptance failure.
- **Gate:** loader returns a registry slice for every field a compiled check binds
  to on the 10-order golden set; unknown-form orders are flagged, not processed.

## Phase 2 — caption stop-text + cell-region anchoring (kills F7 residue + F8)

This is the L3 "region" the back-locator already reserves a slot for.

- `back_locator`: when locating an XML value on the PDF, require the located token
  run to fall **within the field's `cell_region`** (from the registry) and to the
  right-of/below its `caption_text` bbox. A hit outside the region → **not located
  → value null → CANNOT_EVALUATE**, never a garbage value (analysis §3 gate).
- Caption stop-text: every `caption_text` string is excluded from extraction
  candidates for its region → the "results ITEM of" / F7 class becomes structurally
  impossible (belt-and-suspenders with the current shape guard).
- **Comp grid (F8):** anchor each `comp_N_*` value to its **column band** (comp N's
  x-range from the grid header). A value spanning multiple column bands (the
  `CvPor,CvPat CvPor,CvPat…` bleed) fails the single-column test → suppressed.
  This is the *safe* way to do F8 — column geometry, not string-shape guessing.
- **Gate:** garbage-binding rate = 0 on the golden set (any caption/cross-cell hit
  is a bug); F8 comp-grid values each anchor to exactly one column.

## Phase 3 — vendor adapter (L1)

- `(vendor, mismo_variant) → canonical XPath map + date/number normalizers`.
  Detect vendor from `AppraisalSoftwareProductName` (a la mode / ClickFORMS / ACI
  all present in the 5-XML sample); fall back to the generic 2.6GSE map.
- New vendor = a new map file, zero engine change.
- **Gate:** per-label extraction precision ≥ 99% XML-sourced / ≥ 95% PDF-sourced
  vs human-verified truth, **run per vendor** before that vendor is enabled.

## Phase 4 — UAD 3.6 registry slice (when 3.6 sample XMLs arrive)

3.6 is structured data (less PDF mining) → L1/L2 shrink; L3 check-compiler + L4
judge/queue port unchanged (format-agnostic by design). Key everything
`uad36.urar.<section>.<field>`. Lean the 3.6 differentiator into cross-document /
engagement-letter overlay checks the GSE compliance engine doesn't do.

## Acceptance gates (from audit §5 — the definition of done)

| Gate | Threshold |
|---|---|
| Per-label extraction precision vs human truth (all 3 vendors) | ≥ 99% XML / ≥ 95% PDF; every value carries provenance or is null |
| Garbage-binding rate (caption / cross-cell) | 0 — anchoring makes it structurally impossible |
| Trigger-correctness (N/A decisions) | 100% on a written per-check truth table |
| Judge input = resolved values | already asserted in code (`test_packet_value_is_resolved_not_raw_preresolution_slot`) |
| REVIEW queue composition | 0 caption/garbage-value REVIEWs; system-degradation cards already grouped (`needs_data`) |
| New-vendor onboarding | golden suite green on 3–5 sample orders before enabling |

## Sequencing note

Phases 0→1→2 are the F8 + provenance critical path and can ship independently of
3 and 4. Phase 3 (vendor adapter) is needed before onboarding a non-a-la-mode AMC
in production. Phase 4 waits on real 3.6 sample XMLs but the registry must be
version-namespaced from Phase 1 so 3.6 drops in without a rekey.
