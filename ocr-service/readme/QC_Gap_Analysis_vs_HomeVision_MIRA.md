# QC Engine — Gap Analysis vs. a HomeVision MIRA‑Class Standard

> **Purpose.** Rate this application's appraisal‑QC engine against the rule standard a top
> commercial reviewer (HomeVision **MIRA**) is built on, section by section, and call out
> precisely where we win, where we lose, and why.
>
> **Honesty about the benchmark (read this first).** HomeVision MIRA's *actual* rule set and
> its exact rejection/verification wording are **proprietary and not published** — their public
> materials only state that MIRA encodes ">90% of client policy" and that for **UAD 3.6** they
> authored **"more than 800 automated compliance and review rules"** built on 1M+ appraisals
> ([homevision.co/platform](https://homevision.co/platform), [mira-appraisal-qc](https://www.homevision.co/mira-appraisal-qc)).
> We therefore benchmark against the **public, authoritative source those rules implement** — the
> GSE Uniform Appraisal Dataset (UAD) spec and the Fannie Mae / Freddie Mac Selling Guides — not
> against HomeVision's internal copy. Every requirement below is cited to a public source.
>
> **Scope rule honored:** rules that need a **photo/sketch/map image** to evaluate are *excluded*
> from this text‑QC analysis and listed in §7 by name (per the review instruction).

---

## 1. Method & scoring

- **Standard basis:** UAD field standardization + Fannie Mae Selling Guide B4‑1.3 (and FHA/USDA
  overlays). Sources in §8.
- **Our implementation:** read from `app/qc/rules/*.py` — **252 rule IDs** across 14 modules
  (subject, contract, neighborhood, site, improvements, sales_comparison, reconciliation,
  cost/income, addendum, photos, signature, fha_usda, global).
- **Rating per section:** Coverage (do we check what the standard requires?) × Precision
  (Pass/Fail/Verify logic + cross‑doc) × Honesty (does the rule reflect *GSE* policy vs. a lender
  overlay?). 🟢 strong · 🟡 partial · 🔴 gap.

---

## 2. Scorecard (summary)

| Section | Standard expectation | Our coverage | Rating | Headline gap |
|---|---|---|---|---|
| Subject | Address/owner/legal/tax/census/occupancy + cross‑doc to engagement | `S‑1…S‑12` (+24 sub‑checks) | 🟢 | USPS is *referenced* but not a live integration (§3.1) |
| Contract | Purchase‑only; price/date/concessions/sale‑type cross‑doc | `C‑1…C‑5` (+sub) | 🟢 | strong; flip/sale‑type good |
| Neighborhood | Characteristics, trends, 1‑unit range, land‑use, market conditions | `N‑1…N‑7` (+sub) | 🟢 | predominant‑value bracketing solid |
| Site | Dims/area/zoning/HBU/utilities/FEMA flood/adverse | `ST‑1…ST‑10` (+sub) | 🟢 | FEMA is text‑only; flood **map** excluded (image) |
| Improvements | Gen desc / foundation / condition (C1‑C6) / conformity | `I‑1…I‑12`, `I‑Q`, `I‑34` | 🟡 | condition/quality partly need photos; ANSI/UAD‑3.6 area model (§5) |
| Sales Comparison | 3+ closed comps, recency, distance, adjustments, bracketing | `SCA‑1…SCA‑27` (+~30 sub) | 🟢 | richest area; **net15/gross25 are overlays, not GSE** (§4) |
| Reconciliation | Approaches weighted; value supported; as‑is box | `R‑1, R‑2, R‑1b, R‑2b, RECON‑T` | 🟢 | good |
| Cost / Income | Form 1004/216 completeness + arithmetic | `CA‑1…CA‑3, IA‑1, MF‑1, USDA‑1` | 🟢 | arithmetic checks are a strength |
| Addendum / 1004MC | Commentary quality + market‑conditions form | `ADD‑1…ADD‑9` (+sub) | 🟡 | commentary judged deterministically (no LLM judge) |
| Signature | License, dates, supervisory | `SIG‑1…SIG‑3` (+sub) | 🟢 | good |
| Photographs / Sketch / Maps | Image presence + content | `PH‑1, PH‑2, SCA‑27` | 🔴 *(by design)* | **excluded — image‑dependent (§7)** |
| **UAD 3.6 readiness** | Dynamic URAR, ANSI area model, 800+ rules | — | 🔴 | engine targets **UAD 2.6** forms (§5) |

**Overall:** for **UAD 2.6 text QC**, this engine is **strong and competitive** — broad coverage,
genuine cross‑document checks, and arithmetic validation that many checklists lack. The real
distance to a MIRA‑class product is **(a) computer‑vision rules**, **(b) UAD 3.6 / ANSI readiness**,
**(c) live USPS/data integrations**, and **(d) per‑AMC policy configurability** — detailed below.

---

## 3. Where we MATCH or BEAT the standard

### 3.1 Cross‑document verification (a genuine strength)
The standard assumes the reviewer compares the report to the **engagement letter** and **purchase
contract**. We implement this as first‑class logic: `S‑1` (address vs order), `S‑2‑coborrower` /
`S‑2‑refi‑owner`, `S‑10a/S‑10b` (lender name/address vs order), `C‑2a/C‑2b` (price/date vs
contract), `C‑4‑concession` (concession vs contract). Many checklist‑only products *describe* this
but don't execute it. **Win.**

### 3.2 Arithmetic & consistency checks
`CA‑3‑arith` / `CA‑3‑depr` (cost‑approach math), `SCA‑bracket` / `SCA‑PR‑bracket` (subject value
must bracket between adjusted comps), `N‑3‑valuepred` (value vs predominant), `SCA‑zadj‑same` /
`SCA‑zadj‑diff` (zero‑adjustment consistency). This is the kind of computational check a
spreadsheet checklist can't do and a MIRA‑class engine is expected to do. **Win.**

### 3.3 Transaction‑aware gating
`C‑1‑refi‑blank` (contract section must be blank on refis), `S‑2‑refi‑owner`, `SCA‑FLIP` /
`SCA‑FLIP‑comp` (resale/flip detection). Matches GSE intent that contract analysis applies only to
purchases (B4‑1.3‑04) and that rapid resales need scrutiny. **Win.**

---

## 4. Where we are HONESTY‑WRONG vs. GSE policy (fixable, important)

These rules fire as if they were GSE requirements, but the GSE Selling Guide does **not** set them —
they are **lender/AMC overlays**. A MIRA‑class engine keeps overlays **configurable per client**,
not hard‑coded as "UAD requirements."

| Our rule | What it asserts | Reality (cited) | Recommendation |
|---|---|---|---|
| `SCA‑net15` | Net adjustment > 15% → reject | Fannie Mae sets **no** net/gross limit; "number/amount of adjustments must not be the sole determinant" ([B4‑1.3‑09](https://selling-guide.fanniemae.com/sel/b4-1.3-09/adjustments-comparable-sales)) | Keep as a **VERIFY** flag, label it a lender overlay, make the threshold per‑AMC config |
| `SCA‑gross25` | Gross adjustment > 25% → reject | same as above | same |
| `SCA‑4‑prox` (if hard 1‑mile) | Comp > 1 mile → reject | GSE requires **distance stated with direction**, market‑area based; no hard mile cap ([B4‑1.3‑08](https://selling-guide.fanniemae.com/sel/b4-1.3-08/comparable-sales)) | VERIFY + require commentary, not auto‑fail |
| `S‑4‑taxyear` (2‑yr window) | Tax year must be ≤ 2 yrs | Reasonable, but it's a data‑freshness overlay, not a UAD field rule | Keep, label as overlay |

> **Why this matters for the comparison:** MIRA markets "automates >90% of *client policy*" — i.e.
> the differentiator is **configurable policy**, not hard‑coded thresholds. Hard‑coding overlays as
> GSE rules is the single most "un‑MIRA‑like" trait in our engine today.

---

## 5. Where we LOSE: UAD 3.6 / ANSI readiness (the biggest strategic gap) 🔴

- HomeVision's headline is **first‑to‑market on UAD 3.6** with **800+ rules** for the new dynamic
  URAR ([platform](https://homevision.co/platform)). UAD 3.6 (limited availability late 2025,
  mandated 2026) **drops "GLA"/"basement"** terminology in favor of **above‑grade / below‑grade
  finished area** and bakes **ANSI Z765‑2021** measurement into the form
  ([McKissock](https://www.mckissock.com/blog/appraisal/the-future-is-now-fannie-mae-and-freddie-mac-announce-uad-3-6-implementation-timeline-and-policy-changes/),
  [ANSI/UAD 3.6](https://www.mckissock.com/blog/appraisal/freddie-mac-announces-adoption-of-ansi-measurement-standard/)).
- **Our engine targets the UAD 2.6 form layout** (`SCA‑17‑gla`, `SCA‑26‑gla`, room‑count grids keyed
  to the 1004). It is **not** UAD‑3.6 / ANSI‑aware. This is the clearest area where a MIRA‑class
  product is ahead.

**Recommendation:** treat UAD‑3.6 as a roadmap track — area‑by‑level model, ANSI cross‑checks
(sketch ↔ stated finished area ↔ room‑level data), and the new field schema. Until then, scope the
engine honestly as **UAD 2.6**.

---

## 6. Where we are PARTIAL 🟡 (good but not best‑in‑class)

- **Commentary quality (`ADD‑1`, `ADD‑2‑selection`, `N‑6`, `R‑1b`):** we judge commentary with
  deterministic canned‑phrase + specificity checks (the LLM "judge" was removed). A MIRA‑class
  engine uses NLP to assess whether narrative *explains why, not just what*. Ours is reliable but
  blunter — acceptable, but a known ceiling.
- **Condition/Quality (`I‑9`, `I‑Q`, `SCA‑14`, `SCA‑16`):** we validate the **stated** C/Q ratings
  and grid consistency, but the standard's intent (does the rating *match the photos*?) needs CV —
  see §7.
- **FEMA flood (`ST‑8‑flood`, `ST‑8‑femadata`):** text‑level only; the actual **flood map** check is
  image‑dependent and excluded.

---

## 7. EXCLUDED — image / photo / sketch / map‑dependent rules (by instruction)

These cannot be evaluated from text alone; they need computer vision on photos, sketches, or maps.
They are **named here and excluded** from the text‑QC rating above:

- **Photographs:** `PH‑1`, `PH‑1‑missing`, `PH‑2`, `PH‑2‑interior` (subject/interior photo presence
  & content); checklist `PH‑3…PH‑6`.
- **Comparable photos:** `SCA‑27`, `SCA‑27‑missing`, `SCA‑27‑mls`, `SCA‑27‑defer`,
  `SCA‑27‑nobuilding`; vision condition `SCA‑16V`, `SCA‑16V‑cond`, `SCA‑16V‑distress`.
- **Occupancy from photos:** `S‑7`/`S‑7‑occupant` *(the cross‑check of stated occupancy vs. what the
  photos show — the text presence check is fine; the photo comparison is excluded)*.
- **Sketch / floor plan:** checklist `SK‑1…SK‑5`; `SCA‑17‑nosketch` (presence is text‑inferable; the
  ANSI area‑from‑sketch check is image).
- **Maps:** checklist `M‑1…M‑4` (location/aerial/plat/**flood map**).
- **FHA image rules:** `FHA‑9`, `FHA‑9‑sides` (photo of all sides); checklist `FHA‑8` (security
  bars), `FHA‑9` (photos), `FHA‑11` (attic/crawl photo).

> Net: roughly **20–25 of the 129 documented rules are image‑dependent.** Excluding them, our
> **text‑QC coverage of the remaining ~105 is high.**

---

## 8. Verdict — do we "lose," and where?

**We do not lose on text QC for UAD 2.6.** Coverage, cross‑document checks, and arithmetic put this
engine in the same class as a commercial text reviewer for the 2.6 form. We **lose**, specifically,
on:

1. **Computer vision (🔴):** every photo/sketch/map rule (§7). MIRA does CV; we don't yet.
2. **UAD 3.6 / ANSI (🔴):** MIRA is shipped; we're 2.6‑only (§5).
3. **Configurable client policy (🟡→🔴):** MIRA's whole pitch is per‑client policy automation; we
   hard‑code overlays as GSE rules (§4).
4. **Live data integrations (🟡):** USPS address, county assessor, flood, MLS — we *reference* them
   in rules but don't integrate them live (USPS detail in the checklist §USPS).
5. **NLP commentary judgment (🟡):** deterministic, not semantic (§6).

**Where we are at parity or ahead:** transaction‑aware gating, cross‑doc verification, arithmetic
and bracketing consistency, and breadth of the 2.6 rule set (252 implemented IDs).

### Prioritized recommendations
1. **Re‑class the overlays** (`SCA‑net15`, `SCA‑gross25`, hard proximity) from FAIL→VERIFY and make
   thresholds per‑AMC config. *(Cheap, high‑credibility.)*
2. **USPS live verification** for the Subject section (address standardization + ZIP+4 + county).
3. **UAD 3.6 / ANSI track** as a roadmap (area‑by‑level, sketch↔area cross‑check).
4. **CV rules** (the §7 set) as a separate vision workstream.
5. **NLP commentary judge** to lift `ADD‑*`/`N‑6` from "canned‑phrase" to "explains‑why".

---

## 9. Sources (public, authoritative)

- HomeVision MIRA (benchmark, capabilities only): [platform](https://homevision.co/platform) · [MIRA for AMCs](https://www.homevision.co/mira-appraisal-qc) · [MIRA for Lenders](https://www.homevision.co/lender)
- Fannie Mae Selling Guide: [B4‑1.3‑01 Review](https://selling-guide.fanniemae.com/sel/b4-1.3-01/review-appraisal-report) · [B4‑1.3‑06 Condition/Quality](https://selling-guide.fanniemae.com/sel/b4-1.3-06/property-condition-and-quality-construction-improvements) · [B4‑1.3‑07 SCA](https://selling-guide.fanniemae.com/sel/b4-1.3-07/sales-comparison-approach-section-appraisal-report) · [B4‑1.3‑08 Comparable Sales](https://selling-guide.fanniemae.com/sel/b4-1.3-08/comparable-sales) · [B4‑1.3‑09 Adjustments](https://selling-guide.fanniemae.com/sel/b4-1.3-09/adjustments-comparable-sales)
- UAD condition/quality definitions: [McKissock C1‑C6](https://www.mckissock.com/blog/appraisal/understanding-appraisal-condition-ratings-c1-to-c6/) · [McKissock quality](https://www.mckissock.com/blog/appraisal/understanding-uad-quality-ratings/)
- UAD 3.6 & ANSI Z765: [McKissock UAD 3.6 timeline](https://www.mckissock.com/blog/appraisal/the-future-is-now-fannie-mae-and-freddie-mac-announce-uad-3-6-implementation-timeline-and-policy-changes/) · [McKissock ANSI](https://www.mckissock.com/blog/appraisal/freddie-mac-announces-adoption-of-ansi-measurement-standard/)
- USPS address APIs: [USPS API catalog](https://developers.usps.com/apis) · [USPS Address Information](https://www.usps.com/business/web-tools-apis/address-information-api.htm)

*Prepared from a read of `app/qc/rules/*.py` (252 rule IDs) against the public GSE/UAD standard. HomeVision's proprietary rule text was not available and is not reproduced.*
