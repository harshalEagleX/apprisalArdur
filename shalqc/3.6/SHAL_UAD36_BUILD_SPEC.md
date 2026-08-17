# SHAL UAD 3.6 — Build Spec

### Checklist-agnostic, AMC-agnostic evaluation of UAD 3.6 reports from flattened PDF

**Version:** build-2.1.0
**Supersedes:** `SHAL_Universal_QC_Architecture.md` (arch-2.0.0) — that document's *reasoning* is preserved here in full; its §3.3 code and §3.4/§3.5 tables are **corrected against measurement**.
**Grounding:** every number below was re-measured against `shalqc/3.6/Email - AppraisalArdur - Outlook (1).pdf` (40pp, 1465 Turner Rd NE, Rome GA) and `_run18.json`, on 2026-08-12.
**Status legend:** ✅ VERIFIED (re-measured, holds) · ⚠️ CORRECTED (claim was wrong, fixed here) · 🆕 NEW (found during verification) · ⬜ UNPROVEN (single-document, needs orders 2 and 3)

---

## 0. How to use this document

This is the durable reference. Read §1 first — it tells you which claims you may build on and which were wrong.

- **§1** verification ledger — trust boundary
- **§2–§9** the pipeline, stage by stage, with production code where it exists
- **§10–§14** the AMC-agnostic layer: IR, coverage gate, rescue, verdicts
- **§15** concurrency and budget
- **§16** build order — start here when implementing
- **§17** appendices: measured section map, row-label template, checklist zones, defect ledger

**Standing project rule that governs this whole document:** never judge a QC result from fewer than 3 randomly-picked orders. Everything marked ⬜ is measured on one document and proves a *mechanism*, never an *effect*.

---

## 1. Verification ledger

### 1.1 Verified — build on these

| Claim | Measurement |
|---|---|
| Document is flattened, no text layer | 40 pages, **0 characters, 0 fonts**, producer `PDFium` ✅ |
| Section tabs are geometrically invariant | first band at **y = 0.0482** on all 38 tabbed pages — min = max = mean, zero variance ✅ |
| Two pages carry no tab | exactly **[1, 38]** — p1 cover, p38 boilerplate; both inherit from predecessor ✅ |
| Tab left edge is fixed | dark run present at **x ∈ [14.5%, 30%]** on every tabbed page ✅ |
| `(continued)` marks continuation | confirmed visually on Site, Sketch, Dwelling Exterior, Unit Interior, Market, Reconciliation, Supplemental, Certifications ✅ |
| The same detector recovers grid row-groups | p21 returns `Sales Comparison Approach` + `General Information` / `Site` / `Dwelling(s)` / `Unit(s)` / `Quality and Condition` ✅ |
| Sections start mid-page | p19 opens **three** sections (y = 4.8%, 47.5%, 74.3%); p2 and p14 open three each ✅ |
| comp_6 was read correctly and wrongly discarded | `_run18.json` → `checks_run: 0`, both checks `skipped`, **`line_sum_read: -8200.0`** matching the printed net ✅ |
| Instrumentation disagrees with itself | grid block computes **regions 7 / verified 6 / checks 11**; summary reports **8 / 7 / 12** ✅ |
| Coverage is computed against the wrong denominator | `coverage_pct 125.7` = 357 emitted ÷ 284 schema ✅ |
| Cost projector under-predicts 3.3× | `cost_projection.output_tokens: 24600` vs 80,251 actual ✅ |
| Provenance is off by one on the section path | `design_style` stamped p6, Dwelling Exterior starts p7. Same −1 on assignment (1/2), reconciliation (25/26), value_reconciliation (32/33); appraiser −2 (38 vs signature p40) ✅ |
| Checklist parse was clean | verdicts CSV = 91 rows = 90 numbered items + `49b` split; identical gap set `[3,4,25,27,28,38,39,88,89,96]` ✅ |
| FHA block is 17 sub-items | rows 132–149 of the checklist CSV ✅ |
| Septic contradiction is real | p19 Sales Contract Analysis: *"The seller is required to repair the septic system to proper working order prior to closing"* ✅ |
| Concessions field conflict is real | p19: `Known Sales Concessions: Yes` / `Total Sales Concessions: $0` ✅ |
| FHA block is legitimately N/A | p19: *"conventional financing (80% LTV, 30-year fixed)"* ✅ |
| A1 list-price conflict is real | grid subject column: `List Price $330,000` + `Listing Status Pending`; p19 pending listing is **$310,000**, and $330,000 was the *withdrawn* listing's final price ✅ |

### 1.2 Corrected — the previous spec was wrong

| # | What arch-2.0.0 said | What measurement shows | Consequence |
|---|---|---|---|
| **C1** | §3.3 detector: `if 6 <= y - start <= 40` with `gap_px=4` | **Silently deletes real bands.** On p21 the `Quality and Condition` band renders **5px** at 100 DPI and is dropped; on p23 the same band renders 6px and survives. Every band is a *pair* of runs (main 6–16px + companion 4–5px) and `gap_px=4` fails to join them | ⚠️ The row-label template §9.3 depends on is **unbuildable by the spec's own code**. Fixed in §4.3 |
| **C2** | §3.4: p19 has 3 bands, p8 and p15 have 3, p22/p24 have 5 | With the corrected constants: p19 = **3** ✅, p8 = **2**, p15 = **2**, p21/22/23/24 = **6 each** | ⚠️ Spec's *observations* were right where it mattered (p19); its counts on p8/p15/p22/p24 were wrong |
| **C3** | §3.5 `section_map` lists 18 sections | The document has **21**. Missing: **`Subject Property`** (p2) and **`Functional Obsolescence`** (p12); `Outbuilding` is printed `Outbuilding - Outbuilding` | ⚠️ Two sections would never be extracted — silent NOT_PRESENT on fields that exist |
| **C4** | §3.3 "crop each band → one small VLM call ... under 1,000 output tokens" | Band **kind** needs no model at all. Width fraction separates them with zero overlap: **0.18–0.22 = section tab**, **0.70 = row-group**. Only the label string needs a call | ⚠️ Cheaper and deterministic; kind is never a model guess |
| **C5** | §8.3 "Type D must never use text logic" — defined as caption-index presence only | Exhibits carry **data**, not just captions. The p19 MLS exhibit contains DOM/price history that contradicts the structured fields above it; the p16–18 trend graphs carry the 210-sales figure behind finding A3 | ⚠️ Taxonomy gap — see 🆕 N2 |

### 1.3 New — found during verification, in neither prior document

