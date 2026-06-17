# QC Coverage Audit — UAD 2.6 (canonical requirement → rule mapping)

> **Goal.** A real gap list, not an estimate. We build a **canonical UAD 2.6 requirement
> checklist** from the public standard (Fannie Mae Selling Guide **B4‑1.3** + the UAD field
> standardization), then map **every one of the 252 implemented rule IDs** in `app/qc/rules/*.py`
> onto it and mark each requirement **Covered / Partial / Missing / Excluded‑image**.
>
> **Honesty caveat (unchanged from the gap analysis).** There is **no single published canonical
> "2.6 rule list"** — Fannie doesn't publish a count, and UCDP/EAD bundles thousands of low‑level
> format edits into a few hundred meaningful checks. This canonical list is therefore *our*
> faithful derivation of the **meaningful, reviewable** requirements of the 1004/URAR under 2.6,
> each tied to a public source. It is the right denominator for "are we missing anything," but it
> is a derivation, not an official catalogue.
>
> **Status legend:** ✅ Covered · 🟡 Partial (exists but shallow / mis‑scoped) · ❌ Missing ·
> 🖼️ Excluded‑image (needs CV — *not counted as a gap*, per the review instruction).

---

## 1. Scorecard

| Section | Canonical reqs | ✅ | 🟡 | ❌ | 🖼️ |
|---|---:|---:|---:|---:|---:|
| Subject | 16 | 14 | 1 | 1 | (S‑7 photo‑half) |
| Contract | 8 | 8 | 0 | 0 | 0 |
| Neighborhood | 8 | 8 | 0 | 0 | 0 |
| Site | 11 | 9 | 0 | 1 | (flood map) |
| Improvements | 14 | 8 | 2 | 4 | (security bars) |
| Sales Comparison | 30 | 27 | 2 | 1 | (SCA‑16V, SCA‑27) |
| Reconciliation | 6 | 6 | 0 | 0 | 0 |
| Cost / Income | 6 | 6 | 0 | 0 | 0 |
| Addendum / 1004MC | 7 | 4 | 3 | 0 | 0 |
| Signature / Doc | 8 | 5 | 1 | 2 | 0 |
| FHA / USDA overlays | 15 | 6 | 0 | 6 | (FHA‑8/9/11/14) |
| UAD format/syntax (cross‑cut) | 3 | 0 | 3 | 0 | 0 |
| **Total** | **~132** | **~101** | **~14** | **~16** | **~9 sets** |

**Headline:** of the meaningful non‑image 2.6 requirements, **~77% fully covered, ~11% partial,
~12% missing.** No whole section is absent. The misses cluster in **Improvements detail**, the
**FHA overlay**, and **UAD format‑syntax validation** — not in the core valuation logic.

---

## 2. Subject (B4‑1.3‑03)

| # | Canonical requirement | Your rule(s) | Status |
|---|---|---|---|
| 1 | Address complete & valid (street/city/state/zip/county) | `S‑1` (+USPS spec) | ✅ |
| 2 | All borrowers/co‑borrowers listed | `S‑2`, `S‑2‑coborrower` | ✅ |
| 3 | Owner of public record present | `S‑3`, `S‑2‑refi‑owner` | ✅ |
| 4 | Legal description present | `S‑4‑legal`, `S‑4a` | ✅ |
| 5 | APN present + format | `S‑4‑apn‑format` | ✅ |
| 6 | Tax year + RE taxes present/plausible | `S‑4‑taxyear`, `S‑4‑tax‑implausible`, `S‑4b/c/d` | ✅ |
| 7 | Neighborhood name recognized (not N/A) | `S‑5`, `S‑5‑generic`, `S‑5‑neighborhood` | ✅ |
| 8 | Map reference present | `S‑6` | ✅ |
| 9 | Census tract format `XXXX.XX` | `S‑6`, `S‑6b` | ✅ |
| 10 | Occupant status stated | `S‑7`, `S‑7‑occupant`, `S‑7‑tenant`, `S‑7‑vacant` | ✅ (photo‑vs‑stated = 🖼️) |
| 11 | Special assessments (0 or amount+purpose) | `S‑8`, `S‑8‑assessment` | ✅ |
| 12 | PUD/HOA box consistency | `S‑9`, `S‑9‑pud` | ✅ |
| 13 | Property rights — exactly one box | `S‑11`, `S‑11‑rights` | ✅ |
| 14 | Assignment type / lender‑client vs order | `S‑10a`, `S‑10b` | ✅ |
| 15 | Prior sale/listing history + data source | `S‑12`, `S‑12‑datasource`, `S‑12‑listing` | ✅ |
| 16 | **Condo (Form 1073) project review** (owner‑occ %, budget, eligibility) | — | ❌ *(borderline: project eligibility, not form QC)* |

