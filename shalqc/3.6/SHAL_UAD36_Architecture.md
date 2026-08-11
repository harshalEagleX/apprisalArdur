# SHAL — UAD 3.6 Vision Extraction & Multi-AMC QC Architecture

**Status:** design reference · measurements are real, LLM latencies are estimates
**Scope:** UAD 3.6 (redesigned URAR, Fannie/Freddie Sept 2024). **UAD 2.6 is untouched.**
**Evidence base:** `Email - AppraisalArdur - Outlook (1).pdf` (40pp, 1465 Turner Rd NE, Rome GA)
and `UAD_3_6_Checklist_2_UAD_3.csv` (Equity Solutions USA, 90 numbered items)
**Inference provider:** Together AI, serverless

---

## 0. TL;DR

Five decisions, each with the number behind it:

| # | Decision | Because |
|---|----------|---------|
| 1 | **Do not send checklist items to the vision model.** Extract facts; judge separately. | Only **25%** of checklist items can be answered from one page. **54%** need two or more pages. |
| 2 | **Exploit the report's internal redundancy as a free verification network.** | **13 canonical facts, 44 independent observations, 3.4 sources per fact** — at zero extra cost. |
| 3 | **Wall clock is a `max()`, not a `sum()`.** Size lanes to the wave; hedge the tail. | 21 lanes → p50 **33.4s**, p95 **41.3s**. 4 lanes → **100% of runs blow the deadline.** |
| 4 | **Serverless models only.** Qwen3-VL-32B is dedicated-only and uneconomic at your volume. | Dedicated H100 ≈ $6.49/hr; break-even ≈ 5B tokens/mo. You run ≈ **717M/mo** — 7× below. |
| 5 | **One extraction, N checklists.** The AMC variability lives in a compiled bundle. | New AMC = one overlay file. No new extractor, no new schema, no re-reading the PDF. |

Cost: **$0.045/order** serverless tiered, **$0.022** batched. ≈ **$202/month** at 4,500 orders.

---

## 1. Evidence base — what was measured

Everything in this section was run against the actual uploaded file. Nothing is estimated.

### 1.1 The PDF has no text layer

| Probe | Result |
|---|---|
| `get_text()` across all 40 pages | **0 characters** |
| `get_fonts()` across all 40 pages | **0 fonts** |
| Page geometry | **612 × 792 pt (US Letter) on all 40 pages** — no exceptions |
| Classification | **`flattened`** — glyphs are vector outlines |

Producer is PDFium (Chrome/Outlook print-to-PDF). The native TOTAL export is normally a real
digital PDF. **See §9, Action 1.**

### 1.2 Page map

| Signature | Meaning | Count |
|---|---|---|
| `0 images, high drawings` | dense text/table | **7** |
| `many images, low drawings` | photo sheet — **skip** | **16** |
| mixed | data + exhibit | **17** |

**24 pages worth extracting, 16 skipped before a single call is made.**

> ⚠️ **CORRECTED 2026-08-09 — page skipping has been REMOVED.** The 16 "photo"
> pages included **page 33**, which carries a *Value Reconciliation* table
> restating every comparable's adjusted price, weight and weighted contribution
> ($318,300 / 20% / $63,660 for comp 1 — matching the grid arithmetic exactly,
> weights summing to 100%). That is the free independent answer key for the
> hardest region in the document, and it was being discarded.
>
> It cannot be rescued by a better threshold — page 33 and a genuine photo sheet
> are structurally **indistinguishable**:
>
> | | p33 (data table) | p27 (photo sheet) |
> |---|---|---|
> | images | 29 | 20 |
> | image area | **44.2%** | **44.2%** |
> | drawings | 305 | 304 |
>
> On a flattened PDF there is no text layer to separate them, so any rule that
> drops one drops the other. Interior photos are also the only evidence for the
> appliance fields, and photo *presence* is itself a checklist item. All 40 pages
> now read, for **$0.097 — 13% of cap**. The cost lever is DPI and call shape;
> never discarding evidence.

### 1.3 Image billing is FLAT — DPI does not change token cost at all

> ⚠️ **CORRECTED 2026-08-09 by direct measurement against the live endpoint.**
> This section previously carried a tile formula
> (`min(2, w//560) × min(2, h//560) × 1601` → 3,202/6,404 tokens per page) and a
> "132-DPI cliff". Both were inherited from Anthropic-based planning and are
> **wrong for `google/gemma-4-31B-it` on Together — by a factor of ~24.**

Measured on **page 21, the sales grid** — the densest page in the document —
by differencing a request with and without the image:

| Request | Pixels | `prompt_tokens` | Image costs |
|---|---|---:|---:|
| text only | — | 22 | — |
| grid page @130 DPI | 1105 × 1430 | 291 | **269** |
| grid page @150 DPI | 1275 × 1650 | 291 | **269** |
| grid page @200 DPI | 1700 × 2200 | 291 | **269** |

An earlier sweep at 72/100/130/150/200 DPI on page 2 returned `prompt_tokens=298`
at *every* setting, with the subject address read correctly every time.

Three consequences, all inverted from the previous text:

1. **DPI is not a cost lever.** 72 DPI and 200 DPI bill identically. Together
   downscales server-side to a fixed internal representation before billing.
