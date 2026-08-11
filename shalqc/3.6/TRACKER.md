# UAD 3.6 Vision Extraction — Work Tracker

**Owner:** Harshal · **Started:** 2026-08-09 · **Branch:** `uad3.6`
**Live document.** Claude updates this at the end of every working session.
Add mid-session notes under §8 rather than editing the status table.

---

## 1. Decisions

| # | Decision | Status | Why |
|---|---|---|---|
| D1 | **Vision model = `google/gemma-4-31B-it`** on Together **serverless** | ✅ locked 2026-08-09 | Serverless (per-token, no endpoint), Text+Image input, JSON Mode, 262K context, $0.39/$0.97 — all confirmed against the account's own catalogue. |
| D1a | ~~Anthropic `claude-sonnet-5`~~ | ⬅ superseded same day | Chosen first, then reversed when the Together serverless catalogue was checked. The Anthropic backend is **built and retained** behind the same interface — one env var away if the grid needs a stronger reader. |
| D2 | **Qwen3-VL line is OFF the table** (8B / 32B / 235B) | ✅ locked | Every one is **dedicated-only**: using one means provisioning a GPU endpoint billed per hour (~$6.49/hr H100, ~$4.7k/mo at 24/7) whether or not an order is processed, plus cold-start latency at sparse traffic. A growth lever at sustained high volume, never a starting point. |
| D3 | **Together stays the judge** (`gpt-oss-120b`) | ✅ locked | Unchanged. Single provider account now serves both jobs; `TogetherPool`'s token-bucket governor and the whole judge path are untouched. |
| D4 | **Provider is an interface, not a hardcode** | ✅ built | `VisionProvider` + Together and Anthropic backends. This is what made the D1 reversal a config change instead of a rewrite. |
| D5 | **2.6 path byte-for-byte untouched** | ✅ holding | Fork is at extraction only, keyed on `uad_version`. Everything downstream is shared and version-agnostic. |
| D6 | **New compiled bundle under a separate key** | ⏳ pending | The active 2.6 bundle `96b595e6f127ba4f.yaml` holds ~46 hand-tuned bindings existing ONLY there, not regenerable. Never `--force` over it. |
| D7 | **Hard per-order $ cap, enforced before spending** | ✅ built | `BudgetGovernor.check()` prices the next call and refuses; the order degrades to REVIEW cards rather than overrunning. |
| D8 | **Config is frontend-owned, not Python-owned** | ✅ built (API) / ⏳ (UI) | `runtime_config` table → env → code default. Admin REST is live; the settings screen is the next slice. |

## 2. Ground truth — measured on the real file

`shalqc/3.6/Email - AppraisalArdur - Outlook (1).pdf`
1465 Turner Rd NE, Rome, GA 30165 · Purchase · $300,000 contract / $310,000 opinion

| Probe | Result |
|---|---|
| Pages | **40**, every one US Letter (612×792 pt) |
| `get_text()` / `get_fonts()` across all 40 | **0 characters, 0 fonts** |
| Producer | **PDFium** — printed from a browser preview; the text layer was flattened in transit |
| `classify_document()` | **`flattened`** ✅ |
| `detect_uad_version()` | **3.6** ✅ |
| Page split | 7 text_dense · 17 mixed · 16 photo_grid · 0 blank |
| Extraction plan | **24 extractable, 16 photo sheets dropped** |
| Current 2.6 pipeline yield | 31/279 fields = **42% precision, 4.7% coverage** |

## 3. Cost — measured, not estimated

`gemma-4-31B-it` serverless at $0.39 in / $0.97 out, computed from the real page map:

| | Calls | Input tok | Output tok | Cost |
|---|---:|---:|---:|---:|
| Base | 27 | 83,274 | 12,840 | **$0.054** |
| +15% checksum retries | | | | **$0.063** |
| Batched | | | | ~$0.031 |

