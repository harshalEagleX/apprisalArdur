# SHAL Universal QC Architecture
### Checklist-agnostic, AMC-agnostic evaluation of UAD 3.6 reports from flattened PDF

**Version:** arch-2.0.0
**Grounding:** empirically derived from a 40-page flattened UAD 3.6 URAR (1465 Turner Rd NE, Rome GA), plus GSE UAD 3.6 specification behaviour
**Replaces:** positional-window routing, fused extraction/judgment, boolean coercion at extraction

---

## 0. Invariants

These hold for every AMC, every checklist, every property type. Violating any one of them is what produced the failures in `_run18`.

| # | Invariant |
|---|---|
| **I1** | Extraction never sees a checklist. Evaluation never sees an image. |
| **I2** | Page position is never a routing input. Structure is discovered per document. |
| **I3** | Absent ≠ false. Three distinct states: NOT_PRESENT, PRESENT_EMPTY, UNREAD. |
| **I4** | Literal text is stored before any derived value. Derivation is additive, never destructive. |
| **I5** | Arithmetic is code. A model never computes, sums, compares, or ratios. |
| **I6** | Every check declares its input facts. Unmapped input = build failure, not runtime VERIFY. |
| **I7** | A missing fact triggers rescue before it triggers a verdict. |
| **I8** | No PASS from a single unverified read. |

---

## 1. Why the current pipeline cannot be patched

From `_run18` on this exact report:

| Symptom | Root cause |
|---|---|
| 41 fields lost (`market`, `contract_history`) | 23 calls in flight over 4 keys → 17–25 tok/s per call → 180s timeout = 4,500 token hard ceiling |
| Truncation retries at 9,200 and 12,000 tokens | Truncation handler raises `max_tokens` instead of splitting. `splits: 0` — the split path never fired |
| `comp_4` concession/time adjustments transposed, still `CERTIFIED` | `grid_reconcile` proves sum, not binding. Sum is invariant to row permutation |
| Septic finding structurally unreachable | `adverse_conditions='None' → 'False'` destroyed the literal; `contract_analysis_comment` never extracted |
| `is_pud_checked = "Planned Unit Development (PUD)"` | Model returned the row label as the value; no label/value discrimination |
| `JOB 018JOB 018`, `Dynnesson`, `09/29` vs `09/25` | Full-page resolution on dense alphanumerics; no second pass |
| Provenance off by 1–2 pages throughout | Model asked to self-report page number |
| `DONE`, `coverage 125.7%` on an unreviewable run | Coverage counts fields emitted, not required fields resolved |

The architecture below removes each cause structurally rather than tuning around it.

---

## 2. Stage 0 — Ingest and format gate

```
pdfinfo    → page count, page size
pdffonts   → empty table ⇒ flattened ⇒ vision path
             non-empty ⇒ text path (pdftotext -layout), vision only for checkbox regions
pdfdetach  → embedded MISMO XML? (some vendors attach it — check before assuming none)
```

**Decide once, at the top.** This report: `pdffonts` empty, 40 pages, `document_class: flattened`.

Rasterize at **150 DPI for routing**, **crop-and-upscale for dense regions** (§5.4). Together downscales server-side to a fixed image-token budget, so page DPI above ~150 buys nothing; crop area is the only lever on effective resolution.

---

## 3. Stage 1 — Structural router (deterministic, zero model cost)

### 3.1 The problem with positional windows

UAD 3.6 is a single dynamic URAR replacing the 1004/1073/1025/2055/1004C family. Sections activate and repeat based on property characteristics and scope: condo sections appear only for condos, Unit Interior repeats per unit on a 2-4, and government-loan fields (Remaining Economic Life, effective age, attic) appear only for FHA/USDA/VA assignments.

**Consequence:** the sales grid is on pages 21–24 in this report and will be elsewhere in the next one. A positional window feeds the wrong page to the right schema, and a VLM handed the wrong page does not error — it produces plausible values for fields that aren't there.