| # | Finding |
|---|---|
| **N1** | 🆕 **DOM contradiction, structured field vs. embedded exhibit.** The Subject Listing table (p19) reports DOM **197** for the withdrawn listing and **8** for the pending, totalling `Total DOM 205`. The MLS history exhibit *on the same page* reports **188** and **7**, totalling 195. Both are separately defensible (196 calendar days 09/23/25→04/07/26 vs. MLS's post-`Coming Soon` counter from 10/01/25) — but the report never reconciles them, and the review's "DOM 197+8=205 ✓" verified the table against itself. |
| **N2** | 🆕 **Exhibits are a fact source, not just a presence check.** N1 and finding A3 (210 vs 44 sales) are both field-vs-exhibit contradictions. §8.4 already lists A3 as a contradiction pair while §8.3 defines Type D as caption-membership only — the spec contradicts itself. Resolution in §9.1: split **D (presence)** from **D2 (exhibit-data)**. |
| **N3** | 🆕 **Three checklist zones sit outside the 90 numbered items** and are unmodelled: the 5 STOP conditions (rows 1–5), the FHA block (17 sub-items + 2 preconditions, rows 128–149), and Cost Approach (row 153). Row **129** — *"Per HUD's directive, all Site Condos must be on the 1073 form"* — is a driver-derived STOP condition, not a question. |
| **N4** | 🆕 **The AMC ships its own reject-language template** (row 157): *"Hello {appraiser name}, Equity Solutions USA has performed a Quality Control Review for the property located at {subject address} and found the following results…"* with a numbered findings list. This is the render target for §14's `reject_language_mode: amc_language_bank` and was never captured. |
| **N5** | 🆕 **Grid row-group `Outbuilding` was among the bands C1 drops** (p22). That is exactly where the unsupported $5,000/$2,500 outbuilding adjustments from FAIL 2.6 live — so the C1 bug lands directly on a finding the system is supposed to produce. |
| **N6** | 🆕 **Row 135 is an FHA hard threshold** the numbered checklist doesn't carry: *"Comparable sales 1, 2 and 3 MUST be within 12 months of the effective date."* Item 76 flagged comp 3's contract date at ~13 months as a soft VERIFY; under FHA it is a hard FAIL. |

### 1.4 Unproven — do not treat as fact

| Claim | Why it is not yet established |
|---|---|
| Band geometry generalises to other vendors | ⬜ Measured on **one** report from **one** form generator. A different vendor's URAR renderer may use different tab metrics. §4.4 defines the fallback. |
| The 8-type taxonomy covers any AMC checklist | ⬜ Derived from one 90-item checklist. Plausible and well-argued; unvalidated on a second AMC. |
| 77% no-LLM ratio | ⬜ Follows from the classification above; inherits its uncertainty. |
| Budget 80,251 → ~27,300 output tokens | ⬜ A projection. The previous projector was wrong by 3.3× (§1.1) — treat this one as a hypothesis with a measurement gate, not a plan input. |
| Wall clock ~68s at 4 keys | ⬜ Depends on the token projection above **and** on `wall = tokens/(keys×101)`, which PROBLEM_LOG P19b showed does **not** hold (measured 137 tok/s aggregate on 4 keys, not 405; run ends with its *slowest* call, not when a shared bucket drains). See §15.1. |

---

## 2. Invariants

These hold for every AMC, every checklist, every property type. Violating any one produced a documented failure in `_run18`.

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
| **I9** 🆕 | A **skipped** check is not a failed check. `verified · not_applicable · failed · skipped` are four distinct outcomes, and only `failed` may lower confidence. *(comp_6: 48 correct fields stamped 0.55 because `skipped` collapsed into `verified: false`.)* |
| **I10** 🆕 | Provenance is stamped by the caller, never self-reported by the model. *(Every −1 page error in §1.1 came from asking the model for a number only the caller knows.)* |
| **I11** 🆕 | A detector that can silently drop a record must be able to prove it didn't. Structurally identical pages must yield identical structure — asymmetry is an alarm. *(p21=5 vs p23=6 was the only visible symptom of C1.)* |

---

## 3. Stage 0 — Ingest and format gate

```
pdfinfo    → page count, page size
pdffonts   → empty table ⇒ flattened ⇒ vision path
             non-empty ⇒ text path (pdftotext -layout), vision only for checkbox regions
pdfdetach  → embedded MISMO XML? (some vendors attach it — check before assuming none)
```

**Decide once, at the top.** This report: `pdffonts` empty, 40 pages, `document_class: flattened`. ✅ re-measured.

Rasterize at **150 DPI for routing**, **crop-and-upscale for dense regions** (§6.4). Together downscales server-side to a fixed image-token budget, so page DPI above ~150 buys nothing (PROBLEM_LOG P8: identical 269 prompt tokens at 130/150/200 DPI). Crop area is the only lever on effective resolution. DPI **is** a byte lever — 200 DPI is 322 KB/page vs 91 KB at 72 — and oversized payloads caused connection resets at high concurrency.

---

## 4. Stage 1 — Structural router (deterministic, zero model cost)

### 4.1 Why positional windows cannot work

UAD 3.6 is a single dynamic URAR replacing the 1004/1073/1025/2055/1004C family. Sections activate and repeat by property characteristics and scope: condo sections appear only for condos, Unit Interior repeats per unit on a 2-4, government-loan fields (Remaining Economic Life, effective age, attic) appear only for FHA/USDA/VA.

**Consequence:** the sales grid is on pages 21–24 in *this* report and elsewhere in the next. A positional window feeds the wrong page to the right schema, and a VLM handed the wrong page does not error — it produces plausible values for fields that aren't there.

This is not hypothetical. PROBLEM_LOG P13 records it happening twice: `improvements` spanned pp. 7–14, the window landed [11,12,13], and `gla`/`bedrooms`/`baths`/`year_built`/quality/condition were **all reported ABSENT** while the call returned valid JSON.

`_run18` ran with `"triage": {"skipped": "positional windows used (VISION_USE_TRIAGE=0)"}`.

### 4.2 The form generator gives you a free anchor

Section tabs are black rounded rectangles rendered by the form engine, not the appraiser. Re-measured across all 40 pages:

- tab left edge at **x ≈ 14.5%** of page width
- page-top tab at **y = 0.0482** — identical on all 38 tabbed pages, zero variance
- bands are **pairs** of dark runs: main band + companion 4–5px below ⚠️ C1
- **width fraction separates kind deterministically: 0.18–0.22 = section tab, 0.70 = row-group** ⚠️ C4 — no model call needed
- `(continued)` italic suffix marks continuation

### 4.3 Detection algorithm — CORRECTED ⚠️

All thresholds are expressed as **fractions of page height**, so the detector is DPI-independent. Verified identical output at 100 / 150 / 200 DPI (70 bands, 50 tabs, 20 row-groups).

```python
def find_section_bands(page_gray):
    """Returns [(y0, y1, kind)]. Deterministic, no model call.

    C1: thresholds are page-height fractions, not pixel constants. The spec's
    `6 <= h <= 40` at 100 DPI sat one pixel above the true minimum and silently
    deleted the `Quality and Condition` row-group on p21 and `Outbuilding` on p22.
    """
    h, w = page_gray.shape
    x0, x1 = int(w * 0.145), int(w * 0.30)
    dark = (page_gray[:, x0:x1] < 90).mean(axis=1)

    runs, start = [], None
    for y, is_dark in enumerate(dark > 0.75):
        if is_dark and start is None:
            start = y
        elif not is_dark and start is not None:
            runs.append([start, y])
            start = None
    if start is not None:
        runs.append([start, h])

    # Each band is a PAIR: main run + companion 4-5px below. Join them.
    gap = int(round(h * 0.0127))
    merged = []
    for s, e in runs:
        if merged and s - merged[-1][1] <= gap:
            merged[-1][1] = e
        else:
            merged.append([s, e])

    lo, hi = int(round(h * 0.0036)), int(round(h * 0.0545))
    out = []
    for s, e in merged:
        if not (lo <= e - s <= hi):
            continue
        out.append((s, e, _band_kind(page_gray, s, e, x0, w)))
    return out


def _band_kind(g, y0, first_run_end, x0, w):
    """C4: kind is geometry, never a model guess. Zero overlap between classes.

    C6: measured as the MEDIAN extent across the rows of the band's FIRST run.
    Three plausible-looking alternatives are all wrong — see §4.3b.
    """
    ink = g[y0:first_run_end] < 90
    extents = []
    for row in ink:
        last, gap = x0, 0
        for x in range(x0, w):
            if row[x]:
                last, gap = x, 0
            else:
                gap += 1
                if gap > int(w * 0.02):
                    break
        extents.append((last - x0) / w)
    frac = float(np.median(extents))
    return "section_tab" if frac < 0.45 else "row_group"
```

### 4.3b The classifier trap ⚠️ C6 — found in implementation

The band-kind measurement looks trivial and has **three** wrong forms, each of which produces a plausible, non-erroring, wrong answer. Measured on the real document:

| Sampling | Result | Why it fails |
|---|---|---|
| Midpoint of the merged band | `width_frac = 0.0` on **every** band | A band is a merged pair; its vertical midpoint lands in the **white gap** between the two runs. Works on the real PDF only because antialiasing fills the gap — fails outright on a cleanly rendered page. |
| Densest row of the merged span | 43 tabs / 27 row-groups | The companion run is the section's **underline rule**, spanning ~0.92 of page width. The densest row is the rule, so tabs classify as row-groups. |
| Single row of the first run | 50/20 at 100 DPI → 47/23 at 150 → **46/24 at 200** | The rule bleeds into the first run at some resolutions. Which rows it occupies moves with DPI, so the classification becomes **resolution-dependent**. |
| **Median across the first run's rows** ✅ | **50/20 at 100, 150 and 200 DPI**; `tabW=[0.18,0.22]`, `rowW=[0.70,0.70]` | A tab's rows all measure ~0.18–0.22 except the one the rule touches. The median ignores it. |

This is the same class of defect as C1 — a geometric constant that is *almost* right, fails silently, and only shows up when you vary something (there, page; here, DPI). Pinned by `test_underline_rule_does_not_reclassify_a_tab`.

### 4.3c Labelling is batched — not one call per band ⚠️ C7

arch-2.0.0 §3.3 says "crop each detected band → one small VLM call per band." On this document that is **~50 calls**, each carrying a sliver of image and returning a handful of tokens — latency dominated entirely by per-call overhead.

**Fourteen band crops compose into one contact sheet that stays legible** (verified: the section vocabulary in §17.1 was read off exactly such sheets). That makes the labelling pass **~4 calls for a 40-page report**, not 50. Detection itself remains free.

Implemented as `_compose_sheet` / `label_bands` in `app/extraction/vision/structural_router.py`.

### 4.4 Fallback when geometry does not hold ⬜

Band geometry is measured on one vendor's renderer. Guard it:

```
IF bands_found == 0 on > 20% of pages          → geometry does not apply
IF grid page-pair band counts are asymmetric   → I11 alarm, do not trust template
   → fall back to: full-page section-label read, one call per page (40 calls, ~1,200 tok)
   → never fall back to positional windows
```

The fallback is more expensive and still correct. Positional windows are cheap and *silently wrong* — never a fallback.

### 4.5 Empirical result — CORRECTED ⚠️

**70 bands: 50 section tabs + 20 row-groups.** Zero-band pages exactly `[1, 38]`.

| Pages | Section tabs | Note |
|---|---|---|
| 1, 38 | **0** | No tab — inherit from previous page |
| 3–6, 9–11, 16–18, 20, 25, 27–37, 39, 40 | 1 | Single section |
| 7, 8, 12, 13, 15, 21–24, 26 | 2 | Section boundary mid-page |
| 2, 14, 19 | 3 | Multiple sections start on one page |
| 21–24 | +5 row-groups each | Grid template — see §17.2 |

**Three findings that matter:**

1. **Sections start mid-page.** Page 19 alone opens Subject Listing Information (y=4.8%), Sales Contract (47.5%) and Prior Sale and Transfer History (74.3%). Header-band-only cropping misses two of three. **Scan full page height.**
2. **Grid row-group bands come free from the same mechanism** — this is the row-label binding `grid_reconcile` lacks (§8.3).
3. **The grid page-pair must be symmetric.** p21/p23 and p22/p24 are structurally identical. Asymmetry is the I11 alarm that exposed C1.

### 4.6 Output

Sections not in the map are **NOT_PRESENT** — a first-class state, not a null. Full measured map in §17.1.

---

## 5. Stage 2 — Driver fields and the applicability model

### 5.1 Why this exists

The GSEs replaced form numbers with a small set of Summary-section data points determining which sections render. This is the *only* legitimate source of N/A. The judge must never infer applicability — that is the documented cause of the false-NA class (see memory: `feedback_llm_judges_no_hardcode`, `project_qc4_condo_extraction_gaps`).

### 5.2 The driver pass

**One call, pages 1–2 only, ~12 fields, before everything else.**

| Driver | This report | Governs |
|---|---|---|
| `construction_method` | Site Built | manufactured (1004C) sections, cost approach requirement (checklist row 153) |
| `attachment_type` | Detached | attached/row sections |
| `project_legal_structure` | (absent) | condo / co-op / PUD sections; **+ HUD Site Condo → 1073 STOP (row 129)** 🆕 |
| `subject_site_owned_in_common` | No | condo site sections |
| `units_excluding_adus` | 1 | Unit Interior repetition, 2-4 income sections |
| `accessory_dwelling_units` | 0 | ADU sections; STOP if units+ADU > 4 |
| `property_valuation_method` | Traditional Appraisal | desktop/hybrid/exterior scope reductions |
| `inspection_type` (ext/int) | Physical / Physical | interior-dependent checks |
| `assignment_reason` | Purchase | refinance-only checks (EQ-63) |
| `financing_type` (from contract) | Conventional ✅ | **entire FHA block (17 sub-items + 2 preconditions)** |
| `occupancy` | Vacant | tenant-occupied checks |
| `is_pud / condo / coop / condop` | all No | EQ-60, 61, 62, 81 |

### 5.3 Applicability resolution — the three-way rule

```
driver says section NOT required          → NOT_APPLICABLE      (silent, no card)
driver says required + section_map has it → must extract; failure is UNREAD
driver says required + section_map lacks  → REPORT DEFECT       (real finding, FAIL)
```

**This is the whole N/A problem, solved.** No judge improvisation. On this report the rule produces, deterministically: FHA block N/A (`financing_type = Conventional` ✅), PUD items N/A (`is_pud = No`), EQ-63 N/A (`assignment_reason = Purchase`), EQ-26 N/A (`converted_area = None`), cost approach N/A (`construction_method = Site Built`) — 6 checklist items plus **17** FHA sub-items ✅.

**Note the leverage:** the FHA block being N/A suppresses nine findings that would otherwise fire (no attic/crawl statement, no appliance or mechanical operability statements, no remaining-economic-life figure, no well/septic distance commentary). If the order is re-cast as FHA, all nine fire **and** the septic issue becomes a mandatory "subject to". Applicability is not cosmetic — it is most of the verdict.

### 5.4 Checkbox extraction rule

`is_pud_checked = "Planned Unit Development (PUD)"` is the row **label**, not the state. Fix:

```json
{"row_label": "Planned Unit Development (PUD)",
 "yes_box": "checked|unchecked",
 "no_box":  "checked|unchecked"}
```

Validator: `yes_box XOR no_box`. Both or neither → **NOT_FOUND → rescue → VERIFY**. Never default to False. This form has ~30 such pairs (p1×5, p2×8, p7, p13×2, p15, p19×3 ✅ confirmed on p19: *Is there a sales contract? / Was sales contract information analyzed? / Does this appear to be an arm's length transaction?*).

---

## 6. Stage 3 — Extraction

### 6.1 Region types

| Kind | Ceiling | Output | Validator |
|---|---|---|---|
| **scalar_region** | 600 tok | typed key/value | enum + type + label-match |
| **narrative_region** | 400 tok | **verbatim text, no JSON nesting** | length > 0, no truncation marker |
| **checkbox_region** | 200 tok | label + yes/no pair | XOR |
| **grid_region** | 700 tok/comp/page | positional array | row-label binding + sum |
| **exhibit_region** | 250 tok | caption list + **embedded-table values** 🆕 | count ≥ 1 |

### 6.2 The narrative rule

`contract_history` requested 22 structured fields, blew 6,500 tokens, truncated, retried at 12,000, died. Split it:

- **5 scalars** (contract_price, contract_date, sale_type, list_price, dom) → `scalar_region`, 300 tok
- **1 narrative** (`contract_analysis_comment`) → `narrative_region`, verbatim, 400 tok
- **1 table** (`listing_price_history`) → `grid_region`, 300 tok

Same content, ~1,000 tokens instead of 6,500, no truncation possible.

**Narrative fields in this form** (all verbatim, never schematised):
`contract_analysis_comment`, `prior_sale_analysis_comment`, `listing_history_analysis`, `market_conditions_commentary`, `price_trend_commentary`, `sketch_commentary`, `quality_condition_reconciliation`, `final_reconciliation_comment`, `apparent_defects_*` (every instance).

The septic finding lives in `contract_analysis_comment`. It was lost twice over: the field was never extracted, **and** `adverse_conditions='None'` was boolean-coerced to `False`, destroying the literal on the other side of the contradiction.

### 6.3 Provenance — I10 ⚠️ C8, mechanism corrected

**arch-2.0.0 and this spec's own §1.1 both diagnosed this wrong.** The claim was "section path 0-based, grid path 1-based" and "the model is asked to self-report a number only the caller knows." Neither is what happens.

The code already maps caller-side: the model reports `image_index` (a 1-based index into the images *it was handed*) and `_page_of` resolves that against the uploaded page list. That design is correct.

The real mechanism is the **positional window's left edge used as a provenance default**:

```python
centre = round(page_hint * (len(extractable) - 1))
pages  = extractable[max(0, centre - 1): centre - 1 + 3]   # window starts BEFORE the section
...
return pages[0]        # ← fallback when the model omits image_index
```

Because the window is centred on the hint and then widened by `centre − 1`, `pages[0]` is systematically **one page before the section's true start**. Every observed delta reproduces exactly:

| section | `page_hint` | window | `pages[0]` | true page | delta |
|---|---:|---|---:|---:|---:|
| assignment | 0.02 | [1,2,3] | 1 | 2 | −1 |
| dwelling_exterior | 0.15 | [6,7,8] | 6 | 7 | −1 |
| reconciliation | 0.64 | [25,26,27] | 25 | 26 | −1 |
| value_reconciliation | 0.82 | [32,33,34] | 32 | 33 | −1 |
| appraiser | 0.97 | [38,39,40] | 38 | **40** | **−2** |

The appraiser −2 needs no special explanation either: same mechanism, the signature simply sits two pages past the window's left edge.

**Two consequences.**

1. **The structural router fixes most of this for free.** Once `pages` is the section's *true* page list rather than a 3-page guess, `pages[0]` is the section's real first page.
2. **The fallback must still not guess silently.** A page nobody established is not page `pages[0]` — it is unknown (I3). Emit `page_exact: false` so a reviewer's click-to-scroll and an AMC reject letter can tell a citation from a default.

`comparable_count` carried `page: 0`, an invalid sentinel under either convention — the tell that nothing validated the field.

### 6.4 Crop-based resolution for dense alphanumerics

Image tokens are ~constant per image after server-side downscale, so a crop of 1/9 page area delivers ~3× linear resolution **at the same cost**.

Mandatory crop targets: APN / legal description block (`JOB` ← `J08`), all checkbox column pairs, grid numeric columns, license number and expiry (p37, p40), all dates (`09/25` ← `09/29`), **and embedded exhibit tables (N1 — the MLS history is legible only at high crop factor)** 🆕.

### 6.5 Grid extraction — one call per comp per page-pair

Current: 12 calls, each comp read twice. 42,939 output tokens — **53% of the entire run**.

Correct: **6 calls**, one per comp, both pages of the pair in the same call. The comp column header and `Property Address` row repeat on both pages — use address as the **join key** so column binding survives the page split.

Column geometry is **measured, never assumed** (PROBLEM_LOG P22): `detect_grid_columns()` recovers boundaries from the page's own rules as the longest arithmetic progression among horizontal-rule endpoints, then snaps predictions onto real drawn coordinates. The grid occupies `x ∈ [0.153, 0.847]` in five equal columns of 0.1385 — *not* the full page width with a 28% label column, which is what caused a comp-1 crop to clip its own address and include 62% of comp 2.

Output as positional arrays keyed to the row-label list:

```json
{"comp_index": 4,
 "address": "412 Perry Rd, Armuchee, GA 30105",
 "row_group": "Unit(s)",
 "rows": [["Bedrooms","4",null],
          ["Baths - Full | Half","2 | 0","$9,000"],
          ["Finished Area Above Grade","1,884 Sq. Ft.","$10,600"]]}
```

The three-tuple `[label, value, adjustment]` makes transposition **detectable** — §8.3.

---

## 7. Stage 4 — Fact store

### 7.1 Record shape

```yaml
site.apparent_defects:
  literal: "None"                    # I4 — always first, never overwritten
  derived:
    has_defects: false               # additive
  state: PRESENT                     # PRESENT | PRESENT_EMPTY | NOT_PRESENT | UNREAD
  page: 3                            # stamped by caller — I10
  region: site.defects
  reads: [{pass: 1, value: "None"}, {pass: 2, value: "None"}]
  agreement: true
  confidence: verified               # verified | single | unverified | unread
```

`confidence` is **categorical, not a float**. `0.93` on every field and `0.55` on every comp_6 field carries no information — it is a constant per code path, and in comp_6's case a *wrong* constant applied to 48 correct values.

### 7.2 Multi-observation facts

Achieved **1.09 observations per fact** against a 3.4 design — both GLA sources were on page 7, the same read double-counted. Register observation **sites**, not field aliases:

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
| **DOM** 🆕 | p19 listing table (8 / 197 / 205), **p19 MLS exhibit (7 / 188)** — N1 |

Majority vote across genuinely independent reads; any dissent → VERIFY with all observations cited.

**Arithmetic beats pixels on ambiguous digits.** The sketch states a Level-1 total of 2137.35; three clear line items sum to 2039.49; the fourth must therefore be 97.86 — so 97.87 is right and 97.07 is a misread, settled by subtraction without re-reading the page.

---

## 8. Stage 5 — Deterministic verification (no model)

Runs before evaluation. Exact, reproducible, free.

### 8.1 Identity checks

`gla == total_living_area == grid_subject_gla`; room counts vs sketch; area chain (outbuilding 253.85→254, carport 329.26, deck 249.38→249, porch 272); DOM `197+8=205` **against the table, and separately against the exhibit — N1** 🆕; signature date ≥ effective date; cert expiry > effective date.

### 8.2 Grid arithmetic — must be comp-class aware

Per comp: `Σ line adjustments == net_printed`. Across set: weights sum to 100%; `Σ(adjusted × weight) == final value`; supported range contains final value.

**The base-price identity depends on comp class.** This is what discarded a correct comp_6 read:

```
closed sale       → adjusted == sale_price  + net
pending / active  → adjusted == list_price  + net    ← comp 6: 349,900 − 8,200 = 341,700 ✅
```

The report states this methodology itself (p32, *Active / Pending / Contingent listings*): the Final Sale-to-List ratio applies to pendings, the Original Sale-to-List ratio to actives. **Branch on `listing_status` before selecting the identity.** A comp whose class has no identity rule is a **verifier gap**, not an UNREAD region — never downgrade its confidence (I9).

### 8.2b Field-level presence

`missing: []` on a region that silently dropped `comp_3_vehicle_storage_adjustment` is a lie. The extraction plan must enumerate **expected keys per region**; the region reports `expected − returned` as missing. An adjustment cell containing `$0` and one never read are different facts (I3), and only the row-label template can tell them apart.

Known silent per-field gaps in `_run18`, all inside regions reporting `missing: []`: `comp_3_vehicle_storage_adjustment` ($0 in the PDF), `comp_2_heating_cooling_adjustment`, `comp_6_net_adjustment_total`.

### 8.3 Row-label binding — the transposition fix

Sum is invariant to permutation. `comp_4` had the contract-date adjustment sitting in the concessions row and still returned CERTIFIED.

```
1. Expected row-label template per row_group, derived from the grid_region bands (§4.5, §17.2)
2. Every returned triple must bind to exactly one template label
3. Template labels present on the page must all be bound — no gaps
4. Adjustment values must attach to their own label, not a neighbour's
5. Unbound or duplicate label → region UNREAD → rescue
```

⚠️ **This step is why C1 is critical.** With the spec's original detector the template is missing `Quality and Condition` (p21) and `Outbuilding` (p22) — so the outbuilding adjustments behind FAIL 2.6 would be unbindable, and step 3 could never fire (N5).

### 8.4 Rate-consistency derivation

Fit implied rates and compare to stated support: GLA $/sqft, lot $/sqft, per-bath, per-garage-space, pool, condition step.

On this report this derivation produced **FAIL EQ-94** (stated $8,500/garage vs applied $6,000 and $3,500) and **downgraded EQ-77 from FAIL to VERIFY** by proving the time adjustments reconcile to the p16 trend matrix. Both outcomes are correct; **neither is reachable by a model.** This is the single clearest argument for I5.

### 8.5 Ratio computation

Net %, gross %, largest-line % per comp, against a per-AMC threshold table (§10.3).

---

## 9. Stage 6 — Evaluation

The evaluator sees the **fact store as text**, never an image, and holds all sections simultaneously. This is the only layer where cross-page findings can exist.

The septic finding requires `site.apparent_defects` (p3) + `unit_interior.utilities_operating` (p8) + `contract.analysis_comment` (p19) + `reconciliation.value_condition` (p26). **Every one of those pages passes in isolation** — a page-scoped verdict returns PASS on the most serious issue in the report. That is the geometric argument for I1, and it matches TRACKER §4h: 54% of the checklist needs cross-page fusion, 25% is single-page, and *no finding in the audit came from a single page*.

### 9.1 Evaluator taxonomy — CORRECTED ⚠️

| Type | Definition | Engine | Missing-fact policy |
|---|---|---|---|
| **A** | Single-field lookup / enum test | code | rescue → VERIFY |
| **B** | Cross-field identity or equality | code | rescue → VERIFY |
| **C** | Aggregate over the comp set | code | partial credit, name the gap |
| **D** | Artifact **presence** (photo, graph, exhibit) | code over caption index | rescue that page |
| **D2** 🆕 | Artifact **data** — values inside an exhibit | crop + extract, then treat as a fact | rescue that crop |
| **E** | Narrative-grounded judgment | LLM over retrieved spans | VERIFY (honest) |
| **F** | Field-vs-narrative **or field-vs-exhibit** contradiction | contradiction pass | both sides required |
| **G** | External-document dependency | none | NOT_DETERMINABLE by design |
| **H** | Policy threshold / investor criteria | threshold table + LLM | VERIFY |

**D2 is new (C5/N2).** Type D as originally defined answers "is a photo there?" It cannot answer N1 (DOM 188 vs 197) or A3 (210 vs 44 sales), because those live in *values inside an exhibit*. Without D2 the exhibit is write-only evidence.

### 9.2 ESA checklist classified (all 91) ⬜

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

**A+B+C+D = 70 of 91 = 77% requires no LLM.** Only 12 items (E+F) need language judgment; 9 (G+H) are structurally VERIFY or policy lookups.

This ratio is the profitability lever **and** the determinism lever — 77% of verdicts become byte-identical across runs, which is the precondition for `auto_pass_enabled: true`. It is ⬜ unvalidated on a second AMC.

### 9.3 Type D must never use text logic

"Are the required photos included?" is a **caption-index membership test**, not a question about text absence:

```yaml
exhibit_index:
  - {page: 5,  caption: "Property Access (Street Scene) - Street view"}
  - {page: 7,  caption: "Dwelling Front - Side View"}
  - {page: 8,  caption: "Dwelling Rear - Rear View"}
  - {page: 8,  caption: "Dwelling Rear - Septic Tank"}
```

Then EQ-33 = `require_any(["front"]) ∧ require_any(["rear","back"]) ∧ require_any(["street"]) ∧ comp_front_count == comparable_count`.

### 9.4 Type F — the contradiction pass

Runs independently of the checklist and produces findings the checklist has no item for. On this report it caught the $330,000 vs $310,000 subject list price ✅, 210 vs 44 sales, the comp 3 address typo, the 11.4%-vs-6.1% reduction arithmetic — **and, once D2 exists, N1's DOM conflict** 🆕. None map to an ESA item.

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
    a: subject_listing.current_list_price      # p19 pending = 310,000
    b: grid.subject_list_price                 # p21/23      = 330,000
    rule: equal
    severity: FAIL

  - id: CX-SAMPLE-SIZE
    a: market.sales_past_12mo                  # 44
    b: market.trend_commentary.sample_n        # 210
    rule: equal
    severity: VERIFY

  - id: CX-DOM-EXHIBIT                          # 🆕 N1
    a: subject_listing.dom[*]                   # table: 8, 197
    b: exhibit.mls_history.dom[*]               # exhibit: 7, 188
    rule: equal
    severity: VERIFY
    note: DOM definitions can differ legitimately (calendar vs post-Coming-Soon).
          Require the report to reconcile, do not assert which is correct.
```

Contradiction pairs are **AMC-independent** — they belong to the UAD 3.6 form, so every AMC inherits them free. This is a differentiator a per-check checklist model cannot express.

---

## 10. The Checklist IR — the AMC-agnostic layer

`checklist_compile.py` targets this IR; the evaluator only ever reads the IR.

### 10.1 Item schema

```yaml
- id: EQ-87
  source_text: "Is the subject bathroom count bracketed by the comparable sales?"
  type: C
  polarity: expect_true
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
  applicable_when: drivers.is_pud == true      # ← N/A computed, never inferred
  on_missing: rescue
  on_false: FAIL
```

### 10.2 Polarity is mandatory

ESA mixes expectation directions: EQ-16 ("Is the zoning legal non-conforming or illegal?") expects **No**; EQ-20 ("Was ANSI used?") expects **Yes**. TRACKER §4i counts **~34 of 90** items as "Yes = a problem" and calls the missing polarity column *"the single biggest silent failure mode."* Project memory independently records empty `expects:` fields as a known false-positive class.

In the IR, `polarity` is a **required** field — compile fails without it. That one constraint eliminates the class.

### 10.3 Per-AMC parameter table

Thresholds are data, not code. A new AMC is a YAML file, not a release.

```yaml
amc: equity_solutions_usa
thresholds:
  comp_distance_miles: {urban: 1.0, suburban: 2.0, rural: 5.0}
  adjustment: {net_pct: 15, gross_pct: 25, line_pct: 10}
  comp_contract_age_months: 12
  fha_comp_123_age_months: 12          # 🆕 N6 — checklist row 135, hard under FHA
  min_closed_comps: 3
  min_data_sources: 2
  condition_stop: [C5, C6]
  quality_acceptable: [Q1,Q2,Q3,Q4,Q5]
  max_units_incl_adu: 4
stop_conditions: [form_type_mismatch, condition_c5_c6, hbu_not_present_use,
                  illegal_use, units_exceed_4, hud_site_condo_not_1073]   # 🆕 N3 row 129
reject_language_mode: amc_language_bank
reject_language_template: |                                               # 🆕 N4 row 157
  Hello {appraiser_name},

  Equity Solutions USA has performed a Quality Control Review for the property
  located at {subject_address} and found the following results which require
  your comments or revisions:

  {numbered_findings}

  When your revisions and/or comments are ready, re-deliver the report the same
  way you originally delivered it. Per USPAP, the date of the revised report
  should be {revision_date_rule}.
```

### 10.4 Known checklist defects to carry explicitly

From TRACKER §4i, all still open. **Do not silently patch — carry the corrected rule and have the AMC confirm.**

| Defect | Impact |
|---|---|
| No polarity column (~34 of 90 inverted) | The single biggest silent failure mode — §10.2 |
| **Item 70 logic inverted** — CSV requires commentary when comps are UNDER the mileage guideline; it is required when OVER | Fires on this very report (comp 3 at 7.59 mi) |
| Missing thresholds — item 52 (median DOM "reflective of an active market?" — 63 days, yes or no?), items 47/48 ("meet investor criteria" — which investor?) | The judge must never improvise a threshold |
| Compound items — 16 and 63 each ask two questions | Split at compile time, or one half silently decides both. *(`49b` in the verdicts CSV shows the split already happening ad hoc)* |

### 10.5 Onboarding a new AMC

1. Map each raw question → `type` + `requires` + `polarity` (the only manual step)
2. Fill the threshold table and reject-language template
3. Run the coverage gate (§11)
4. Run the golden-set regression (§15)

No extraction change. No prompt change. **The fact store is AMC-independent by construction** — which is also why a checklist recompile must never invalidate stored packets in the replay harness.

---

## 11. The coverage gate — build-time, not runtime

This is the mechanism that answers *"without failing a single time."*

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

A checklist that references a fact nobody extracts **cannot ship**. You cannot guarantee the model reads every page correctly; you *can* guarantee no check ever fails because the data path was never built. That is the failure class actually being hit.

Runtime companion:

```
required_facts = ∪ requires of all applicable items
resolved_facts = fact store entries with state ∈ {PRESENT, PRESENT_EMPTY, NOT_PRESENT}
coverage       = |resolved| / |required|
IF coverage < 1.0 AND rescue exhausted → run status = INCOMPLETE, emit no verdicts
```

`_run18` reported `DONE` and `coverage 125.7%` because it counted fields **emitted** (357) against schema **size** (284) ✅. Under this definition the same run reports `INCOMPLETE, coverage 0.71` — the truth. Coverage must also be computed **after** suppression: `357 merged (4 suppressed)` vs `DONE — 353 fields` with coverage taken pre-suppression is a third inconsistency in the same block.

---

## 12. The rescue ladder

Budget is not a constraint. VERIFY is the **last** step.

| Step | Action | Cost |
|---|---|---|
| 1 | Re-read region, split in half, ceiling halved | ~2 × 300 tok |
| 2 | Field-targeted re-read: that page, only the missing keys | ~150 tok |
| 3 | Crop the row/column region, 3× effective resolution | ~150 tok |
| 4 | Second independent pass; disagreement → VERIFY (never tie-break) | ~150 tok |
| 5 | VERIFY tagged **UNREAD**, page cited, cause recorded | 0 |

Run step 4 **unconditionally** on: all checkbox pairs, all grid numerics, all Type A/B facts, license number, all dates, APN. That is the `auto_pass_enabled` precondition (I8).

**On truncation → SPLIT, never raise `max_tokens`.** `_run18` retried at 9,200 then 12,000 tokens with `splits: 0` — the split path never fired. This matters more on a reasoning model: exhausting the ceiling mid-reasoning returns an **empty** `content` with HTTP 200 — full latency paid, full tokens billed, every field in the call gone, and nothing in the response says so.

---

## 13. Verdict algebra and deduplication

```
NOT_APPLICABLE   ← applicable_when false (driver-derived only)
PASS             ← predicate true AND all inputs confidence ∈ {verified}
VERIFY           ← predicate true but inputs confidence = single/unverified
                 | type E/H
                 | any input UNREAD after rescue
                 | two passes disagree
NOT_DETERMINABLE ← type G: answer lives outside the appraisal (loan file, title)
FAIL             ← predicate false with all inputs verified
INCOMPLETE       ← coverage < 1.0 (run-level; suppresses all verdicts)
```

**`NOT_DETERMINABLE` is distinct from VERIFY** (TRACKER §4i). VERIFY = a human must exercise judgment. NOT_DETERMINABLE = no amount of reading the appraisal settles it. Different queue, different reviewer action. Items 2, 5, 7 upgrade out of it as soon as engagement-letter fields are bound — SHAL already ingests those documents.

**Dedup by `dedup_group`.** The septic root cause satisfies EQ-19, 95, 98, 99. Emit **one** card with four checklist references — project memory records duplicate cards from one underlying field as a known false-positive class.

**Reject language** carries `mode` from §10.3, renders into the AMC template (N4), and never embeds instance values — comp numbers, dollar amounts and dates are `{slots}` filled at render time.

---

## 14. Grid verification outcomes — the four-state rule (I9)

```python
class CheckOutcome(Enum):
    VERIFIED       = "verified"        # ran, passed
    FAILED         = "failed"          # ran, failed        → lower confidence
    NOT_APPLICABLE = "not_applicable"  # rule doesn't apply to this comp class
    SKIPPED        = "skipped"         # no rule exists      → VERIFIER GAP, not a data problem
```

Only `FAILED` may lower confidence. `_run18` collapsed `SKIPPED` into `verified: false` and propagated 0.55 confidence to **48 correctly-read comp_6 fields** ✅, converting a verifier gap into a false VERIFY on every check touching the listing comp.

`SKIPPED` must be **loud** — it is a backlog item ("write the pending-listing identity rule"), not a data quality signal.

---

## 15. Concurrency, timeout, budget

### 15.0 Measured — runs 19, 20, 21 ✅ 🆕

Four live runs on the same 40-page report, same 4 keys, same models.

| | run 18 | run 19 | run 20 | **run 21** |
|---|---:|---:|---:|---:|
| **Wall clock** | 602.8s | 1806.1s | 327.2s | **220.9s** |
| Slowest call | contract_history 592.9s | contract_history 1782.5s | market 299.7s | **contract_history 199.8s** |
| `peak_in_flight` | 23 | 16 | 9 | 10 |
| Fields | 357 | 116 | 365 | 353 |
| Input tokens | 57,938 | 103,915 | 82,669 | 91,661 |
| Output tokens | 80,251 | 65,972 | 96,266 | 94,745 |
| Grid | 5 CERT + 1 UNREAD | 2 PARTIAL | 5 CERT + 1 CONFLICT | **6 CERTIFIED** |
| Regions verified | 7/8 | 2/4 | 7/8 | **8/8, 0 failed** |
| Cost | $0.1004 | $0.1045 | $0.1256 | $0.1277 |

**Run 19 is the load-bearing measurement, and it refutes this document's §15.3.** Output tokens *fell 15%* while wall clock *rose 2.8×*. The token bucket predicts 168s for 67,870 tokens; the run took 1,806s. **~90% of the run was stall, not generation** — so the whole 80,251 → 27,300 token plan was optimising the wrong variable. Halving tokens against a 90% stall share would have moved 1,806s to roughly 1,700s.

**Three defects, all found in run 19, all fixed:**

| # | Defect | Evidence | Fix |
|---|---|---|---|
| **L1** | `concurrency` handed to the section pool AND the grid pool, which run simultaneously — the limit was spent twice | asked 8, measured `peak_in_flight: 16` = 4/key; 9 of 12 grid calls died on read timeouts | Global `BoundedSemaphore` in the **provider**, the only object both pools share |
| **L2** | Split recursion unbounded in time and **sequential**; each half kept the **full** ceiling | `market` = 1,566s of a 1,667s run; 14 splits | Per-section deadline (240s) over the whole tree, halves run concurrently, ceiling halves per level |
| **L3** | Split depth unbounded, and **every split re-uploads the page images** | +3,003 input tokens per split; +73% input for −15% output | `_MAX_SPLIT_DEPTH = 2` |

L2's parallel halves are only safe *because* L1 exists — nested pools without a global gate is precisely what produced 16-in-flight.

**Result: 602.8s → 220.9s, with all six comparables certifying arithmetically for the first time** (comp_6 at `net = lines = −8,200`, the comp-class fix in §8.2 proven live).

**L4 — the two budgets did not know about each other.** Run 22 then measured a slowest call of **301.2s inside a 240s section deadline**, for a 530.4s run. The deadline gates *entry* to a call; the provider then spends its own independent 300s allowance, so a call admitted at 239s still runs to 539s. Fixed by passing the section's remaining time down as `budget_s`, which the provider takes the min of. Run 23: slowest call **130.6s**, run **256.9s**.

| run | wall | slowest call | peak_in_flight | grid |
|---|---:|---:|---:|---|
| 20 | 327.2s | 299.7s | 9 | 5 CERT + 1 CONFLICT |
| 21 | 220.9s | 199.8s | 10 | **6 CERTIFIED** |
| 22 (pre-L4) | 530.4s | **301.2s** | 8 | 2 CERT + 2 PART + 2 UNREAD |
| 23 (post-L4) | **256.9s** | **130.6s** | 8 | 5 CERT + 1 UNREAD |

⬜ **Four post-fix runs, one document, spanning 220.9s–530.4s.** That establishes the mechanisms, not the effect size — variance is larger than any single improvement claimed here. The three-order rule still applies, and orders 2 and 3 must be *different documents*.

### 15.1 The governing equation — treat with suspicion ⬜

arch-2.0.0 asserts `wall_clock = total_output_tokens / (keys × 101)`. **PROBLEM_LOG P19b measured this false:** run 14 did 74,708 tokens ÷ 546.5s = **137 tok/s aggregate on 4 keys**, not 405. Per-call decode ran 25–61 tok/s. And every call starts at t=0, so **the run ends when its slowest single call ends**, not when a shared bucket drains. The equation predicted 185s; the run took 555s.

Use it as an optimistic lower bound only. Plan against the slowest-call model:

```
wall_clock ≈ max over calls of (call_ceiling / decode_rate_at_that_concurrency)
```

### 15.2 Rules

```
in_flight ≤ 2 × keys            (8 concurrent at 4 keys; queue the rest)
timeout   = (ceiling / rate_at_current_concurrency) × 1.5, computed per call
on truncation → SPLIT, never raise max_tokens
retry on error code only, NEVER on timeout
hard 300s wall-clock budget per logical call, covering all retries and backoff
```

**A read timeout is not a 5xx and must not be retried like one.** A 5xx means the request was rejected and nothing is running. A read timeout means it was accepted and the model *is* generating — re-posting abandons work in progress, pays the upload again, and usually ends the same way. Run 14's longest item was `grid:comp6` at **546.5s returning nothing**: three consecutive 180s timeouts with backoff, each re-uploading ~1.5 MB.

⚠️ **Note the tension with P24.** arch-2.0.0 says "fewer concurrent calls finish this report faster." PROBLEM_LOG run 17 tested exactly that — concurrency 20 → 8 — and got **worse** (494s vs 310s), because narrowing the pool serialises into waves. Run 18 went back to 20 and produced the best result on record (12/12 grid calls). **The three knobs are not independent:** read timeout must cover the ceiling, the ceiling must cover the call, and how fast a call spends its ceiling depends on contention. Tune them together, and measure — do not assume the §15.2 numbers transfer.

### 15.3 Budget projection ⬜

| Bucket | Old | New (projected) | How |
|---|---:|---:|---|
| Structural router | 0 | 900 | new, pays for itself |
| Driver pass | 0 | 400 | new |
| Grid | 42,939 | 8,400 | 6 calls not 12; positional arrays |
| Narrative sections | 17,521 | 3,200 | verbatim blocks, 400 cap |
| Scalar sections | 19,791 | 9,000 | tightened schema |
| Checkbox micro-calls | 0 | 2,400 | new, ~30 pairs |
| Second pass (high-risk) | 0 | 3,000 | new |
| **Total** | **80,251** | **~27,300** | |

**This is a hypothesis, not a plan input — and §15.0 now shows it is aimed at the wrong variable.** Run 19 cut output tokens 15% and got 2.8× *slower*. Token reduction is a cost lever, not a latency lever, until the stall share is small. Re-measure the stall share before spending effort here: at 90% stall, halving tokens buys ~5%.

The previous projector predicted 24,600 against 80,251 actual — a 3.3× miss that made `cap_usd` structurally unable to fire in time ✅. Gate any new projector: log projected-vs-actual per bucket on every run and alarm at >1.5× drift.

Cost is not the binding constraint at any of these numbers — every run so far sits at $0.10–0.13 against a $0.75/order cap (13–17%). **Latency is, and it was concurrency and split policy, not tokens.**

---

## 16. Regression harness

Extraction and evaluation version independently:

```
packet   = {section_map, driver_fields, fact_store, exhibit_index}   ← versioned, replayable
verdicts = evaluate(packet, checklist_ir, thresholds)                ← pure function
```

Because `evaluate` is pure over a stored packet, **a checklist recompile is testable with zero model calls.**

| Gate | Threshold |
|---|---|
| Golden-set field accuracy | ≥ 99.5% on Type A/B facts |
| Verdict diff vs human-reviewed baseline | 0 unexplained FAIL flips |
| Determinism | 3 consecutive runs, byte-identical on A+B+C+D items |
| Coverage | 1.0 on every golden order |
| **Router symmetry (I11)** 🆕 | grid page-pair band counts equal; total bands == 70 on the Turner Rd fixture |
| **Band-detector fixture** 🆕 | synthetic PDF with a 5px band at 100 DPI must be detected — pins C1 shut |
| Wall clock | p95 < 60s ⬜ (see §15.1 — currently 310–602s) |

Seed the golden set with this report: it carries a cross-document contradiction, a stated-vs-applied support conflict, two unbracketed dimensions, a mislabeled adjustment row, five internal data conflicts (four known + N1), and a fully N/A FHA block.

**Precision and coverage are never blended** — guessing more raises coverage and lowers precision, and one number hides the trade.

---

## 17. Build order

Ordered by dependency, with the verification status of the reasoning behind each.

Status re-checked against the working tree on 2026-08-12. Several steps were already done before this spec was written.

| # | Change | Status | Where |
|---|---|---|---|
| 1 | Cap in-flight per key; per-call timeout; retry on error code only | ✅ **done** | commit `5e9a0e8`; `vision_calls_per_key=2` |
| 2 | Split on truncation; delete the raise-ceiling path | ✅ **done** | commit `5e9a0e8` — "split, always. Never raise" |
| 3 | Stop boolean-coercing free text; literal-first storage (I4) | ✅ **done** | `plausibility.py` — `_is_exclusion`, declared `exclusion_values` |
| 4 | Narrative regions as verbatim blocks | ✅ **done** | `vision/narrative.py` |
| 5 | **Four-state check outcome (I9)** + comp-class base price | ✅ **done this pass** | `verify.py::base_price`, `VerifyResult.not_applicable`, `verifier_gap` |
| 6 | **Honest provenance (I10)** — stop defaulting to the window's left edge | ✅ **done this pass** | `sections.py::_page_of` → `page_exact`; `runner.py` → `location_quality` |
| 7 | **Structural router (§4.3)** + symmetry alarm (I11) + fallback (§4.4) | ✅ **built, flag-gated** | `vision/structural_router.py`; `VISION_USE_STRUCTURAL_ROUTER=0` |
| 8 | Checkbox label/value discrimination | ✅ **done** | `plausibility.py::_echoes_own_label` |
| 9 | Driver pass + three-way applicability | ☐ **next** | — |
| 10 | Checkbox XOR pairs (yes_box/no_box, never a bare bool) | ☐ | — |
| 11 | Row-label binding in `grid_reconcile`, fed by §17.2 template | ◐ partial — `expected_rows` exists; not yet fed from the router | `verify.py::reconcile_comp` |
| 12 | Coverage gate + INCOMPLETE status; fix coverage denominator | ✅ **done** | commit `5e9a0e8`; `coverage_detail`, `status: INCOMPLETE` |
| 13 | Field-level expected-key presence (§8.2b) | ☐ | — |
| 14 | Checklist IR + evaluator types A–H **+ D2** | ☐ ⬜ one checklist | — |
| 15 | Contradiction pass incl. CX-DOM-EXHIBIT | ☐ | — |
| 16 | Rescue ladder + unconditional second pass | ◐ partial — split/retry done, no crop or second-pass step | `vision/resilient.py` |
| 17 | Model the three unmodelled checklist zones (N3) + AMC reject template (N4) | ☐ | — |

**Steps 1–8 and 12 are complete.** Together they are the set that "alone would have produced a correct review of this report."

**Validation gate for step 7.** Detection is pinned by 18 tests including a synthetic 5px band and a DPI sweep, and `route()` is proven end-to-end against a stub provider. What has *not* run is the labelling pass against the live provider — hence the flag. To promote it:

```bash
VISION_USE_STRUCTURAL_ROUTER=1  # then check the run report:
#   meta.structural_router.health == []          (I11 clean)
#   meta.structural_router.bands.unlabelled == 0
#   section_pages matches Appendix 17.1
```

---

## Appendix 17.1 — Measured section map (Turner Rd, 40pp)

21 sections. Derived from 50 detected `section_tab` bands. ⚠️ arch-2.0.0 §3.5 listed 18 and omitted the two marked 🆕.

| Section | Pages |
|---|---|
| *(cover / summary — no tab)* | 1 |
| Assignment Information | 2 |
| **Subject Property** 🆕 | 2 |
| Site | 2, 3, 4, 5 |
| Sketch | 6, 7 |
| Dwelling Exterior | 7, 8 |
| Unit Interior | 8, 9, 10, 11, 12 |
| **Functional Obsolescence** 🆕 | 12 |
| Outbuilding *(printed `Outbuilding - Outbuilding`)* | 13 |
| Vehicle Storage | 13, 14 |
| Subject Property Amenities | 14 |
| Overall Quality and Condition | 14 |
| Highest and Best Use | 15 |
| Market | 15, 16, 17, 18 |
| Subject Listing Information | 19 |
| Sales Contract | 19 |
| Prior Sale and Transfer History | 19, 20 |
| Sales Comparison Approach | 21, 22, 23, 24, 25, 26 |
| Reconciliation | 26 – 35 |
| Supplemental Information | 36, 37, 38 *(38 inherited — no tab)* |
| Certifications | 39, 40 |

## Appendix 17.2 — Grid row-label template (the transposition fix)

20 `row_group` bands, 5 per grid page, symmetric across both page-pairs. **Two of these are invisible to arch-2.0.0's detector (C1) — marked ⚠️.**

| Page pair | Page A (p21 / p23) | Page B (p22 / p24) |
|---|---|---|
| 1 | General Information | Overall Quality and Condition (Ratings: 1-6, 1 is highest) ⚠️ |
| 2 | Site | Property Amenities |
| 3 | Dwelling(s) | Vehicle Storage |
| 4 | Unit(s) | **Outbuilding** ⚠️ *(ADU and vehicle storage not included)* — N5 |
| 5 | Quality and Condition (Ratings: 1-6, 1 is highest) ⚠️ *(p21 only)* | Summary |

Comps 1–3 on p21/p22; comps 4–6 on p23/p24. Merge by comparable number across the pair; join on `Property Address`, which repeats on both pages.

## Appendix 17.3 — Checklist zones (N3)

The ESA checklist is **not** 90 questions. It is five zones, and four of them are unmodelled.

| Zone | CSV rows | Count | Modelled? |
|---|---|---:|---|
| STOP conditions | 1–5 | 5 | partial — in review prose, not in IR |
| Numbered questions | 6–126 | 90 (+`49b` split = 91) | ✅ yes |
| FHA preconditions | 128, 129 | 2 | ❌ no — row 129 is a driver-derived STOP |
| FHA requirements | 132–149 | **17** | ❌ no — N/A on this order, but must exist |
| Cost Approach | 153 | 1 | ❌ no — driver-derived on `construction_method` |
| Reject-language template | 157 | 1 | ❌ no — N4, the render target |

Numbered-item gaps (ids absent from the CSV, confirmed identical in the verdicts file): `3, 4, 25, 27, 28, 38, 39, 88, 89, 96`.

## Appendix 17.4 — Where the 3.6 catalog actually stands 🆕

Measured from `config/qc_catalog_uad36.yaml` (90 items) on 2026-08-12. §9.2 argues 70 of 91 items *can* be decided by code; this is how many *are* bound to it today.

| Dimension | Distribution |
|---|---|
| `check_type` | `same_section` 40 · **`unbound` 30** · `visual` 14 · `cross_document` 6 |
| `proof` | **`none` 87** · `bracketing` 3 |
| `polarity` | `yes` 54 · `no` 25 · **`unknown` 11** |
| `evidence_kind` | `text` 84 · `sketch` 3 · `map` 2 · `photo` 1 |

**Three gaps, in priority order.**

1. **`proof: none` on 87 of 90.** Only #74, #86 and #87 carry a deterministic proof, all `bracketing`. So the code-decided share is **3%, against the 77% §9.2 says is reachable**. Everything else is decided downstream, which is where run-to-run variance lives.

2. **30 items are `unbound`** — no section binding, so they cannot reach their own facts. The clearest case is **#34, "Is the square footage in this section consistent with the sketch?"** TRACKER §4k already states this item *"is answered deterministically, with no judge call at all — the item IS the consistency check"*, and `consistency.py` already computes it from four independent GLA sites. The machinery exists; the binding does not.

3. **11 items carry `polarity: unknown`** — #32, 47, 60, 63, 80, 81, 82, 83, 84, 85, 95. §10.2 makes polarity a **compile error** precisely because a missing direction lets the judge decide which answer is bad, and TRACKER §4i calls that *"the single biggest silent failure mode."* Under the coverage gate (§11) these 11 cannot ship.

**Why this ordering.** Binding an item (2) is a YAML edit. Setting polarity (3) is a YAML edit plus AMC confirmation. Writing proofs (1) is engineering — but items already carrying `check_type: same_section` and a real binding are where a proof is cheapest to add, so 2 → 3 → 1 is also the order in which each step makes the next one cheaper.

---

## Appendix 17.5 — `_run18` defect ledger

Every entry re-confirmed against the raw JSON on 2026-08-12.

| Symptom | Root cause |
|---|---|
| 41 fields lost (`market`, `contract_history`) | 23 calls in flight over 4 keys → 17–25 tok/s per call → 180s timeout = 4,500-token hard ceiling |
| Truncation retries at 9,200 and 12,000 tokens | Truncation handler raises `max_tokens` instead of splitting. `splits: 0` — the split path never fired |
| `comp_4` concession/time adjustments transposed, still CERTIFIED | `grid_reconcile` proves sum, not binding. Sum is invariant to row permutation |
| **`comp_6` UNREAD at 0.55 on all 48 fields — but read correctly** | Verifier assumes every comp has `sale_price`. Comp 6 is a **pending listing**. Both checks `skipped`, `line_sum_read: -8200.0` matches printed net exactly; 349,900 − 8,200 = 341,700 matches printed adjusted price ✅ |
| Septic finding structurally unreachable | `adverse_conditions='None' → False` destroyed the literal; `contract_analysis_comment` never extracted |
| `is_pud_checked = "Planned Unit Development (PUD)"` | Model returned the row label as the value; no label/value discrimination |
| `JOB 018JOB 018`, `Dynnesson`, `09/29` vs `09/25`, `appraiser_name = "Colcord"`, `lender_name` missing "USA, LLC" | Full-page resolution on dense alphanumerics; no second pass |
| Silent per-field gaps inside "successful" regions | `comp_3_vehicle_storage_adjustment` ($0 in the PDF), `comp_2_heating_cooling_adjustment`, `comp_6_net_adjustment_total` absent — regions report `missing: []` |
| Provenance: section path 0-based, grid path 1-based | 7 of 11 field groups stamped exactly −1; appraiser −2 (p38 vs signature p40); `comparable_count` carries `page: 0` ✅ |
| Cost projector predicted 24,600 output tokens; actual 80,251 | 3.3× under-projection — `cap_usd` could never fire in time ✅ |
| `DONE`, `coverage 125.7%` on an unreviewable run | 357 emitted ÷ 284 schema size, not required facts resolved ✅ |
| Instrumentation disagrees with itself | Summary `regions 8, verified 7, checks 12`; grid block computes 7 / 6 / 11 ✅ |

---

*Empirical figures re-measured 2026-08-12 against the 40-page 1465 Turner Rd NE report, `_run18.json`, and the 90-item Equity Solutions USA UAD 3.6 checklist. Items marked ⬜ rest on a single document and are subject to the project's three-order rule.*