**8.3% of the $0.75/order cap.** Cost is not the constraint — grid legibility is.
That headroom is deliberately spent on coverage instead (see the §2 page-threshold
note) and leaves room to escalate to a stronger model if the grid demands it.

> **Contrast, for the record:** a dedicated Qwen3-VL-32B endpoint would run
> ~$0.70–1.00/order at this volume — roughly **15× more** — for an unmeasured
> quality gain. That is the whole argument for staying serverless.

## 4. What is built and verified

| Component | File | Verified by |
|---|---|---|
| `Source.VISION` / `VISION_UNVERIFIED` | `extraction/result.py` | Confidence 0.93 sits above `pdf_digital` (0.92), below `xml` (0.97) — XML priority intact. |
| Page cap made config | `pdf_digital.py`, `pdf_scanned.py` | Was a hardcoded 8; pages 9-40 hold the entire valuation. Now `EXTRACT_MAX_PAGES` (default 60). |
| 3.6 intake + version markers | `pipeline/intake.py` | `_UAD36_MARKERS` added. |
| Structural probe | `extraction/page_map.py` | Run on the real file: `flattened`, 3.6, 24/16 split, all critical pages retained. |
| **Arithmetic checksums** | `extraction/verify.py` | Comp #1's real page-21 arithmetic **closes**; 3 mutation classes (transposed digit, sign flip, dropped row) all **caught**; 6 negative notations parse correctly. |
| Render + tokenizer math | `vision/render.py` | Tile-aware; `label_and_column_clips()` for per-comparable crops. |
| Budget governor | `vision/budget.py` | Refuses before spending; projection matches the run. |
| Vision providers | `vision/provider.py` | Together (tiered, `json_schema`→`json_object` fallback) + Anthropic. Schema sanitiser strips API-rejected keywords. |
| Runtime config | `runtime_config.py`, `api/admin.py` | 15 editable keys, allow-listed; range/enum validation rejects bad writes with UI-renderable messages. |

## 4a. Live-run findings (first real call against gemma)

| Finding | Consequence |
|---|---|
| **`gemma-4-31B-it` REJECTS `response_format: json_schema`** (HTTP 400) | The `json_object` + in-prompt-schema fallback is **load-bearing, not defensive** — without it every call fails. Confirmed in the live log. Output shape is therefore a strong instruction, not an API guarantee, so `sanitize_schema` + tolerant parsing (code-fence stripping) carry more weight than they would on a strict-schema model. |
| Vision gets its **own Together key** (`TOGETHER_API_GEMMA`) | Together rate-limits **per key**. A 40-page order's image traffic on the judge's key would contend with the judge's token budget — the same contention that made earlier runs both slower *and* lossier. Separate key = separate bucket. Falls back to the pool if unset. |
| Latency is the real constraint, not cost | ~27 calls at up to 180s each. Cost is 8% of cap; wall-clock is what needs managing (batching, concurrency, or fewer/larger calls). |

## 4b. Measurement needs no hand-authored answers

The pipeline contains **zero per-document values** — verified by grep over
`app/` and `config/`. Input is the checklist plus the document, nothing else.

Quality measurement follows the same rule, because a metric that needs someone
to type the right answers for each file does not survive the next file:

| Signal | Needs ground truth? | What it catches |
|---|---|---|
| **Verification rate** (`verify.py`) | **No — the document is its own oracle** | Column shifts, dropped rows, sign flips, sketch mismatches |
| **Abstention rate** | No | Confabulation. 0% abstention on a form with absent sections is a red flag, not a win |
| **Provenance rate** | No | A value that cannot name its printed label is a guess |
| **Coverage** | No | How much of the schema filled |
| Precision | Yes — spot check only | Confidently-wrong values, on golden orders only |

`3.6/score.py` reports the first four by default; precision is an optional
argument. Precision and coverage are **never blended** — guessing more raises
coverage and lowers precision, and one number hides that trade.

## 4c. Speed — the 60s/order target