### 3.2 The form generator gives you a free anchor

Section tabs in the URAR are black rounded rectangles rendered by the form engine, not by the appraiser. They are geometrically invariant. Measured across all 40 pages of this report:

- tab left edge at **x ≈ 14.5% of page width**
- tab height **6–40 px at 100 DPI**
- page-top tab at **y = 4.8% on 38 of 40 pages** (100% of pages that have one)
- `(continued)` italic suffix marks continuation

### 3.3 Detection algorithm

```python
def find_section_bands(page_gray):
    h, w = page_gray.shape
    x0, x1 = int(w*0.145), int(w*0.30)
    dark = (page_gray[:, x0:x1] < 90).mean(axis=1)
    runs, start = [], None
    for y, is_dark in enumerate(dark > 0.75):
        if is_dark and start is None:
            start = y
        elif not is_dark and start is not None:
            if 6 <= y - start <= 40:
                runs.append((start, y))
            start = None
    return merge_adjacent(runs, gap_px=4)     # p8 emitted 48.7% + 49.7% as two runs
```

Crop each detected band → one small VLM call per band returning only the label string. Bands are ~30 tokens of image each. **Entire router for a 40-page report: well under 1,000 output tokens.**

### 3.4 Empirical result on this report

| Pages | Detected bands | Note |
|---|---|---|
| 1, 38 | **0** | No tab — inherit section from previous page |
| 3–6, 9–11, 16–18, 20, 25, 27–37, 39, 40 | 1 | Single section |
| 7, 12, 13, 26 | 2 | Section boundary mid-page |
| 2, 8, 14, 15, 19 | 3 | Multiple sections start on one page |
| 21, 23 | 5–6 | Grid tab **plus row-group bands** |
| 22, 24 | 5 | Grid continuation row-groups |

**Two findings that matter:**

1. **Sections start mid-page.** Page 19 alone opens Subject Listing Information, Sales Contract, and Prior Sale and Transfer History. Header-band-only cropping (top 12%) misses two of three. Scan the **full page height**.

2. **Grid row-group bands are detected by the same mechanism.** On p21 the detector returns the section tab plus `General Information`, `Site`, `Dwelling(s)`, `Unit(s)` — these are the row-group boundaries. **This is the row-label binding that `grid_reconcile` currently lacks** (§7.3).

### 3.5 Output

```yaml
section_map:
  assignment:              {pages: [2],           complete: true}
  site:                    {pages: [2,3,4,5],     complete: true}
  sketch:                  {pages: [6,7],         complete: true}
  dwelling_exterior:       {pages: [7,8],         complete: true}
  unit_interior:           {pages: [8,9,10,11,12],complete: true}
  outbuilding:             {pages: [13],          complete: true}
  vehicle_storage:         {pages: [13,14],       complete: true}
  amenities:               {pages: [14],          complete: true}
  quality_condition:       {pages: [14],          complete: true}
  highest_best_use:        {pages: [15],          complete: true}
  market:                  {pages: [15,16,17,18], complete: true}
  subject_listing:         {pages: [19],          complete: true}
  sales_contract:          {pages: [19],          complete: true}
  prior_transfer:          {pages: [19,20],       complete: true}
  sales_comparison:        {pages: [21,22,23,24,25,26], complete: true}
  reconciliation:          {pages: [26,...,35],   complete: true}
  supplemental:            {pages: [36,37,38],    complete: true}
  certifications:          {pages: [39,40],       complete: true}
```

Sections not in the map are **NOT_PRESENT** — a first-class state, not a null.

---

## 4. Stage 2 — Driver fields and the applicability model

### 4.1 Why this exists

The GSEs replaced form numbers with a small set of Summary-section data points that determine which sections the report renders. This is the *only* legitimate source of N/A. The judge must never infer applicability — that is the documented cause of your false-NA class.

### 4.2 The driver pass

**One call, page 1–2 only, ~12 fields, run before everything else.**