## 3. Contract (B4‑1.3‑04, purchase only)

| # | Requirement | Rule(s) | Status |
|---|---|---|---|
| 1 | Contract analyzed (purchase) | `C‑1`, `C‑1‑analyze` | ✅ |
| 2 | Refi → section blank | `C‑1‑refi‑blank` | ✅ |
| 3 | Sale type identified | `C‑1‑saletype`, `C‑1‑txn‑unknown` | ✅ |
| 4 | Price + date match contract | `C‑2a`, `C‑2b` | ✅ |
| 5 | Seller = owner of record + data source | `C‑3`, `C‑3‑datasource`, `C‑3‑comment` | ✅ |
| 6 | Concessions yes/no + amount + desc | `C‑4`, `C‑4‑concession`, `C‑4‑blank`, `C‑4‑contradict`, `C‑4‑desc` | ✅ |
| 7 | Personal property contribution | `C‑5`, `C‑5‑personal` | ✅ |
| 8 | Value‑vs‑contract variance reconciled | `C‑1‑variance` | ✅ |

## 4. Neighborhood (B4‑1.3‑03)

| # | Requirement | Rule(s) | Status |
|---|---|---|---|
| 1 | Characteristics checkboxes (each category) | `N‑1`, `N‑1‑checkbox` | ✅ |
| 2 | Housing trends set | `N‑2`, `N‑2‑mca` | ✅ |
| 3 | 1‑unit price/age range + predominant | `N‑3`, `N‑3‑range`, `N‑3‑predominant`, `N‑3‑comprange`, `N‑3‑valuepred` | ✅ |
| 4 | Present land use ~100% + "Other" desc | `N‑4`, `N‑4‑landuse`, `N‑4‑other` | ✅ |
| 5 | Boundaries delineated (text, not map‑only) | `N‑5`, `N‑5‑boundary`, `N‑5‑delineation`, `N‑5‑maponly`, `N‑5‑abbrev` | ✅ |
| 6 | Neighborhood description specific | `N‑6` | ✅ |
| 7 | Market conditions consistent | `N‑7` | ✅ |
| 8 | Built‑up % vs land use | `N‑1‑landuse‑x` | ✅ |

## 5. Site (B4‑1.3‑04)

| # | Requirement | Rule(s) | Status |
|---|---|---|---|
| 1 | Dimensions present | `ST‑1`, `ST‑1‑dims` | ✅ |
| 2 | Area present + consistent | `ST‑2`, `ST‑2‑area` | ✅ |
| 3 | Shape | `ST‑3`, `ST‑3‑shape` | ✅ |
| 4 | View (UAD) + grid consistency | `ST‑4`, `ST‑4‑view`, `ST‑4‑grid` | ✅ |
| 5 | Zoning classification + compliance + rebuild comment | `ST‑5`, `ST‑5‑nonconforming`, `ST‑5‑nozoning`, `ST‑5‑illegal‑hold` | ✅ |
| 6 | Highest & best use | `ST‑6`, `ST‑6‑hbu‑hold` | ✅ |
| 7 | Utilities + off‑site | `ST‑7`, `ST‑7‑utilities` | ✅ |
| 8 | Well/septic when applicable | `ST‑7‑wellseptic` | ✅ |
| 9 | FEMA flood zone/panel/date (text) | `ST‑8`, `ST‑8‑flood`, `ST‑8‑femadata` | ✅ (flood **map** = 🖼️) |
| 10 | **Utilities/off‑site *typical for market*** (checklist `ST‑9`) | — | ❌ *(documented `ST‑9`, not implemented)* |
| 11 | Adverse site conditions | `ST‑10`, `ST‑10‑adverse` | ✅ |