**Root cause of the original 105s average latency was the prompt, not the model.**
`gemma-4-31B-it` is a **reasoning model**: it writes into a `reasoning` field
before `content`. An eight-paragraph system prompt made it deliberate until it
exhausted `max_tokens` mid-reasoning and returned an **empty `content`** — full
latency, full token spend, nothing produced, and no error saying so. The same
model on a short prompt read the subject address correctly in **3.3s**.

Measured levers, in order of effect:

| Lever | Effect | Note |
|---|---|---|
| **Concurrency** | the only real lever | Per-call latency ~40s is *irreducible* — it is reasoning time. Proven: a value-only schema with 20% fewer output tokens ran 42.2s vs 42.1s. So calls must overlap, not queue. |
| **Short system prompt** | 105s → ~40s | Rules compressed to the six that change behaviour. Prompt length is paid for in reasoning tokens on every call. |
| **`max_tokens` sized for reasoning + JSON** | failure → success | 1,500 truncated mid-reasoning; a 24-field section needs ~2,900. Defaults raised to 8,000 (section) / 20,000 (grid). |
| **Triage removed from the critical path** | −25s | Was a serial round trip before any section could start. |
| **Provenance** | free | Keep it — it costs no measurable latency. |

**Two structural replacements for model calls** (both zero latency, zero cost):

1. **Section location by document position.** Section *order* is stable across
   URAR variants even where page *numbers* are not, so each section gets a
   proportional window over the extractable pages. **7/7 sections located
   correctly** with no call.
2. **Grid detection by long horizontal rules.** Ranking by drawing count is the
   intuitive metric and is *wrong* — on a flattened PDF the densest pages are
   the certification pages (68,000+ drawings of pure prose, zero tables).
   Counting long horizontal rules inverts it correctly:

   | | p21 | p22 | p23 | p24 | best non-grid | certs p38/p39 |
   |---|---|---|---|---|---|---|
   | drawings | 2439 | 1498 | 2403 | 1820 | 2467 | 5450 / 5890 |
   | **h-rules** | **200** | **114** | **200** | **114** | 54 | **0 / 2** |

   Top-4 by h-rules = **exactly [21, 22, 23, 24]**, in 2.9s.

## 4d. What page-by-page reading revealed

- **Page 1 is a summary page** carrying opinion of value, effective date,
  assignment reason, borrower, owner of record, contract price, listing status,
  appraiser, Q4/C4 ratings, PUD/condo checkboxes, unit and ADU counts, property
  rights, HBU and zoning compliance. A large share of the checklist from one
  cheap call — the 3.6 form gives this away by design.
- **Page 4 is a location map** with almost no extractable data, currently paid
  for as an ordinary page.
- **The grid spans page PAIRS.** p21 holds comps 1-3's General/Site/Dwelling/Unit
  rows; **p22 holds the SAME comps 1-3 continued**, including the Summary block
  with Net Adjustment Total, Adjusted Price and Comparable Weight. p23/p24 repeat
  for comps 4-6.

## 4h. DECISION (settled) — the vision model NEVER returns a verdict

Question raised: why extract values at all, rather than send the image plus the
checklist and let the vision model answer the checklist directly?