| Driver | This report | Governs |
|---|---|---|
| `construction_method` | Site Built | manufactured (1004C) sections, cost approach requirement |
| `attachment_type` | Detached | attached/row sections |
| `project_legal_structure` | (absent) | condo / co-op / PUD sections |
| `subject_site_owned_in_common` | No | condo site sections |
| `units_excluding_adus` | 1 | Unit Interior repetition, 2-4 income sections |
| `accessory_dwelling_units` | 0 | ADU sections |
| `property_valuation_method` | Traditional Appraisal | desktop/hybrid/exterior scope reductions |
| `inspection_type` (ext/int) | Physical / Physical | interior-dependent checks |
| `assignment_reason` | Purchase | refinance-only checks (EQ-63) |
| `financing_type` (from contract) | Conventional | **entire FHA block** |
| `occupancy` | Vacant | tenant-occupied checks |
| `is_pud / condo / coop / condop` | all No | EQ-60,61,62,81 |

### 4.3 Applicability resolution — the three-way rule

```
driver says section NOT required          → NOT_APPLICABLE      (silent, no card)
driver says required + section_map has it → must extract; failure is UNREAD
driver says required + section_map lacks  → REPORT DEFECT       (real finding, FAIL)
```

**This is the whole N/A problem, solved.** No judge improvisation. On this report the rule produces: FHA block N/A (financing_type = Conventional), PUD items N/A (is_pud = No), EQ-63 N/A (assignment_reason = Purchase), EQ-26 N/A (converted_area = None), cost approach N/A (construction_method = Site Built) — 6 checklist items plus 16 FHA sub-items, all deterministically.

### 4.4 Checkbox extraction rule (applies wherever drivers are read)

Your `is_pud_checked = "Planned Unit Development (PUD)"` is the label, not the state. Fix:

```json
{"row_label": "Planned Unit Development (PUD)",
 "yes_box": "checked|unchecked",
 "no_box":  "checked|unchecked"}
```

Validator: `yes_box XOR no_box` must hold. Both or neither → **NOT_FOUND → rescue → VERIFY**. Never default to False. This form has ~30 such pairs (p1×5, p2×8, p7, p13×2, p15, p19×3).

---

## 5. Stage 3 — Extraction

### 5.1 Region types

Every extraction unit is one of four kinds. They have different schemas, ceilings and validators.

| Kind | Ceiling | Output | Validator |
|---|---|---|---|
| **scalar_region** | 600 tok | typed key/value | enum + type + label-match |
| **narrative_region** | 400 tok | **verbatim text, no JSON nesting** | length > 0, no truncation marker |
| **checkbox_region** | 200 tok | label + yes/no pair | XOR |
| **grid_region** | 700 tok/comp/page | positional array | row-label binding + sum |
| **exhibit_region** | 250 tok | caption list only | count ≥ 1 |

### 5.2 The narrative rule (this is what lost your headline finding)

`contract_history` requested 22 structured fields, blew 6,500 tokens, truncated, retried at 12,000, died.

Split it:
- **5 scalars** (contract_price, contract_date, sale_type, list_price, dom) → `scalar_region`, 300 tok
- **1 narrative** (`contract_analysis_comment`) → `narrative_region`, verbatim, 400 tok
- **1 table** (`listing_price_history`) → `grid_region`, 300 tok

Same content, ~1,000 tokens instead of 6,500, no truncation possible.

**Narrative fields in this form** (all must be verbatim, never schematised):
`contract_analysis_comment`, `prior_sale_analysis_comment`, `listing_history_analysis`, `market_conditions_commentary`, `price_trend_commentary`, `sketch_commentary`, `quality_condition_reconciliation`, `final_reconciliation_comment`, `apparent_defects_*` (every instance).

### 5.3 Never ask the model for provenance

Page, section and region are known by the caller. Stamp them in code. Removing `page` from the schema also removes the `p38`/`p40` and `p25`/`p26` errors that would put wrong citations in AMC reject letters.