## 6. Improvements (B4‑1.3‑05 / ‑06) — the weakest non‑image area

| # | Requirement | Rule(s) | Status |
|---|---|---|---|
| 1 | General desc (type/units/year/age) | `I‑1`, `I‑1‑fields`, `I‑1‑age`, `I‑1‑gendesc` | ✅ |
| 2 | Foundation | `I‑2`, `I‑2‑foundation` | ✅ |
| 3 | Exterior materials/condition | `I‑34`, `I‑34‑materials` | 🟡 (combined; not per‑element) |
| 4 | Interior materials/condition | `I‑34‑materials` | 🟡 (folded into I‑34) |
| 5 | **Utilities (heating/cooling type)** — checklist `I‑5` | — | ❌ |
| 6 | **Appliances (general, non‑FHA)** — checklist `I‑6` | (only `FHA‑13`) | ❌ |
| 7 | Above‑grade room count + grid consistency | `I‑7`, `I‑7‑roomcount` | ✅ |
| 8 | **Additional features** — checklist `I‑8` | — | ❌ |
| 9 | Condition C1‑C6 + grid + eff age | `I‑9`, `I‑9‑grid`, `I‑9‑effage` | ✅ (photo match = 🖼️) |
| 10 | Quality Q1‑Q6 | `I‑Q` | ✅ |
| 11 | Adverse conditions to livability | `I‑10`, `I‑10‑adverse` | ✅ |
| 12 | Neighborhood conformity | `I‑11`, `I‑11‑conform` | ✅ |
| 13 | Additions/updates referenced | `I‑12`, `I‑12‑addition` | ✅ |
| 14 | **Security bars** — checklist `I‑13` | (`FHA‑8`) | 🖼️ |

## 7. Sales Comparison (B4‑1.3‑07/08/09) — strongest area