2. **There is no 132-DPI cliff.** Nothing is lost by rendering the grid below
   132 DPI, and nothing is gained above it. The old advice ("never use 130 DPI
   for the comparable grid") was protecting against a boundary that does not exist.
3. **DPI is a BYTE lever, and lower is better.** 200 DPI is 322 KB per page
   versus 91 KB at 72 DPI for identical tokens and identical accuracy — and at
   high concurrency those oversized payloads caused connection failures that
   cost whole sections. Defaults are now 100 DPI (sections) / 110 (grid).

**What this does NOT change:** cropping is still worth it. Because the model
always sees a fixed-size downscaled image, a crop of one comparable's column is
genuinely higher *effective* resolution than the same budget spread across four
columns plus margin. Crop for legibility, never for tokens.

> **Input tokens are ~24× cheaper than modelled, so the real constraints are
> LATENCY and OUTPUT tokens, not input.** See §5 and the output-ceiling note in
> §1.4.

### 1.4 Per-order cost — measured end to end, not modelled

> ⚠️ **CORRECTED 2026-08-09.** The 147,078-input-token figure below followed from
> the tile formula corrected in §1.3 and is ~24× too high. Real end-to-end runs
> against `google/gemma-4-31B-it`:

| Run | Calls | Input tok | Output tok | Cost | Time |
|---|---:|---:|---:|---:|---:|
| 6 | 19 | ~35k | ~31k | **$0.098** | 175.6s |
| 9 | 19 | — | — | $0.092 | 175.5s |
| 10 | 19 | — | — | $0.104 | 337.6s |

**Output exceeds input**, which is the opposite of the modelled shape and is the
whole story of this integration: `gemma-4-31B-it` is a **reasoning model** that
spends output tokens deliberating before it writes any JSON.

**The output ceiling is a cliff, not a dial.** Set slightly too low it does not
return a shorter answer — it returns an **empty** one, having paid full latency
and full token cost. Raising it alone moved a real run from 23 → 81 → 160 fields
with nothing else materially changed. Tuning rule: **squeeze input, never squeeze
output.**

Cost is not the binding constraint at any setting measured — $0.098 against a
$0.75/order cap is **13%**, including reading all 40 pages. Latency is.

Measured on run 14 (`3.6/_run14.json`), `gemma-4-31B-it` everywhere:

```
17 calls        input 27,561 tokens        output 74,708 tokens        $0.0832
```

| Config | Serverless | +15% retry | Batched (−50%) | @4,500 orders/mo |
|---|---:|---:|---:|---|
| **Gemma 4 31B IT everywhere** (measured) | **$0.0832** | $0.0957 | **$0.0416** | **$374 / $431 / $187** |

Add the existing judge (`gpt-oss-120b`, ~$0.014/order) for total cost of order.

Cost is **output-dominated**: at gemma's $0.39/$0.97 per million, the 74,708
output tokens are $0.0725 of the $0.0832 — **87% of the bill** — against $0.0107
for all 27,561 input tokens. Every output token trimmed helps latency and cost
identically; input is nearly free here.

### 1.5 Non-LLM stage timings

| Stage | Naive | Optimized | Note |
|---|---:|---:|---|
| `get_text()` ×40 | 0.79s | 0.79s | needed for classification |
| `get_fonts()` ×40 | 0.04s | 0.04s | needed |
| `get_images()` ×40 | 0.08s | 0.08s | needed |
| **`get_drawings()` ×40** | **5.02s** | — | **replaced** |
| `get_cdrawings()` on 7 image-less pages only | — | 0.76s | returns dicts, not objects |
| **Total probe** | **6.33s** | **1.51s** | **4.8s recovered** |
| Render 1 page @150 DPI | 0.19s | 0.19s | |
| Render 19 pages sequential | 2.48s | — | ~0.13s/page, CPU-bound |

**The probe fix is the cheapest win in the document.** `digital | flattened | scanned` is
decided by chars + fonts alone; drawings are only needed to separate `text_dense` from
`photo_grid`, and image count already does that.

> Rendering is CPU-bound and scales with cores. On a 1-core box, threads and processes both
> *lose* to sequential. On the production VPS, use chunked processes (one `fitz.open` per
> worker, not per page). Better still — see §4, L5 — never let rendering block at all.

---

## 2. Why the vision model must not judge

The intuitive design is: screenshot a page, attach the checklist items that relate to it,
let the model return PASS/FAIL/VERIFY. It is the natural first instinct. It cannot work,
and the reason is structural rather than a matter of prompt quality.

### 2.1 The numbers

All 90 ESA items were classified by the evidence each one actually requires:

| Class | Meaning | Count | % |
|---|---|---:|---:|
| **A** | single-section fact | 39 | 42% |
| **B** | cross-page fusion / arithmetic | 26 | 28% |
| **C** | **external document required** (loan file, contract, title, investor guides) | 9 | 9% |
| **V** | visual inventory (photos, sketch legibility, maps, graphs) | 9 | 9% |
| **G** | gated → N/A unless a predicate holds | 8 | 8% |

> **Items needing more than one page: 50 of 91 = 54%.**
> **Items answerable from ONE page with no external document: 23 of 91 = 25%.**

A page-scoped verdict call is structurally blind to 75% of the checklist.

### 2.2 Three worked failures from the actual report

**Item 98 — "Do any apparent defects require repairs?"**

| Page | Says |
|---|---|
| p1 | Apparent Defects, Damages, Deficiencies: **None** |
| p26 | Apparent Defects: **None** · Market Value Condition: **As Is** |
| p19 | Contract: *"the seller is required to repair the septic system to proper working order prior to closing"* |
| p8 | Photo: *"Dwelling Rear – Septic Tank"* (excavated) |

**Every page passes in isolation.** Show gemma page 1 with item 98 attached and it returns
PASS — a false negative on the most serious issue in the report. The finding exists only in
the join.

**Items 86 / 87 — bracketing.** Comps 1–3 are on p21, comps 4–6 on p23.

```
bedrooms  subject 4 | comps 3,3,3,4,3,3  → max 4, not bracketed ABOVE  → FAIL
baths     subject 3 | comps 2,2,2,2,2,2  → every comp below subject     → FAIL
```

From p21 alone you would conclude "3,3,3 — not bracketed" and be right by accident. This is
the same partial-read trap that manufactured the false $310k-below-range finding during the
manual audit.

**Item 75 — concessions.** Needs p21 + p23 for the five concessions, **plus** p18 for the
market context.

```
comp1 $5,350 → $0        comp4 $9,275 → $0
comp2 $7,000 → $0        comp5 $6,000 → $0
comp3 $10,000 → $0       (p18: 65.3% of market sales carry concessions)
```

Three pages, one finding.

### 2.3 The nine items nothing can fix

Items **1, 2, 5, 7, 11, 12, 43, 47, 48, 85** require a document the appraisal does not
contain. A vision model shown a screenshot has no way to know it *cannot* know, so it will
invent a verdict on *"Does the borrower's name match the loan file?"*

This forces a taxonomy addition — see §6.3, `NOT_DETERMINABLE`.

### 2.4 The four non-geometric reasons

1. **Multi-AMC economics.** Fused: `orders × AMCs × vision`. Separated:
   `orders × vision + orders × AMCs × judge`. Three AMCs on one report: **$0.135 fused vs
   $0.087 separated** — and fused means *a new AMC requires re-reading every PDF.*
2. **Ground truth becomes unwriteable.** Precision/coverage scoring only works on facts.
   Build fixtures on verdicts and every checklist edit invalidates the entire test set.
3. **Checksums die.** `net_adj == sum(line_adjustments)` is checkable. *"FAIL: concessions
   not adjusted"* is not. You would be shipping unverifiable output from a mid-tier 31B
   model into a mortgage decision.
4. **It collapses the audit trail.** *"Trust AI but never fully accept the verdict"* requires
   perception and policy to be separable. Fused, a reviewer seeing FAIL cannot tell whether
   the model misread the page or misapplied the rule.

### 2.5 Where the instinct *is* right

Nine items (**21, 22, 23, 24, 33, 42, 59, 72, 90**) are genuine vision tasks — *"are the
required photos present"*, sketch dimension legibility, the comparable map, market graphs.
Handle these with a targeted vision call that returns a **structured inventory**:

```json
{"photos_present": ["subject_front","subject_rear","street_scene",
                    "comp1_front","comp2_front", "..."],
 "photos_missing": [], "page": 25}
```

A fact, not a verdict. The judge decides whether the inventory satisfies the item.

---

## 3. The five layers

```
 PDF ──▶ [0] PROBE ──▶ [1] LEDGER ──▶ [2] VERIFY ──▶ [3] FUSION ──▶ [4] JUDGE ──▶ verdicts
         1.5s, code    vision model   code, free     code, free      text LLM
         ◀──────────── identical for EVERY AMC ────────────▶        ◀── per AMC ──▶
```

The vertical line matters more than the boxes. Layers 0–3 depend only on the **form**
(UAD 3.6). Layer 4 depends on the **checklist**. That seam is what makes a new AMC a
config file rather than an integration.

### Layer 0 — Structural probe · `page_map.py` · 1.5s

Classify the document, build the page map, decide the route. Deterministic, no LLM.
Emits `document_class`, `uad_version`, per-page `kind`, and the skip list.

### Layer 1 — Fact Ledger · vision model · the only expensive layer

The model's contract is narrow and absolute:

| Rule | Statement |
|---|---|
| **R1** | Transcribe only what is visibly printed. Never infer, complete, or normalize. |
| **R2** | One section per call. Never the whole document. |
| **R3** | Abstention is a first-class answer. `null` is correct; a plausible guess is a defect. |
| **R4** | Every non-null value carries `page`, `source_text`, `label_text`. |
| **R5** | Never emit an opinion, verdict, or assessment. Values only. |
| **R6** | `temperature=0` + JSON schema. |

The ledger is keyed by the **3.6 form**, not by any AMC's questions — roughly 250–300 fields
across the 34 section names. Written once, serves every client forever.

Every value is shaped:

```json
{"value": 2137, "page": 8, "source_text": "2,137 Sq. Ft.",
 "label_text": "Finished Above Grade"}
```

> **`temperature=0` works on Together open models.** The HTTP-400 warning that applies to
> Claude Opus 5 / Sonnet 5 is Anthropic-specific. Determinism here = `temperature=0` +
> tight JSON schema + one page per call.

### Layer 2 — Arithmetic verification · `verify.py` · free

Nine closed-form identities, each a correctness oracle needing no LLM and no ground truth:

```
sum(line_adjustments)          == net_adjustment_total
sale_price + net_adjustment    == adjusted_price
sum(sketch area line items)    == total_living_area          (±2)
sum(comparable weights)        == 100%
adjusted_price × weight        == weighted_contribution
sum(weighted_contributions)    == opinion_of_value
room_summary counts            == reported totals
sum(abs(line_adjustments))/sale_price == gross_adjustment_pct
sum(listing DOM)               == total_DOM
```

Verified against the sample — all close:

```
Comp #1 net:      −23,800 +9,000 +11,600 +5,000 +5,000 −12,000 +3,500 = −1,700   ✓
Comp #1 adjusted: 320,000 + (−1,700)                                  = 318,300  ✓
Sketch:           128.38 + 1018.58 + 892.53 + 97.87 = 2137.36 → 2,137            ✓
Rooms:            p8 "4-Bedroom, 3-Bath Full" = Total BR 4 / Baths-Full 3        ✓
```

**These test whether extraction is faithful to the page — never whether the appraiser
complied.** Compliance belongs to the judge. Two different questions; this layer never
answers the second.

### Layer 3 — Fusion & consistency · free · §4

### Layer 4 — Judge · text-only · per AMC

One item, one small packet of bound facts, no image. Cheap, cacheable, regression-testable,
and re-runnable per AMC without touching the PDF.

---

## 4. Cross-verification — the report is its own answer key

The central observation: **a UAD 3.6 report states the same fact in several places.** You are
already extracting those pages, so confirming a fact from six independent sources costs
**zero extra calls.**

### 4.1 The redundancy map (measured on this report)

| Canonical fact | Sources | Pages | Answers items |
|---|---:|---|---|
| `gla_above_grade` | **6** | 6, 7, 8, 21 | 34 |
| `opinion_of_value` | 5 | 1, 26, 33, 35 | 97 |
| `contract_price` | 5 | 1, 19, 21, 26 | 74, 97 |
| `overall_condition` | 5 | 1, 7, 8, 14, 21 | 48 |
| `bedrooms` | 4 | 6, 8, 21 | 35 |
| `baths_full` | 4 | 6, 8, 21 | 35 |
| `effective_date` | 3 | 1, 26, 27 | 76 |
| `year_built` | 2 | 7, 21 | 83 |
| `appraiser_license_expiry` | 2 | 37, 40 | 6, 100 |
| `comp_adjusted_prices` | 2 | 21, **33** | 74, 91, 92 |
| `carport_area` · `outbuilding_area` · `deck_area` | 2 each | 6, 13, 14 | — |

**13 canonical facts · 44 independent observations · 3.4 sources per fact · zero extra cost.**

GLA alone appears six times: sketch total (p6), sketch line-item sum (p6), sketch commentary
prose (p7), interior finished-above-grade (p8), level-and-room-detail area (p8), grid subject
column (p21).

### 4.2 One mechanism, three outcomes

**CONFIRMED** — all sources agree.

```
gla_above_grade: 2137 from 6 independent sources → CONFIRMED
→ item 34 ("sq ft consistent with the sketch?") answered PASS deterministically.
→ NO JUDGE CALL AT ALL.
```

Items 34 and 35 literally *are* consistency checks. The mechanism answers them for free.

**REPAIR** — one source dissents; the majority outvotes it.

```
p8 misread as 2737 (a 1→7 flip); five other sources say 2137
→ REPAIR: re-extract ONE PAGE, not the order — and the expected value is already known.
```

Majority-vote self-healing. The repair is targeted and instantly verifiable.

**CONFLICT** — sources genuinely disagree in the report.

```
condition: p1 C4, p7 C4, p14 C4 | p8 C3, p21 C3
→ CONFLICT: not an extraction bug. A finding. Route to judge / VERIFY.
```

### 4.3 Arithmetic beats pixels on ambiguous digits

The sketch states a Level-1 total of `2137.35`. Three clearly-read line items sum to
`2039.49`. Therefore the fourth item **must** be `97.86`.

```
'97.87' is correct.  '97.07' is a misread.
```

Resolved by subtraction, without looking at the page again. No vision model, at any quality
level, gives you this.

### 4.4 Page 33 validates the 4-page comparable grid

The highest-value link in the graph. The grid spans p21+p22 (comps 1–3) and p23+p24
(comps 4–6). The **Value Reconciliation** table on p33 independently restates every comp's
adjusted price.

```
p21+p22 comp1:  320,000 + (−23,800+9,000+11,600+5,000+5,000−12,000+3,500)
              = 320,000 + (−1,700) = 318,300
p33 table, comp1 ............................ = 318,300      ✓ MATCH

weights: 20 + 15 + 25 + 15 + 25 + 0 = 100%                   ✓
contrib: 318,300 × 0.20 = 63,660                             ✓
```

**The hardest, most dangerous region — the one where a column shift does the most damage —
gets a free second opinion from an unrelated part of the document.**

### 4.5 Verification ladder — escalate only when cheaper layers can't settle it

| Tier | Mechanism | Cost | Catches |
|---|---|---|---|
| 1 | Arithmetic oracles | free | column shifts, digit flips, dropped rows |
| 2 | Consistency graph (n-source vote) | free | single-page misreads → targeted repair |
| 3 | Provenance check (`source_text` present on page) | free | fabricated values |
| 4 | Targeted re-extract of one page @200 DPI | ~1 call | what tiers 1–3 flagged |
| 5 | Different-model re-read (a non-Qwen family vs Gemma) | ~1 call | correlated single-model failure |
| 6 | Judge → VERIFY card | 1 call | genuine report conflicts |

> **Delete "two-pass on numerics" from the plan.** The consistency graph *is* the second
> pass, and unlike a blind re-extraction it is free and it tells you *which* page was wrong.

---

## 5. The 60-second budget

Modeled as a DAG over 400 simulated runs. Stage timings for probe and render are **measured**;
vision and judge latencies are **estimates to be replaced with your own measurements**.

### 5.1 Target profile

```
probe          + 1.50s  ->  t= 1.50s   ###
first_render   + 0.26s  ->  t= 1.76s
vision         +15.33s  ->  t=17.09s   #################################
retry          +12.17s  ->  t=29.25s   ##########################
fusion         + 0.05s  ->  t=29.30s
judge          + 3.99s  ->  t=33.29s   ########
rollup         + 0.10s  ->  t=33.39s

21 vision calls · 8 batched judge calls · 8 hedged · headroom to 60s: 26.6s
```

**p50 33.4s · p95 41.3s · p99 44.5s**

### 5.2 Ablation — what each lever is worth

| Config | p50 | p95 | Note |
|---|---:|---:|---|
| naive: 4 lanes, no skip / hedge / pipeline | 59.5 | 59.5 | **100% of runs hit the clamp and degrade** |
| + page-map skip (L1) | 59.5 | 59.5 | still lane-starved |
| + 24 lanes (L2/L3) | 36.9 | 51.6 | **biggest single win** |
| + hedged requests (L4) | 34.0 | 42.0 | **p95 −9.6s** |
| + pipelined tier-1 judging (L5) | **33.4** | **41.3** | target |
| + per-call verify & retry (no barrier) | **28.1** | **38.1** | further −3.2s at p95 |

> The 59.5s in the naive rows is **the deadline clamp firing, not a completion.** Every
> naive run is shipping unverified regions as VERIFY.

### 5.3 The six levers

**L1 — Skip.** 16 of 40 pages are pure photo grids. Never render them, never send them.

**L2 / L3 — Lanes, critical path first.** Wall clock across a wave is `max()`, not `sum()`.
Lane sizing plateaus exactly where theory says it should:

```
lanes  4 → p50 59.5s        lanes 21 → p50 33.3s
lanes  8 → p50 39.4s        lanes 24 → p50 33.3s
lanes 12 → p50 33.6s        lanes 32 → p50 33.3s
```

**21 lanes = 21 vision calls = one wave.** Beyond that there is nothing to gain; below it,
calls queue and the wave degenerates from `max()` into `sum()`. Dispatch the grid pages
(p21–24) **at t=0** — they are the slowest, the most retry-prone, and everything gates on
them.

**L4 — Hedge the tail.** With 21 calls in flight, one p99 straggler sets the wall clock.
At p75, fire a duplicate of any call still running and take whichever returns first.
≈10% more tokens (≈$0.005/order) for **9.6s off p95.** Best value in the design.

**L5 — Never barrier.** Three places:

- Render behind the network. Only the first grid pair blocks (0.26s); the rest overlaps with
  in-flight calls.
- Judge tier-1 items as their page lands. 39 of 93 items are single-section, so ~42% of
  judging happens *during* the vision wave.
- **Verify per call, retry immediately** rather than after the whole wave. The 12.17s `retry`
  bar is mostly dead time; this dissolves it (p50 33.4 → 28.1s).

**L6 — Deadline-aware degradation.** At **T−8s** stop starting new work. Anything unverified
ships as VERIFY with a stated reason. An order returning 90 verdicts + 3 VERIFYs at 52s beats
a perfect order at 95s — and it is doctrinally correct, because a human was always in the loop.

### 5.4 Sensitivity — the number that decides everything

| vision p50 / p95 | order p95 | within 60s |
|---|---:|---|
| 7.0 / 15.0s | 41.7s | 100% |
| 10.5 / 22.5s | 58.3s | 100% |
| 14.0 / 30.0s | clamps | degrading |
| 21.0 / 45.0s | clamps | degrading |

**You have roughly 1.5× headroom on vision latency.** Past that, you begin shipping VERIFYs.
This is the first thing to measure, and it is the one input that could not be verified here.

---

## 6. Multi-AMC design

Different AMCs send different checklists. Different orders within one AMC can differ. The
architecture must absorb that without touching extraction.

### 6.1 The seam

```
Fact Ledger  ──── AMC-agnostic, form-driven ────  written ONCE
     │
     ├──▶ compiled bundle: EQUITYSOLUTIONS  ──▶ verdicts
     ├──▶ compiled bundle: AMC_B            ──▶ verdicts
     └──▶ compiled bundle: AMC_C            ──▶ verdicts
```

Same order, three AMCs = **one** extraction, **three** judge passes. Onboarding a new AMC is
one overlay file.

### 6.2 The compiler

Raw AMC CSVs are hostile inputs. The ESA file alone has: no polarity column, inverted logic,
compound questions, wh-questions in a yes/no grid, 10 missing IDs, cp1252 mojibake, and
thresholds stated only in prose. **Compiling means making every one of those explicit before
a judge ever sees it.**

Compiled output for ESA:

```
bundle  EQUITYSOLUTIONS / UAD 3.6 / hash d5bfdfe64ee53e89
items   93 (after splitting compound rows)
polarity        GOOD 57 · PROBLEM 34 · WH 2
evidence class  A 39 · B 26 · C 9 · V 9 · G 10
gated           26, 60, 61, 62, 63.1, 63.2, 81, 84, 99.1, 99.2
need ext doc    1, 2, 5, 7, 11, 12, 43, 47, 48, 85
flagged defect  47, 48, 52, 70
```

Each compiled item carries:

| Field | Purpose |
|---|---|
| `polarity` | `GOOD` / `PROBLEM` / `WH` — is "Yes" healthy or a finding? |
| `gate` | predicate over facts; false → N/A **without calling the judge** |
| `binds` | the fact paths the judge is allowed to see — and nothing else |
| `thresholds` | AMC numbers lifted out of prose |
| `needs_external` | documents required beyond the appraisal |
| `split_of` | set when one raw row became several answerable items |
| `defect` | carried forward for human review, **never silently fixed** |

### 6.3 Three defects the compiler forced into the open

**Polarity is absent from the CSV entirely — and 34 of 93 items are "Yes = problem"**
(8, 18, 19, 44, 54–57, 66–68, 75, 93, 98 …). Without a polarity column a judge marks healthy
answers as rejects. This is the single largest silent failure mode in the system, and one
column fixes it.

**Item 70's logic is inverted.** The CSV reads *"If under these recommended mileage, pleased
esnure commentay."* Commentary is required when comps **exceed** the limit. It fires on this
very report — **comp #3 at 7.59 miles** against a 5-mile rural guideline. The compiler records
`commentary_required_when: OVER` **and** flags the defect, so a human confirms with the AMC
rather than the system silently patching the client's document.

**Missing thresholds.** Item 52 (*"median DOM reflective of an active market?"* — 63 days,
yes or no?), items 47/48 (*"meet investor criteria"* — which investor?). These live in the
overlay as explicit, AMC-confirmable numbers. **Never let the judge improvise one.**

### 6.4 Verdict taxonomy

| Verdict | Meaning | Decided by |
|---|---|---|
| `PASS` | condition satisfied | judge |
| `FAIL` | violated; reject language drafted | judge |
| `VERIFY` | human judgment genuinely required | judge |
| `NOT_APPLICABLE` | gate predicate false | **code, never the judge** |
| `NOT_DETERMINABLE` | needs a document we do not have | judge |
| `UNREAD` | fact never extracted or failed its checksum | code |

Two additions matter:

- **`NOT_DETERMINABLE` ≠ `VERIFY`.** VERIFY means a human must exercise judgment.
  NOT_DETERMINABLE means no amount of staring at the appraisal can settle it, because the
  answer lives in the loan file. Different queue, different reviewer action, different SLA.
- **`UNREAD` is an extraction defect, not an appraiser defect.** It must never become a FAIL.

> Because SHAL already ingests engagement letters, items **2, 5, 7** upgrade from
> NOT_DETERMINABLE to cross-document fusion the moment those fields are bound.

### 6.5 Gates are evaluated in code

Verified against the real report:

```
N/A     items 60/61/62/81 (PUD block)     ← subject.is_pud == True
ACTIVE  item 84 (non-public utilities)    ← site.utilities.sewer != 'Public'
N/A     item 26 (converted areas)         ← dwelling.converted_area not in (None,'None')
N/A     item 63 (refinance + listed)      ← assignment.reason == 'Refinance'
```

Item 84 correctly activates — the subject is on septic. Ten items resolve to N/A without
spending a single judge call. **Required-but-empty sections must route to VERIFY, never N/A.**

### 6.6 STOP conditions bypass the checklist

| ID | Predicate | Text |
|---|---|---|
| STOP1 | `form_type_ordered != form_type_found` | Form type mismatch |
| STOP2 | `overall_condition in ('C5','C6')` | Subject in C5/C6 condition |
| STOP3 | `hbu.present_use_is_hbu == False` | Existing use is not highest and best use |
| STOP4 | `site.zoning_compliance == 'Illegal'` | Subject use is ILLEGAL |
| STOP5 | `subject.units_total > 4` | Exceeds 4 units |

Evaluated first, in code. If any fires, the order short-circuits to a human immediately.

---

## 7. Model selection on Together

### 7.1 Serverless vs dedicated — read the price column

In the Together catalog, **a price means serverless** (per-token, callable now).
**"n/a" means dedicated-only** (provision GPUs, pay per hour).

**The entire Qwen3-VL line — including the small 8B — is `n/a`.** Qwen3-VL-32B-Instruct
(DocVQA 93.3%, OCRBench 86.9%) is dedicated-only and therefore off the table at current
volume:

- Dedicated H100 ≈ **$6.49/hr** ≈ **$4,672/month** per GPU, metered even at zero requests.
- Break-even vs serverless for a 70B-class model ≈ **5B tokens/month**.
- Your volume ≈ 150 orders/day × 159K tokens × 30 ≈ **717M tokens/month** — **7× below**.
- Cold starts on a 33B model would also break the 60s target at sparse traffic.

**Revisit dedicated only if you reach thousands of orders/day *and* serverless proves
insufficient on the grid.** It is a growth lever, not a starting point.

### 7.2 Serverless models that actually accept images

| Model | $/1M in–out | Weights | Role |
|---|---|---|---|
| **Gemma 4 31B IT** | 0.39 / 0.97 | open | **in use everywhere** — sections, grid and escalation |
| Qwen3.6-Plus | 0.50 / 3.00 | closed | older multimodal flagship; expensive output; untested here |
| MiniMax M3 | 0.30 / 1.20 | — | alternative serverless VLM |
| Kimi K3 | 3.00 / 15.00 | open | most capable, far too expensive here |

**Retired candidates — do not reintroduce.** `Qwen3.5-9B` and `Qwen3.7-Plus` were
both trialled against this document and rejected: the 9B truncated, and the Plus
returned HTTP 400 on this input shape. They are removed from the pricing table,
the tier defaults and this catalogue so they are not picked up again as options.

**Traps in the same catalog:**

- `Qwen3.7 Max`, `Qwen2.5 7B Turbo` — priced and serverless, but **text-only**.
- `Qwen Image`, `Qwen Image 2.0`, `Qwen Image 2.0 Pro` — these **generate** images
  (text→image). The opposite of what is needed. The name is misleading.
- `gpt-oss-120b` ($0.15/$0.60) — the existing judge. **Text-only**, cannot be the extractor.

### 7.3 Tiered assignment

```
sections (11 calls, 100 DPI)  →  Gemma 4 31B IT    verified serverless Text+Image + JSON Mode
grid     ( 6 calls, 110 DPI)  →  Gemma 4 31B IT    densest, highest-stakes region
escalate ( on checksum fail)  →  Gemma 4 31B IT    see below — NOT yet a different family
judge    (~8 batched calls)   →  gpt-oss-120b      text-only, already in place
```

**The tiering is currently flat, and that is a known compromise.** The two models
that would have made it a genuine cross-family escalation were retired after
testing, so the escalation tier retries the *same* model — which cannot catch a
correlated failure. What it escalates instead is mechanism: DPI (110 → 200) and a
re-prompt carrying the arithmetic error. Point `VISION_MODEL_ESCALATE` at a
verified different family to restore an uncorrelated second opinion.

Escalating to a different model *family* matters: retrying the same model on the same pixels
tends to reproduce the same error.

### 7.4 Batch API

50% discount, 24-hour processing window. Batch the overnight bulk; keep serverless for the
real-time reviewer flow, since batching forfeits the 60s target.

---

## 8. Build order

| # | Task | Needs LLM? | Why first |
|---|---|---|---|
| 1 | `consistency.py` + `verify.py` | **no** | No API key, no ground truth. Alone they answer items 34, 35, 48, 74, 83, 97 deterministically — and tell you immediately whether the rest is worth building. |
| 2 | Optimized probe (`get_cdrawings`, image-less pages only) | no | 4.8s recovered in an afternoon |
| 3 | Raise the 8-page cap; make it config | no | Until then every 3.6 run is blind to pp. 9–40, where the entire valuation lives |
| 4 | **Measure real vision latency + grid accuracy** | yes | **The gate.** Decides page-render vs column-crop, and whether 60s holds |
| 5 | Fact Ledger schema (~250–300 fields) | — | Largest single item. Do it *after* step 4 |
| 6 | Lanes + hedging + per-call retry | — | Takes p95 from ~59s to ~38s |
| 7 | Compile an overlay for AMC #2 | — | Proves the seam is real |

**In parallel, and highest leverage of all: ask the AMC for one native TOTAL export.**
If that PDF carries a real text layer, `pdf_digital` lights up, vision becomes a cheap
deterministic *fallback*, and the hardest problem in this document disappears. One email may
delete the grid-legibility risk entirely. Send it before building the vision path.

---

## 9. Open questions and honest caveats

| # | Item | Status |
|---|---|---|
| 1 | **Native vs flattened PDF** | Unresolved and upstream of everything. Ask the AMC. |
| 2 | **Does Together downsample past the 2×2 tile cap?** | Unknown. If it does, a 4-column grid at ~1120px (~280px/column) may blur. Mitigation is known: crop to per-column strips (1×2 tiles = 3,202 tokens, full vertical detail) — which is also the plan's own "extract by column" defense. |
| 3 | **Vision latency (p50/p95)** | **Estimated, not measured.** Sits in one place at the top of `scheduler.py`. Replace it first. |
| 4 | **Field-level precision of the chosen VLM on your grid** | **Unmeasured.** The "42% precision" figure was the *old broken* pipeline; the "13 correct / 4 partial / 14 wrong" audit was manual reading, not this model. Gemma 4 31B now measures **100% precision (15/15)** on a clean spot-check of run 12, but coverage is only 42.8% and no comparable's arithmetic has yet closed. |
| 5 | **`binds` mappings** | A first draft derived from one report. Review, don't trust. |
| 6 | **Consistency graph portability** | Drawn from a single report. Validate the redundancy holds across the 3-order fixture set — a TOTAL template change could move where facts are restated. |
| 7 | **Checklist thresholds** | Items 47, 48, 52 carry assumed defaults. Confirm with the AMC before production. |
| 8 | **Compiled-bundle safety** | Compile 3.6 to a **new bundle hash under a separate key**. Never `--force` over the active 2.6 bundle — it holds hand-tuned bindings that exist only there. |

### Validation methodology

There is no ground truth for 3.6 today. Build it:

1. Take **3 UAD 3.6 orders** (the standing minimum-three rule — never judge from fewer).
2. Vision-extract every field, page by page.
3. **Hand-verify against the rendered pages.** The expensive, unavoidable step.
4. Freeze as `testfiles/uad36/<order>/ground_truth.json`.
5. Score every change as **precision** (of what it emitted, how much is right) and
   **coverage** (of the schema, how much it filled) — **reported separately**.

**Add the checksum suite as a permanent regression gate.** It needs no ground truth at all:
any report whose comp arithmetic fails to close is either a bad extraction or a genuinely
broken report, and both deserve a card.

---

## Appendix A — Findings verified on the sample report

Each of these was computed from the actual document, and each requires evidence from more
than one page.

| Item | Finding | Pages fused |
|---|---|---|
| 86 | Bedrooms **not bracketed above** — subject 4, comps 3,3,3,4,3,3 | 8, 21, 23 |
| 87 | Bathrooms **not bracketed** — subject 3 full, **all six comps have 2** | 8, 21, 23 |
| 75 | **5 comps with real concessions, every one adjusted $0** (market: 65.3% of sales carry concessions) | 18, 21, 23 |
| 93 | Comp #2 gross adjustment **29.3%** vs 25% guideline (others 21.8 / 14.2 / 10.2 / 10.9%) | 21, 23 |
| 70 | Comp #3 at **7.59 mi** vs 5-mi rural guideline — *and the CSV rule is inverted* | 15, 21 |
| 83 | Comp #4 built **1901** vs subject 1979 — Δ78 years | 7, 21, 23 |
| 98 | **"As Is" + defects None, but contract mandates septic repair** | 1, 8, 19, 26 |
| 69 | Prior sale 09/29/2023 at **$315,000** vs current contract $300,000 | 19 |
| 55/57 | p15 reconciles "In Balance" / trend stable, while supply 3.5→5.0 mo, DOM 45→63, price −1.5% | 15, 16 |
| 6 / 100 | License expires 07/31/2027, signed 07/27/2026 → **active** (PASS) | 37, 40 |
| 34 | Sketch 2,137.36 → 2,137 = interior finished above grade 2,137 → **PASS** | 6, 8 |

### The false-positive trap to encode

A naive item-91 rule (*"market declining → all time adjustments should be negative"*) would
flag three **correct** adjustments. The p16 monthly matrix is cumulative-to-effective-date and
**not monotonic** (Jul −1.5%, Aug −1.1%, Sep −0.6%, Oct 0.0%, Nov +0.6%, Dec +1.1%):

```
Comp #1, Dec 2025 → +1.1% × $320,000 = $3,520  ≈ +$3,500   ✓ correct
Comp #2, Aug 2025 → −1.1% × $274,500 = $(3,020) ≈ −$3,000   ✓ correct
Comp #3, Jun 2025 → −1.7% × $320,000 = $(5,440) ≈ −$5,400   ✓ correct
```

**The judge needs the full page-16 trend matrix in context, not just the headline −1.5%.**
Extract the 36-month matrix as a first-class field.

---

## Appendix B — File manifest

| File | Layer | Needs API key |
|---|---|---|
| `probe_and_price.py` | 0 | optional — cost model runs without one; live grid test needs one |
| `together_vision.py` | 1 | yes |
| `verify.py` | 2 | **no** |
| `consistency.py` | 3 | **no** |
| `item_analysis.py` | — | **no** — the evidence-class classification |
| `checklist_compile.py` | 4 | **no** — raw CSV → compiled bundle |
| `judge.py` | 4 | yes (gate evaluation runs without one) |
| `scheduler.py` | — | **no** — wall-clock DAG model |

---

## Appendix C — Sample document ground truth

| Field | Value | Page |
|---|---|---|
| Form | Uniform Residential Appraisal Report, Fannie/Freddie **Sept 2024** | all (footer) |
| Vendor | TOTAL by a la mode; printed via **PDFium** | metadata + footer |
| Subject | 1465 Turner Rd NE, Rome, GA 30165 (Floyd Co.) | 1, 2 |
| Assignment | Purchase · contract **$300,000** · opinion **$310,000** | 1, 19, 26 |
| Effective / signed | 07/24/2026 · 07/27/2026 | 1, 40 |
| Appraiser | Eric Colcord, CR359036, GA, expires 07/31/2027 | 1, 37, 40 |
| Lender | Homeowners Financial Group USA, LLC | 1 |
| Improvements | Ranch, 1979, 2,137 sf, 4 BR / 3 full baths, Q4 / C4 | 6, 7, 8, 14 |
| Site | 40,511 sq ft, 1 parcel, A-R zoning, Fee Simple | 1, 2, 3 |
| Utilities | Electric + water public; **sewer private/septic** | 3 |
| Comparables | **6** (5 settled + 1 pending), pp. 21–24 | 21–24 |
| Approaches | Sales Comparison only; Cost & Income excluded | 26 |
| Market | −1.5% price trend · DOM 63 (+18) · supply 5.0 mo (+1.5) · 65.3% w/ concessions | 15–18 |