### 5.4 Crop-based resolution for dense alphanumerics

Image tokens are ~constant per image after server-side downscale. A crop of 1/9 page area therefore delivers ~3× linear resolution **at the same cost**.

Mandatory crop targets on this form:
- APN / legal description block (`JOB` ← `J08`)
- All checkbox column pairs
- Grid numeric columns (adjustment values)
- License number and expiry (p37, p40)
- Dates (`09/25` ← `09/29`)

### 5.5 Grid extraction — one call per comp per page-pair

Current: 12 calls (each comp read twice, once per page). 42,939 output tokens — **53% of your entire run**.

Correct: **6 calls**, one per comp, both pages of the pair in the same call. The comp column header (`Comparable #1`) and the `Property Address` row repeat on both pages of a pair — use address as the **join key** so column binding survives page split.

Output as positional arrays keyed to the row-label list, not repeated long key names:

```json
{"comp_index": 4,
 "address": "412 Perry Rd, Armuchee, GA 30105",
 "row_group": "Unit(s)",
 "rows": [["Bedrooms","4",null],
          ["Baths - Full | Half","2 | 0","$9,000"],
          ["Finished Area Above Grade","1,884 Sq. Ft.","$10,600"]]}
```

Three-tuple `[label, value, adjustment]` makes transposition **detectable** — see §7.3.

---

## 6. Stage 4 — Fact store

### 6.1 Record shape

```yaml
site.apparent_defects:
  literal: "None"                    # I4 — always first, never overwritten
  derived:
    has_defects: false               # additive
  state: PRESENT                     # PRESENT | PRESENT_EMPTY | NOT_PRESENT | UNREAD
  page: 3                            # stamped by caller
  region: site.defects
  reads: [{pass: 1, value: "None"}, {pass: 2, value: "None"}]
  agreement: true
  confidence: verified               # verified | single | unverified | unread
```

`confidence` is **categorical, not a float**. Your `0.93` on every field and `0.55` on every comp_6 field carries no information — it is a constant per code path. Categories derived from actual evidence are usable; invented floats are not.

### 6.2 Multi-observation facts (fix `consistency.py`)

You achieved **1.09 observations per fact** against a 3.4 design. Both GLA sources were on page 7 — the same read, double-counted.

True observation sites in this report:

| Fact | Sites |
|---|---|
| GLA 2,137 | p6 sketch calc, p7 ANSI declaration, p8 finished above grade, p21/23 grid subject column |
| Value $310,000 | p1 summary, p26 reconciliation, p33 weighted calc, p35 range chart, p22/24 indicated value |
| Bedrooms 4 | p6 sketch labels, p8 total bedrooms, p8 room summary, p21/23 grid |
| Baths 3 | p6 sketch, p8 totals, p8 room summary, p21/23 grid |
| Year built 1979 | p7 dwelling exterior, p21/23 grid |
| Condition C4 | p1, p7 exterior, p8 interior, p14 overall, p21/23 grid |
| Site area 40,511 | p2 total, p2 APN parcel size, p21/23 grid |
| Contract price $300,000 | p1, p19 sales contract, p21/23 grid, p26 summary |

Register observation **sites**, not field aliases. Majority vote across genuinely independent reads; any dissent → VERIFY with all observations cited.

---

## 7. Stage 5 — Deterministic verification (no model)

Runs before evaluation. Everything here is exact, reproducible, free.

### 7.1 Identity checks
`gla == total_living_area == grid_subject_gla`; room counts vs sketch; area chain (outbuilding 253.85→254, carport 329.26, deck 249.38→249, porch 272); DOM 197+8=205; signature date ≥ effective date; cert expiry > effective date.

### 7.2 Grid arithmetic
Per comp: `Σ line adjustments == net_printed`; `sale + net == adjusted_printed`. Across set: weights sum to 100%; `Σ(adjusted × weight) == final value`; supported range contains final value.