| # | Requirement | Rule(s) | Status |
|---|---|---|---|
| 1 | ≥ 3 **closed** comparables | `SCA‑2`, `SCA‑2‑count` | ✅ |
| 2 | Listings = support only | `SCA‑2‑listings`, `SCA‑23`, `SCA‑23‑listing` | ✅ |
| 3 | Comp addresses | `SCA‑3`, `SCA‑3‑addr` | ✅ |
| 4 | Distance with direction (no GSE mile cap) | `SCA‑4`, `SCA‑4‑prox` | ✅ *(hard cap = overlay, §11)* |
| 5 | Data sources + DOM | `SCA‑5`, `SCA‑5‑ds`, `SCA‑5‑dom` | ✅ |
| 6 | Verification sources | `SCA‑6`, `SCA‑6‑verif` | ✅ |
| 7 | Sale/financing concessions | `SCA‑7`, `SCA‑7‑conc` | ✅ |
| 8 | Date of sale + time adjustment | `SCA‑8`, `SCA‑8‑datesale`, `SCA‑DC`, `SCA‑DC‑old` | ✅ |
| 9 | Location rating | `SCA‑9` | ✅ |
| 10 | Leasehold/fee + rights | `SCA‑10`, `SCA‑10‑rights`, `SCA‑10‑lease` | ✅ |
| 11 | Site / View / Design | `SCA‑11`, `SCA‑12`, `SCA‑13` | ✅ |
| 12 | Quality (Q) + comment | `SCA‑14`, `SCA‑14‑comment` | ✅ |
| 13 | Actual age | `SCA‑15`, `SCA‑15‑age` | ✅ |
| 14 | Condition (C) | `SCA‑16` | ✅ (photo `SCA‑16V*` = 🖼️) |
| 15 | Room count + GLA + sketch consistency | `SCA‑17`, `SCA‑17‑gla`, `SCA‑17‑comp‑gla`, `SCA‑17‑nosketch` | ✅ |
| 16 | Below‑grade / basement | `SCA‑18` | ✅ |
| 17 | Functional utility / HVAC / garage / porch | `SCA‑19`, `SCA‑20`, `SCA‑21`, `SCA‑22` | ✅ |
| 18 | Net/gross adjustments | `SCA‑NET`, `SCA‑GROSS`, `SCA‑net15`, `SCA‑gross25` | ✅ *(mis‑classed overlay, §11)* |
| 19 | Bracketing (value brackets comps) | `SCA‑bracket`, `SCA‑PR‑bracket`, `SCA‑BR`, `SCA‑bracket‑na` | ✅ |
| 20 | Zero‑adjustment consistency | `SCA‑zadj‑same`, `SCA‑zadj‑diff`, `SCA‑ZF`, `SCA‑zf‑same` | ✅ |
| 21 | Adjustment sign/AC consistency | `SCA‑AC`, `SCA‑ac‑inconsistent` | ✅ |
| 22 | Prior sale/transfer (subject + comps) | `SCA‑PSH`, `SCA‑PSH‑subj` | ✅ |
| 23 | New construction comps (in/out project) | `SCA‑25`, `SCA‑25‑newconst` | ✅ |
| 24 | Flip / rapid resale | `SCA‑FLIP`, `SCA‑FLIP‑comp` | ✅ |
| 25 | Square footage consistency | `SCA‑26`, `SCA‑26‑gla` | ✅ |
| 26 | Bed/room grid | `SCA‑BR` | ✅ |
| 27 | **Adjustment *support* (market‑/paired‑sales‑derived)** | — | 🟡 *(needs market analysis; not auto‑derivable)* |
| 28 | **ANSI area model (UAD 3.6)** | — | ❌ *(3.6, out of 2.6 scope — noted)* |
| 29 | Comparable photos | `SCA‑27*` | 🖼️ |

## 8. Reconciliation / Cost / Income

| # | Requirement | Rule(s) | Status |
|---|---|---|---|
| R1 | Approaches weighted | `R‑1`, `R‑1‑weight` | ✅ |
| R2 | Value within range / brackets | `R‑1‑range`, `R‑1‑mismatch`, `RECON‑T` | ✅ |
| R3 | Single final opinion | `R‑2`, `R‑2b` | ✅ |
| R4 | As‑is / subject‑to box correct | `R‑2‑asisbox` | ✅ |
| R5 | Bias‑free language | `R‑2‑bias` | ✅ |
| R6 | Names primary approach | `R‑1b` | ✅ |
| CA1 | Cost approach when required + site value | `CA‑1`, `CA‑1‑sitevalue`, `CA‑2` | ✅ |
| CA2 | Remaining economic life | `CA‑2‑life` | ✅ |
| CA3 | Cost arithmetic / depreciation | `CA‑3‑arith`, `CA‑3‑depr` | ✅ |
| IN1 | Subject rent | `IA‑1`, `IA‑1‑rent` | ✅ |
| IN2 | Form 216 / multi‑family income | `MF‑1`, `MF‑1‑income` | ✅ |

## 9. Addendum / 1004MC / Signature / Doc