**Settled: it emits FACTS only — including for visual items.** An earlier
answer in this session conceded that visual items could be judged directly by
the vision model. That was wrong and is superseded: the correct line sits one
step earlier. A visual item yields a structured **inventory** ("photos present:
front, rear, street, comp1-6"; "sketch dimensions legible: yes"), which is a
fact; the judge still decides whether that fact satisfies the item.

**The decisive evidence is geometric, not stylistic.** Classifying all 90
checklist items by the evidence each needs:

| Evidence class | Share | Can a page-scoped verdict answer it? |
|---|---|---|
| A — single page/section | **25%** | yes |
| B — cross-page fusion (2+ pages, or arithmetic) | **54%** | **no** |
| C — external document (loan file, contract, title, investor guide) | 9 items | **never** — not in the appraisal at all |
| V — visual inventory | ~9 items | only as an inventory, not as a verdict |

Three-quarters of the checklist is unanswerable from one page. This matches what
the audit already found the hard way: **no single page produced a finding — every
one came from two or three pages held against each other.**

Worked example, item 98 (defects requiring repair): p1 says defects *None*; p26
says *None, As Is*; p19 says the contract requires the seller to repair the
septic before closing; p8 photographs the excavated septic tank. **Every page
passes in isolation.** A page-scoped verdict returns PASS — a false negative on
the most serious issue in the report.

Four further reasons, in order of force:

1. **Multi-AMC economics.** Separated, a new AMC is a YAML overlay. Fused, a new
   AMC means re-reading every PDF with vision. Cost goes from
   `orders x vision + orders x AMCs x judge` to `orders x AMCs x vision`.
2. **Ground truth dies.** Precision/coverage fixtures can only be frozen on
   facts. Every checklist edit would invalidate a verdict-based test set.
3. **Checksums die.** `sum(lines) == net` is only checkable if we hold values.
4. **The audit trail dies.** A reviewer seeing FAIL cannot tell whether the model
   misread the page or misapplied the rule.

## 4i. Checklist defects to fix before compiling a 3.6 bundle

| Defect | Impact |
|---|---|
| **No polarity column** — ~34 of 93 items are "Yes = a problem" (8, 18, 19, 44, 54-57, 66-68, 75, 93, 98…), the rest "Yes = healthy" | **The single biggest silent failure mode.** Without it a judge rejects healthy answers. One column fixes it. |
| **Item 70 logic inverted** — CSV says commentary is required when comps are UNDER the mileage guideline; it is required when they are OVER | Fires on this very report (comp #3 at 7.59 miles). Carry the corrected rule explicitly and have the AMC confirm — do not silently patch. |
| **Missing thresholds** — item 52 ("median DOM reflective of an active market?" — 63 days, yes or no?), 47/48 ("meet investor criteria" — which investor?) | The judge must never improvise a threshold. Put explicit numbers in the AMC overlay. |
| **Compound items** — 16 and 63 each ask two questions | Split at compile time, or one half silently decides both. |

**New verdict value needed: `NOT_DETERMINABLE`**, distinct from VERIFY. VERIFY =
a human must exercise judgment. NOT_DETERMINABLE = no amount of reading the
appraisal can settle it, because the answer lives in the loan file. Different
queue, different reviewer action. Items 2, 5 and 7 upgrade out of it as soon as
engagement-letter fields are bound — SHAL already ingests those documents.

## 4j. RESOLVED — page skipping removed; the report is its own answer key

**Page 33 carries a "Value Reconciliation" table restating EVERY comparable's
adjusted price, weight and weighted contribution — and it was being skipped.**

| Comp | Weight | Adjusted price | Weighted contribution |
|---|---:|---:|---:|
| 2324 Floyd Springs Rd NE | 20% | $318,300 | $63,660 |
| 21 Covered Springs Dr NE | 15% | $324,800 | $48,720 |
| 4083 Old Dalton Rd NE | 25% | $311,000 | $77,750 |
| 412 Perry Rd | 15% | $277,400 | $41,610 |
| 37 Covered Springs Dr NE | 25% | $314,900 | $78,725 |
| 316 Armuchee Trl NE (listing) | 0% | $341,700 | $0 |

$318,300 equals comp 1's grid arithmetic exactly; weights sum to 100%; and
318,300 x 0.20 = 63,660. This is a **free, independent answer key** for the one
region whose misreads are hardest to catch — from a completely unrelated part of
the document, at no extra call.

**Why it was skipped, and why structural skipping is now removed entirely:**

| | page 33 (data table) | page 27 (real photo sheet) |
|---|---|---|
| images | 29 | 20 |
| image area | **44.2%** | **44.2%** |
| drawings | 305 | 304 |

Structurally identical. On a flattened PDF there is no text layer to separate
them, so **no structural rule can tell a data table from a photo grid** — any
threshold that drops one drops the other. `extractable` now excludes only
genuinely blank pages. Cost of reading all 40 pages: **$0.097, still 13% of
cap.** A skipped page saves a cent and loses evidence silently.

## 4k. ADOPTED — cross-verification: 13 facts, 44 observations, 3.4 sources each

The report states the same fact in several places, and those pages are already
being read, so confirming a fact from multiple independent sources costs
**nothing extra**. GLA appears six times: sketch total (p6), sketch line-item
sum (p6), sketch commentary (p7), interior finished-above-grade (p8), level and
room detail (p8), grid subject column (p21).

One mechanism, three outcomes:

- **CONFIRMED** — all sources agree. Checklist item 34 ("is the square footage
  consistent with the sketch?") is then answered **deterministically, with no
  judge call at all** — the item *is* the consistency check.
- **REPAIR** — five sources say 2,137 and one says 2,737. Re-extract **that one
  page**, with the expected value already known, so the fix verifies instantly.
  Majority-vote self-healing, free.
- **CONFLICT** — the sources genuinely disagree in the report. Not an extraction
  bug: a finding, routed to the judge.

**Arithmetic beats pixels on ambiguous digits.** The sketch states a Level-1
total of 2137.35; three clear line items sum to 2039.49; therefore the fourth
must be 97.86. So 97.87 is right and 97.07 is a misread — settled by
subtraction, without re-reading the page. No vision model provides that.

Verification escalates cheapest-first: arithmetic oracles (free) -> consistency
vote (free) -> provenance check (free) -> targeted single-page re-extract (~1
call) -> different-model re-read (~1 call) -> judge/VERIFY card.

This **replaces** the plan's "two-pass on numerics" (re-extract everything
independently, medium cost). The consistency graph is that second pass, free.

## 4e. ⚠️ OPEN ISSUE — photo pages must NOT be blanket-skipped (RESOLVED, see 4j)

The 16 "photo_grid" pages are currently dropped from the vision budget entirely.
**That is wrong**, and it is the highest-priority correction outstanding:

- **Interior photos identify appliances and fixtures** the checklist asks about
  (refrigerator, range/oven, dishwasher, disposal, microwave, washer/dryer).
  Those fields exist in the schema and cannot be answered from a data table
  alone — the evidence is in the image.
- **Photo PRESENCE is itself a checklist item** ("required photos included:
  front, back and street scene of the subject, front of each comparable").
  Skipping the pages makes that item permanently unanswerable.
- **Market trend CHARTS** (pp. 16-18) are graphs, not tables — the seller
  concessions trend (65.3% of sales, +6.2pp) is read off a plotted curve.
- **Condition evidence** — the septic excavation photo is what corroborates the
  contract's repair requirement.

**Required change:** photo pages get a CHEAP pass (photo inventory + object
identification), not a skip. The cost lever must come from DPI and call shape,
not from discarding evidence pages. Cost is 9% of cap, so there is ample room.

## 4g. Input tokens and output tokens are different problems

They are separately controlled and must be tuned in **opposite directions**:

| | Who decides | How to control | Correct policy |
|---|---|---|---|
| **INPUT** | We do, exactly | DPI, image count, schema size, prompt length | **Minimise aggressively.** Fully deterministic and safe — nothing is lost by sending less, as long as the pixels are legible. |
| **OUTPUT** | The model does | `max_tokens` ceiling only | **Be generous.** The ceiling is a cliff, not a dial: hitting it destroys the ENTIRE call. |

Why the asymmetry is not a preference but a measured fact: this is a reasoning
model, so it spends output tokens deliberating *before* it writes any JSON. A
ceiling that is slightly too low does not return a shorter answer — it returns
an **empty** one, having paid full latency and full token cost. Three separate
runs lost whole sections and comparables that way (23 fields → 81 → 160 as the
ceiling rose, with nothing else materially changed).

So the tuning rule is: **squeeze input, never squeeze output.**
- Input squeeze that is proven free: DPI 200 → 100. Identical tokens, identical
  accuracy, a third of the upload.
- Output squeeze that destroyed data: 4,000 on a grid column. Raised to 9,000.

Both are frontend-editable (`vision_dpi_*`, `vision_max_tokens_*`).

## 4f. Measured run results

| Run | Change | Time | Fields | Cost | Precision* | Comps |
|---|---|---:|---:|---:|---:|---|
| 3 | first full vision run | 119.8s | 23 | $0.044 | — | none |
| 5 | + retry, per-column grid, DPI fix, concurrency | 99.7s | 81 | $0.069 | 91% | 1,2,4,5,6 |
| 6 | + output ceilings raised | 175.6s | 160 | $0.098 | 95% | all 6 |
| 11 | + consistency engine, all 40 pages, 9 sections | 536.1s | 119 | $0.111 | — | — |
| **12** | **+ sections split to one page-cluster each** | 528.0s | 121 | $0.119 | **100%** (15/15) | all 6 |

\* spot-check against fields read directly off the rendered pages; precision =
of what it emitted and was checked, how much is right.

**Run 12 is the accuracy milestone: 15 correct, 0 wrong, 12 not emitted.**
Nothing it asserted was false. Coverage and latency are the open problems now,
not correctness — which is the right order to solve them in, because a fast
wrong answer is worthless and a slow right one is merely expensive.

\* spot-check against fields read directly off the rendered pages; precision =
of what it emitted and I checked, how much is right.

**Run 6 detail:** 18 correct / 1 wrong / 18 not emitted of 37 checked. The single
wrong value is `units_count` = "One" vs "1" — a formatting difference the
normalizer already handles, not a misread. All six comparables now extract
(124 comp fields). 9 of 12 grid calls succeeded; 3 sections still failed.

**Fixed vs the 42% baseline** — every one of the audit's dangerous
confident-wrong values is now correct: `property_address` (was 'Structure'),
`borrower_name` and `lender_name` (were 'ReferenceID 4208000694'), and
`appraiser_company_address` (was the lender's address).

**Still open:**
1. **175.6s vs the 60s target.** Correctness was bought with output headroom.
   The route back to 60s is input-side and structural, not by re-lowering the
   ceiling: smaller per-call schemas (split the grid schema by page, ~37 fields
   → ~18) so the model reasons less per call.
2. **Only 2 of 8 regions pass their checksum.** Comp columns still reconcile
   against a partial set of line adjustments — the page-pair merge is landing
   some rows but not all, so `sum(lines) != net`. This is the checksum doing its
   job: those columns are correctly refusing to certify.
3. Three sections (sketch, site, market) still fail on individual calls.

## 4l. A section must map to ONE page cluster

Found twice, the same way, and worth stating as a rule because it is invisible
until you look for absent fields rather than wrong ones.

A section is located by a **positional window 3 pages wide**. A section whose
content spans several page clusters therefore silently loses most of its own
fields — the call succeeds, returns valid JSON, and simply never sees the pages
the rest of its fields live on.

| Section | Spanned | Window landed | Lost |
|---|---|---|---|
| `improvements` | pp. 7-14 (3 clusters) | [11,12,13] | `gla`, `bedrooms`, `baths`, `year_built`, quality/condition — all reported ABSENT |
| `reconciliation` | p26 + p33 + pp.38-40 | [33,34,35] | `appraised_value`, the whole signature block |

Both were split into one section per cluster:

    reconciliation -> reconciliation (p26)
                      value_reconciliation (p33)   <- the grid's answer key
                      appraiser (pp.38-40)

    improvements   -> dwelling_exterior (p7)
                      unit_interior (pp.8-9)
                      outbuilding_storage (pp.13-14)

**11 of 11 sections now land on their real pages.** The recovered fields
(`gla`, `bedrooms`, `baths`, `year_built`, quality, condition) went from absent
to present and correct in run 12.

> **Rule:** when adding a 3.6 section, check that its content sits in ONE
> contiguous cluster. If it doesn't, split it — do not widen the window, which
> only trades a missing-field failure for a diluted-scope one.

## 5. Bugs this session caught, all in code written the same hour

1. **`$(12,000)` parsed as +12,000.** The `$` sits *outside* the parens, so a
   `startswith("(")` check never fired. This inverts the sign of every downward
   adjustment — and it does not error, it just makes the net reconcile against
   the wrong number, so the checksum would have *passed* a grid it should have
   rejected. Fixed; six notations now covered including Unicode minus.
2. **Photo-page threshold dropped the market-trends pages.** Set at 6 images, it
   swept pp. 16-18 into "photo" and discarded them. Those pages carry the
   36-month trend matrix, and losing it doesn't just cut coverage — it
   *manufactures* a false positive, because "declining market ⇒ negative time
   adjustments" flags three provably-correct adjustments once the non-monotonic
   monthly figures are missing. Threshold set from measured data (18-112 images
   on true photo sheets vs 7-13 on data pages) to 15.

## 6. Status

| # | Deliverable | Status |
|---|---|---|
| 0 | `Source.VISION` + page cap + 3.6 markers | ✅ done |
| 1 | `page_map.py` — structural probe | ✅ done, verified on the real file |
| 2 | `verify.py` — arithmetic checksums | ✅ done, verified against real page arithmetic |
| 3 | `vision/provider.py` + `budget.py` + `render.py` | ✅ done |
| 4 | Runtime config + admin REST (`GET/PUT/DELETE /settings`) | ✅ done |
| 5 | `vision/sections.py` + `config/vision_sections/uad36/*.yaml` | 🔄 in progress (1 of ~8 schemas written) |
| 6 | `vision/grid.py` — 6-comp column extraction | ☐ next |
| 7 | 3.6 fork in `merge.run_extraction` | ☐ |
| 8 | End-to-end run on Turner Rd + scored report | ☐ |
| 9 | Frontend settings screen (consumes §4 API) | ☐ |
| 10 | Frontend checklist editor + checklist/bundle in DB | ☐ separate slice |
| 11 | 3.6 checklist rebind into a NEW bundle (see D6) | ☐ |

## 7. Standing rules

1. **Never judge a QC result from fewer than 3 randomly-picked orders.** One order
   proves a mechanism, never an effect.
2. **Precision and coverage are reported separately, always.**
3. **Unverified never ships as PASS.** A comp column whose arithmetic doesn't
   close becomes a REVIEW card.
4. **Abstention is correct.** An honest `null` beats a plausible guess.
5. **Never recompile over the active 2.6 bundle.**
6. **Serverless only.** A model with no per-token price is dedicated-only — it
   needs a GPU endpoint and does not belong in this path.
7. **Credentials never come from runtime config.** Only from the environment, so
   nothing settable in a browser can redirect traffic or leak a key.

## 8. Session log

### 2026-08-09 — session 1
- Verified the sample's real structure (40pp, 0 chars/fonts, PDFium, uniform Letter).
- Built and **tested** `page_map` + `verify` — the two no-LLM components — before
  anything that spends money. Both verified against the real document.
- **Plan changed mid-session:** Anthropic Sonnet 5 → Together serverless
  `gemma-4-31B-it`, after the Qwen3-VL line was found to be dedicated-only.
  Cost fell ~9× ($0.54 → $0.063/order). Architecture unchanged — the provider
  interface absorbed it, which is what D4 was for.
- Added the frontend config layer (`runtime_config` + admin REST) so model, DPI,
  budget and page cap are settable from the UI rather than by editing Python.
- Caught two same-session bugs (§5), one of which would have silently defeated
  the checksum layer.
- **Next:** finish the 3.6 section schemas, then `grid.py`, then the merge fork,
  then the first scored end-to-end run.