### 7.3 Row-label binding — the transposition fix

Sum is invariant to permutation. `comp_4` had the contract-date adjustment sitting in the concessions row and still returned CERTIFIED.

```
1. Expected row-label template per row_group, derived from the grid_region bands (§3.4)
2. Every returned triple must bind to exactly one template label
3. Template labels present on the page must all be bound — no gaps
4. Adjustment values must attach to their own label, not a neighbour's
5. Unbound or duplicate label → region UNREAD → rescue
```

### 7.4 Rate-consistency derivation
Fit implied rates and compare to stated support: GLA $/sqft, lot $/sqft, per-bath, per-garage-space, pool, condition step. On this report this derivation produced FAIL EQ-94 (stated $8,500/garage vs applied $6,000 and $3,500) and **downgraded EQ-77 from FAIL to VERIFY** by proving the time adjustments reconcile to the p16 trend matrix. Both outcomes are correct; neither is reachable by a model.

### 7.5 Ratio computation
Net %, gross %, largest-line % per comp, against a per-AMC threshold table (§9.3).

---

## 8. Stage 6 — Evaluation

The evaluator sees the **fact store as text**, never an image, and holds all sections simultaneously. This is the only layer where cross-page findings can exist. On this report the septic finding requires `site.apparent_defects` (p3) + `unit_interior.utilities_operating` (p8) + `contract.analysis_comment` (p19) + `reconciliation.value_condition` (p26).

### 8.1 Evaluator taxonomy

Every check in any AMC checklist reduces to one of eight types.

| Type | Definition | Engine | Missing-fact policy |
|---|---|---|---|
| **A** | Single-field lookup / enum test | code | rescue → VERIFY |
| **B** | Cross-field identity or equality | code | rescue → VERIFY |
| **C** | Aggregate over the comp set | code | partial credit, name the gap |
| **D** | Artifact presence (photo, graph, exhibit) | code over caption index | rescue that page |
| **E** | Narrative-grounded judgment | LLM over retrieved spans | VERIFY (honest) |
| **F** | Field-vs-narrative contradiction | contradiction pass | both sides required |
| **G** | External-document dependency | none | VERIFY by design |
| **H** | Policy threshold / investor criteria | threshold table + LLM | VERIFY |

### 8.2 ESA checklist classified (all 91)

| Type | Count | Items |
|---|---:|---|
| **A** | 36 | 8, 9, 10, 13, 14, 15, 16, 17, 18, 20, 24, 26, 29, 31, 36, 37, 40, 41, 44, 45, 46, 49, 49b, 52, 54, 55, 56, 60, 61, 62, 63, 65, 66, 67, 85, 99 |
| **B** | 8 | 1, 6, 30, 34, 35, 91, 97, 100 |
| **C** | 18 | 53, 70, 71, 73, 74, 75, 76, 78, 79, 80, 81, 82, 83, 84, 86, 87, 92, 93 |
| **D** | 8 | 21, 22, 23, 33, 42, 59, 72, 90 |
| **E** | 6 | 50, 51, 58, 64, 69, 77 |
| **F** | 6 | 19, 57, 68, 94, 95, 98 |
| **G** | 5 | 2, 5, 7, 11, 12 |
| **H** | 4 | 32, 43, 47, 48 |

**A+B+C+D = 70 of 91 = 77% requires no LLM at all.** Only 12 items (E+F) need language judgment; 9 (G+H) are structurally VERIFY or policy lookups.

This ratio is the profitability lever. It is also the determinism lever — 77% of verdicts become byte-identical across runs, which is the precondition for `auto_pass_enabled: true`.

### 8.3 Type D must never use text logic

"Are the required photos included?" is a **caption-index membership test**, not a question about text absence. Build a caption index once during the exhibit pass:

```yaml
exhibit_index:
  - {page: 5,  caption: "Property Access (Street Scene) - Street view"}
  - {page: 7,  caption: "Dwelling Front - Side View"}
  - {page: 8,  caption: "Dwelling Rear - Rear View"}
  - {page: 8,  caption: "Dwelling Rear - Septic Tank"}
  ...
```

Then EQ-33 = `require_any(["front"]) ∧ require_any(["rear","back"]) ∧ require_any(["street"]) ∧ comp_front_count == comparable_count`.

### 8.4 Type F — the contradiction pass

Runs independently of the checklist and produces findings the checklist has no item for. On this report it caught the $330,000 vs $310,000 subject list price, 210 vs 44 sales, the comp 3 address typo, and the 11.4%-vs-6.1% reduction arithmetic — none of which map to an ESA item.

**Declare contradiction pairs in the fact schema, not in the checklist:**

```yaml
contradiction_pairs:
  - id: CX-REPAIR-VS-ASIS
    field_side:     [site.apparent_defects, reconciliation.apparent_defects,
                     unit_interior.utilities_operating, reconciliation.value_condition]
    narrative_side: [contract.analysis_comment, prior_sale.analysis_comment]
    trigger: narrative asserts a required repair, remediation, or non-operational
             condition while field side asserts none / operating / As Is
    severity: FAIL
    links: [EQ-19, EQ-95, EQ-98, EQ-99]      # dedup — one card, four references

  - id: CX-LIST-PRICE
    a: subject_listing.current_list_price
    b: grid.subject_list_price
    rule: equal
    severity: FAIL

  - id: CX-SAMPLE-SIZE
    a: market.sales_past_12mo
    b: market.trend_commentary.sample_n
    rule: equal
    severity: VERIFY
```

Contradiction pairs are **AMC-independent** — they belong to the UAD 3.6 form, so every AMC inherits them for free.

---

## 9. The Checklist IR — the AMC-agnostic layer

This is what makes any checklist work. `checklist_compile.py` targets this IR; the evaluator only ever reads the IR.

### 9.1 Item schema

```yaml
- id: EQ-87
  source_text: "Is the subject bathroom count bracketed by the comparable sales?"
  type: C
  polarity: expect_true          # some questions expect No ("Is this non-arm's length?")
  requires:
    - subject.baths_full
    - comps[*].baths_full
    - comps[*].listing_status
  applicable_when: always
  predicate: bracket(subject.baths_full, comps[status=closed].baths_full)
  on_missing: partial
  on_false: FAIL
  reject_ref: RJ-BRACKET-BATH

- id: EQ-19
  source_text: "Are there any defects, damages or deficiencies? (If yes, are photos/comments provided?)"
  type: F
  polarity: expect_false
  requires: [site.apparent_defects, contract.analysis_comment,
             unit_interior.utilities_operating, reconciliation.value_condition]
  applicable_when: always
  predicate: contradiction(CX-REPAIR-VS-ASIS)
  on_missing: rescue
  on_false: FAIL
  dedup_group: SEPTIC

- id: EQ-60
  source_text: "Is the developer/builder in control of the HOA?"
  type: A
  requires: [pud.developer_control]
  applicable_when: drivers.is_pud == true      # ← N/A is computed, never inferred
  on_missing: rescue
  on_false: FAIL
```

### 9.2 Polarity is mandatory

ESA mixes expectation directions: EQ-16 ("Is the zoning legal non-conforming or illegal?") expects **No**; EQ-20 ("Was ANSI used?") expects **Yes**. Your memory already records "empty `expects:` fields allowing judge to invert logic" as a false-positive class. In the IR, `polarity` is a **required** field — compile fails without it. That single constraint eliminates the class.

### 9.3 Per-AMC parameter table

Thresholds are data, not code. A new AMC is a YAML file, not a release.