| # | Requirement | Rule(s) | Status |
|---|---|---|---|
| AD1 | Commentary standard (no canned) | `ADD‑1` | ✅ |
| AD2 | Comp‑selection commentary (why) | `ADD‑2`, `ADD‑2‑selection` | ✅ |
| AD3 | 1004MC present + core fields | `ADD‑4`, `ADD‑4‑mc`, `ADD‑5`, `ADD‑5‑fields` | ✅ |
| AD4 | **1004MC inventory analysis** (checklist `ADD‑5`) | `ADD‑5` partial | 🟡 |
| AD5 | **1004MC comparables matching** (checklist `ADD‑6`) | — | 🟡 |
| AD6 | **1004MC overall trend** (checklist `ADD‑7`) | `ADD‑4‑mc` partial | 🟡 |
| AD7 | 1004MC condo / USPAP addendum | `ADD‑8`, `ADD‑8‑condo`, `ADD‑9`, `ADD‑9‑exposure/services/type` | ✅ |
| SG1 | Signatures present + dated + no date gap | `SIG‑1`, `SIG‑1‑missing`, `SIG‑1‑gap`, `SIG‑date` | ✅ |
| SG2 | Appraiser license/info + valid | `SIG‑2`, `DOC‑1`, `DOC‑1‑expired` | ✅ |
| SG3 | Supervisory appraiser / trainee | `SIG‑3`, `SIG‑3‑state`, `SIG‑SUP`, `SIG‑sup`, `SIG‑D` | ✅ |
| SG4 | **Appraiser email** (checklist `SIG‑4`) | — | ❌ *(minor)* |
| DC1 | **E&O insurance** (checklist `DOC‑2`) | — | ❌ |
| DC2 | **UAD data‑set completeness** (checklist `DOC‑3`) | scattered | 🟡 |

## 10. FHA / USDA overlays — thin coverage

| # | Requirement | Rule(s) | Status |
|---|---|---|---|
| F1 | FHA case number + match | `FHA‑2`, `FHA‑2‑case`, `FHA‑2‑match` | ✅ |
| F2 | FHA intended use/user | `FHA‑3`, `FHA‑3‑intended` | ✅ |
| F3 | FHA comp dating | `FHA‑5`, `FHA‑5‑comps` | ✅ |
| F4 | FHA remaining economic life | `FHA‑10`, `FHA‑10‑life` | ✅ |
| F5 | **FHA HUD Minimum Property Requirements** (`FHA‑1`) | — | ❌ |
| F6 | **FHA MPR statement** (`FHA‑4`) | — | ❌ |
| F7 | **FHA repairs / subject‑to** (`FHA‑6`) | — | ❌ |
| F8 | **FHA space‑heater as primary heat** (`FHA‑7`) | — | ❌ |
| F9 | **FHA well & septic** (`FHA‑12`) | (`ST‑7‑wellseptic` generic) | ❌ *(FHA‑specific)* |
| F10 | **FHA appliances** (`FHA‑13`) | — | ❌ |
| F11 | FHA photos / sides / attic‑crawl / sketch | `FHA‑9`, `FHA‑9‑sides`, `FHA‑8`, `FHA‑11`, `FHA‑14` | 🖼️ |
| U1 | USDA cost approach | `USDA‑1`, `USDA‑1‑cost`, `USDA‑1‑fields` | ✅ |

## 11. UAD format/syntax (cross‑cutting) — partial everywhere

| # | Requirement | Status | Note |
|---|---|---|---|
| 1 | UAD rating **codes valid** (view/location `X;Y`, C1‑C6, Q1‑Q6) | 🟡 | values checked; exact UAD *syntax* not validated centrally |
| 2 | UAD **abbreviations** (ArmLth, REO, Conv;FHA;VA, etc.) | 🟡 | partial (`N‑5‑abbrev`, scattered) |
| 3 | UAD **grid data formats** (date MM/YYYY, `$`, `;`‑delimited) | 🟡 | partial |

---

## 12. THE REAL GAP LIST (prioritized, non‑image) — **with implementation status**

> **Update (this revision):** the missing non‑image rules below were **implemented** in
> `app/qc/rules/*.py` (+ `config/qc_templates.yaml`). All register, parse, and execute on an empty
> context without error; the section/engine test suite stays green (the one failing test is an
> unrelated vision‑API‑key test). They are confidence‑calibrated (low‑confidence → VERIFY) and the
> FHA rules are FHA‑scoped + signal‑gated to avoid review noise.

**✅ Implemented (was ❌ Missing):**
1. **Improvements detail:** `I‑5` heating/cooling, `I‑6` appliances, `I‑8` additional
   features → `app/qc/rules/improvements.py`.