```yaml
amc: equity_solutions_usa
thresholds:
  comp_distance_miles: {urban: 1.0, suburban: 2.0, rural: 5.0}
  adjustment: {net_pct: 15, gross_pct: 25, line_pct: 10}
  comp_contract_age_months: 12
  min_closed_comps: 3
  min_data_sources: 2
  condition_stop: [C5, C6]
  quality_acceptable: [Q1,Q2,Q3,Q4,Q5]
  max_units_incl_adu: 4
stop_conditions: [form_type_mismatch, condition_c5_c6, hbu_not_present_use,
                  illegal_use, units_exceed_4]
reject_language_mode: amc_language_bank      # | sheet1_generalized | constructed
```

### 9.4 Onboarding a new AMC

1. Map each raw question → `type` + `requires` + `polarity` (the only manual step)
2. Fill the threshold table
3. Run the coverage gate (§10)
4. Run the golden-set regression (§13)

No extraction change. No prompt change. **The fact store is AMC-independent by construction** — which is also why a checklist recompile must never invalidate stored packets in the replay harness.

---

## 10. The coverage gate — build-time, not runtime

This is the mechanism that answers "without failing a single time."

```
FOR each item in compiled checklist:
  FOR each path in item.requires:
    ASSERT path ∈ field_schema                     else COMPILE ERROR
    ASSERT path.region ∈ extraction_plan           else COMPILE ERROR
    ASSERT path.region.kind matches path.data_type else COMPILE ERROR
  ASSERT item.polarity is set                      else COMPILE ERROR
  ASSERT item.applicable_when references only driver fields
                                                   else COMPILE ERROR
```

A checklist that references a fact nobody extracts **cannot ship**. You cannot guarantee the model reads every page correctly; you *can* guarantee no check ever fails because the data path was never built. That is the failure class you are actually hitting.

Runtime companion:

```
required_facts   = ∪ requires of all applicable items
resolved_facts   = fact store entries with state ∈ {PRESENT, PRESENT_EMPTY, NOT_PRESENT}
coverage         = |resolved| / |required|
IF coverage < 1.0 AND rescue exhausted → run status = INCOMPLETE, emit no verdicts
```

`_run18` reported `DONE` and `coverage 125.7%` — because it counted fields emitted (357) against schema size (284) rather than required facts resolved. Under this definition the same run reports `INCOMPLETE, coverage 0.71`, which is the truth.

---

## 11. The rescue ladder

Budget is not a constraint. VERIFY is the **last** step.

| Step | Action | Cost |
|---|---|---|
| 1 | Re-read region, split in half, ceiling halved | ~2 × 300 tok |
| 2 | Field-targeted re-read: that page, only the missing keys | ~150 tok |
| 3 | Crop the row/column region, 3× effective resolution | ~150 tok |
| 4 | Second independent pass; disagreement → VERIFY (never tie-break) | ~150 tok |
| 5 | VERIFY tagged **UNREAD**, page cited, cause recorded | 0 |

Run step 4 **unconditionally** on: all checkbox pairs, all grid numerics, all Type A/B facts, license number, all dates, APN. That is the `auto_pass_enabled` precondition (I8).

---

## 12. Verdict algebra and deduplication

```
NOT_APPLICABLE  ← applicable_when false (driver-derived only)
PASS            ← predicate true AND all inputs confidence ∈ {verified}
VERIFY          ← predicate true but inputs confidence = single/unverified
                | type E/G/H
                | any input UNREAD after rescue
                | two passes disagree
FAIL            ← predicate false with all inputs verified
INCOMPLETE      ← coverage < 1.0 (run-level; suppresses all verdicts)
```

**Dedup by `dedup_group`.** The septic root cause satisfies EQ-19, EQ-95, EQ-98, EQ-99. Emit **one** card with four checklist references. Your memory records "duplicate EQ cards from same underlying field" as a known false-positive class; `dedup_group` removes it structurally.

**Reject language** carries `mode` from §9.3 and never embeds instance values — comp numbers, dollar amounts and dates are `{slots}` filled at render time.

---

## 13. Concurrency, timeout, budget

### 13.1 The governing equation

```
wall_clock = total_output_tokens / (keys × 101)
per_call_rate = 101 / (in_flight / keys)
```