2. **FHA overlay depth:** `FHA‑1` MPR, `FHA‑4` MPR statement, `FHA‑6` repairs‑subject‑to (gated on
   C5/C6 or repair signal), `FHA‑7` space heater (gated on heating field), `FHA‑12` FHA well/septic
   (gated on private water/sewer), `FHA‑13` FHA appliances → `app/qc/rules/fha_usda.py`.
3. **Site:** `ST‑9` utilities/off‑site typical for market (gated on private‑utility signal,
   complements `ST‑7`) → `app/qc/rules/site.py`.
4. **Docs:** `SIG‑4` appraiser email → `app/qc/rules/signature.py`.

**⛔ Intentionally NOT implemented (cannot be checked from report text):**
- **`DOC‑2` E&O insurance** — evidence of errors‑&‑omissions coverage is a **separate underwriting
  document**, not part of the URAR; a report‑text rule cannot verify it. Belongs in document‑set
  QC, not appraisal QC. *(Honest non‑gap.)*

**🟡 Partial — still worth deepening (not done this pass):**
5. **UAD format‑syntax validator** (one central check for valid UAD codes/abbreviations/formats).
6. **1004MC sub‑analysis** (`ADD‑5` inventory, `ADD‑6` comparables match, `ADD‑7` overall trend).
7. **Improvements exterior/interior** split out of the combined `I‑34`.
8. **`DOC‑3`** UAD data‑set completeness as a dedicated check.

**✅ Correction — NOT a mis‑classification:**
9. `SCA‑net15` / `SCA‑gross25` **already emit `VERIFY`, not FAIL** in code
   (`sales_comparison.py`) — the earlier note over‑read the checklist. They are correctly treated
   as soft overlays. *(Remaining nicety: make the 15/25 thresholds per‑AMC configurable — they
   already read from `qc_config.semantic(...)`, so this is config, not code.)*

**🔭 Out of 2.6 scope (note only):** ANSI area model + UAD 3.6 fields; Condo 1073 project review
(project eligibility, not form QC).

**🖼️ Excluded by instruction (NOT gaps — need computer vision):** `S‑7` photo‑occupancy,
`SCA‑16V*`, `SCA‑27*`, `PH‑1…6`, `SK‑1…5`, `M‑1…4`, `FHA‑8/9/11/14`.

---

## 13. Bottom line

**You are not "missing many rules" for 2.6.** ~77% of meaningful non‑image requirements are fully
covered, with the valuation core (Sales Comparison, cross‑doc, arithmetic, reconciliation)
**essentially complete**. The genuine, actionable gaps total **~10 rules** — concentrated in
**Improvements detail (3)** and the **FHA overlay (6)** — plus **~4 "deepen these" partials** and the
**overlay re‑classification**. Close those and the engine has full, honest 2.6 text‑QC coverage;
the only remaining distance to a MIRA‑class product is then **computer vision** and **UAD 3.6**.

## Sources
Fannie Mae Selling Guide [B4‑1.3‑07 SCA section](https://selling-guide.fanniemae.com/sel/b4-1.3-07/sales-comparison-approach-section-appraisal-report) · [B4‑1.3‑08 Comparable Sales](https://selling-guide.fanniemae.com/sel/b4-1.3-08/comparable-sales) · [B4‑1.3‑09 Adjustments](https://selling-guide.fanniemae.com/sel/b4-1.3-09/adjustments-comparable-sales) · [B4‑1.3‑06 Condition/Quality](https://selling-guide.fanniemae.com/sel/b4-1.3-06/property-condition-and-quality-construction-improvements) · UAD ratings [C1‑C6](https://www.mckissock.com/blog/appraisal/understanding-appraisal-condition-ratings-c1-to-c6/) / [Q1‑Q6](https://www.mckissock.com/blog/appraisal/understanding-uad-quality-ratings/) · [USPS APIs](https://developers.usps.com/apis)

*Mapping derived from a read of `app/qc/rules/*.py` (252 rule IDs) against the public GSE/UAD standard. There is no official published 2.6 rule catalogue; the canonical list here is our sourced derivation of the reviewable requirements.*