`_run18`: 23 in flight over 4 keys → 5.75/key → ~17–25 tok/s per call → the "measured 25 tok/s floor" was **self-inflicted**, and it set a 4,500-token hard ceiling under a 180s timeout.

### 13.2 Rules

```
in_flight ≤ 2 × keys            (8 concurrent; queue the rest)
timeout   = (ceiling / rate_at_current_concurrency) × 1.5, computed per call
on truncation → SPLIT, never raise max_tokens
retry on error code only, never on timeout
```

At 8 in flight each call sees ~101 tok/s: a 5,600-token section completes in 55s. **Fewer concurrent calls finish this report faster.**

### 13.3 Budget for this report under the new design

| Bucket | Old | New | How |
|---|---:|---:|---|
| Structural router | 0 | 900 | new, pays for itself |
| Driver pass | 0 | 400 | new |
| Grid | 42,939 | 8,400 | 6 calls not 12; positional arrays |
| Narrative sections | 17,521 | 3,200 | verbatim blocks, 400 cap |
| Scalar sections | 19,791 | 9,000 | tightened schema |
| Checkbox micro-calls | 0 | 2,400 | new, ~30 pairs |
| Second pass (high-risk) | 0 | 3,000 | new |
| **Total** | **80,251** | **~27,300** | |

At 4 keys: **~68s**. At 6 keys: ~45s. Adding a fifth key is the cheapest remaining lever — the equation is linear in `keys` and nothing else in the design is latency-bound.

---

## 14. Regression harness

Extraction and evaluation version independently:

```
packet = {section_map, driver_fields, fact_store, exhibit_index}   ← versioned, replayable
verdicts = evaluate(packet, checklist_ir, thresholds)              ← pure function
```

Because `evaluate` is pure over a stored packet, **a checklist recompile is testable with zero model calls.** Gate every change on:

| Gate | Threshold |
|---|---|
| Golden set field-level accuracy | ≥ 99.5% on Type A/B facts |
| Verdict diff vs human-reviewed baseline | 0 unexplained FAIL flips |
| Determinism | 3 consecutive runs, byte-identical on A+B+C+D items |
| Coverage | 1.0 on every golden order |
| Wall clock | p95 < 60s |

Seed the golden set with this report — it contains an unusually rich failure surface: a cross-document contradiction, a stated-vs-applied support conflict, two unbracketed dimensions, a mislabeled adjustment row, four internal data conflicts, and a fully N/A FHA block.

---

## 15. Build order

| # | Change | Unblocks |
|---|---|---|
| 1 | Cap in-flight at 2/key; per-call timeout formula | recovers both dead sections immediately |
| 2 | Split on truncation; delete the raise-ceiling path | ends the doom loop |
| 3 | Stop boolean-coercing free text; literal-first storage | makes Type F possible at all |
| 4 | Narrative regions as verbatim blocks | recovers `contract_analysis_comment` |
| 5 | Structural router replaces positional windows | correctness on every non-SFR report |
| 6 | Driver pass + three-way applicability | kills false N/A and false FAIL |
| 7 | Checkbox XOR pairs | kills silent boolean flips |
| 8 | Row-label binding in `grid_reconcile` | kills transposition |
| 9 | Coverage gate + INCOMPLETE status | ends silent partial runs |
| 10 | Checklist IR + evaluator types A–H | AMC-agnostic; 77% deterministic |
| 11 | Contradiction pass | findings no checklist contains |
| 12 | Rescue ladder + unconditional second pass | precondition for auto-pass |

Steps 1–4 are configuration and schema changes recoverable in a day, and alone would have produced a correct review of this report. Steps 5–12 are what make it hold for every report and every AMC.

---

*Empirical figures in §3.4, §7.4, §8.2 and §13.3 were measured against the 40-page 1465 Turner Rd NE report and the 91-item Equity Solutions USA UAD 3.6 checklist.*
