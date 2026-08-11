# UAD 3.6 Vision Extraction — Problem Log & Trial History

**Purpose:** every problem found, what caused it, what was tried, and what the
result was. Written so someone who was not in the room can see the shape of the
thing and push back on specifics.

**Status at time of writing:** extraction is *accurate* (100% precision on the
last clean spot-check — nothing it asserted was false) but *slow* (327–555s
against a 60s target) and the comparable-grid calls are *unreliable* (2 of 6 to
8 of 12 succeeding depending on configuration).

---

## Part 1 — The problems, in the order they were discovered

### P1. The document has no text at all
The sample PDF reports **0 characters and 0 fonts across all 40 pages**. It was
produced by PDFium — someone printed the report from a browser/Outlook preview,
which flattened every glyph into vector outlines.

**Why it mattered more than it sounds:** every text-based extractor
(`pdf_digital`, `grid`, `checkbox`, `sweep`) returns zero **without raising an
error**. The pipeline looked healthy and produced confidently wrong values. This
is the root cause of the whole project.

**Engineered:** `page_map.classify_document()` returns `digital | flattened |
scanned` from character, font and drawing counts, so "this file has no text" is
a first-class routing decision instead of a silent zero.

### P2. The 8-page cap made the entire valuation invisible
`pdf_digital` and `pdf_scanned` had a hardcoded `max_pages: int = 8`. Correct for
a 1004; catastrophic for a 40-page URAR where market trends, listing history, the
6-comparable grid, reconciliation and certifications **all sit past page 8**.

**Engineered:** made it config (`EXTRACT_MAX_PAGES`, default 60).

### P3. `$(12,000)` parsed as **positive** 12,000
Accounting notation puts the currency symbol outside the parentheses, so a
`startswith("(")` test never fires. This silently inverts the sign of every
downward adjustment.

**Why it was the most dangerous bug in the session:** it does not error. It makes
the net adjustment reconcile against the wrong number, so the checksum — the one
mechanism that makes an imperfect model trustworthy — would have *passed* grids
it should have rejected.

**Engineered:** `verify.to_number()` now handles `$(12,000)`, `(12,000)`,
`($12,000)`, `-$1,700`, `1,700-` and Unicode minus. Verified against all six.

### P4. The photo-page filter was deleting the market-trend pages
An image-count threshold of 6 swept pages 16–18 into "photo sheet" and dropped
them. Those pages carry the 36-month trend matrix.

**Why that is worse than lost coverage:** without the matrix, a naive reading of
"declining market → time adjustments must be negative" flags three *provably
correct* adjustments. Losing the page does not reduce accuracy, it **manufactures
a false positive**.

**Engineered:** threshold set from measured data (true photo sheets carry 18–112
images; data pages with thumbnails carry 7–13). Later removed entirely — see P14.

### P5. `gemma-4-31B-it` rejects strict `json_schema`
Returns HTTP 400. Discovered on the first live call.

**Engineered:** automatic fallback to `json_object` with the schema restated in
the prompt, plus markdown-code-fence stripping on the response. This path is
**load-bearing, not defensive** — without it every call fails.

### P6. The model is a REASONING model, and that changes everything
`gemma-4-31B-it` writes into a `reasoning` field before it writes `content`. Two
consequences that took most of the session to fully understand:

**(a) Truncation is total, not partial.** If it exhausts `max_tokens` mid-
reasoning, it returns an **empty** `content` with HTTP 200. Full latency paid,
full tokens billed, every field in that call gone, and nothing in the response
says so. This single mode drove field counts of 23 → 81 → 160 as the output
ceiling was raised, with nothing else materially changed.

**(b) Output volume, not input, sets the wall clock.** Output is generated
serially. Reasoning costs roughly **180 output tokens per field requested** on
top of a ~2,000-token base, and it is paid *per call*.

**Engineered:** ceilings sized from field count; explicit error text naming
reasoning exhaustion; and `resilient.transcribe_complete()` — retry with more
room, then **split the field set and recurse** rather than drop fields.

### P7. A long system prompt caused a 105s average latency and 100% failure
The first prompt was eight numbered paragraphs. On a reasoning model that is
actively harmful: it deliberated about the rules until it exhausted the budget
and returned nothing. The same model with a short prompt read the subject address
correctly in **3.3 seconds**.

**Engineered:** prompt compressed to six rules. Prompt length is not free — it is
paid in reasoning tokens on every call.

### P8. DPI does not affect token cost at all (a 24× error in the plan)
The architecture document inherited a tile formula from Anthropic-based planning
(3,202–6,404 tokens/page, and a "132-DPI cliff" below which the grid supposedly
loses detail).

**Measured against the live endpoint on the grid page itself:** the image costs
**269 tokens at 130, 150 and 200 DPI — identical.** A separate sweep at
72/100/130/150/200 DPI returned 298 prompt tokens at every setting, with the
address read correctly every time.

So DPI is not a cost lever; Together downscales server-side before billing. It
*is* a **byte** lever: 200 DPI is 322 KB/page vs 91 KB at 72 DPI, and those
oversized payloads caused connection failures at high concurrency.

**Engineered:** defaults dropped to 100 DPI (sections) / 110 (grid); the doc's
§1.3 corrected in place.

### P9. No retry — 5 of 13 calls were lost to transient 5xx
Together returned 500/503 on five calls in one run. With no retry, each one
permanently lost an entire section or comparable: a third of the order gone to a
fault that clears in a second.

**Engineered:** retry on 408/409/429/5xx with jittered exponential backoff
(jittered because a synchronised retry from every worker recreates the overload).

### P10. Configured concurrency was being ignored
`sections.py` read a module constant `_MAX_CONCURRENCY = 6` instead of the
configured value (20). Eleven sections therefore ran as two waves instead of one,
doubling the section pass's wall clock — invisible from outside, because every
call still succeeded.

**Engineered:** uses the passed-in value.

### P11. The column-crop trade: clip vs bleed
Extracting one comparable at a time needs a crop. Both extremes fail:

- **4% padding** — sliced text that overflows its cell. A comparable's address
  read as *"4 Floyd Springs Rd NE, Buchee"* instead of *"2324 Floyd Springs Rd
  NE, Armuchee"*. Every number was still correct, so nothing downstream could
  flag it: a clipped address is a plausible address.
- **22% padding** — the neighbouring column became visible and the model read it
  too. Comparable 1 returned **14 line adjustments instead of 7**, and its
  checksum failed.

**Engineered:** 8%, biased toward the tighter side because the failures are not
equally bad — a clipped address is one wrong string a reviewer can see, a bled
column corrupts the adjustment set and takes the comparable's verification down
with it.

> **Superseded by P22. This was never a trade-off.** Both failures came from one
> wrong assumption about where the columns are, and measuring the page removes
> both at once. No padding value could have fixed it.

### P12. Whole-page grid reads truncate for a non-obvious reason
Sending the full page fixes clipping and bleed (headings visible, nothing cut).
But the model **reasons about everything visible** before reporting the one
column asked for, so the two dense grid pages exhausted the ceiling and returned
nothing — leaving each comparable with only the half from the sparser page, and
no checksum able to close.

### P13. A section must map to ONE page cluster
Sections are located by a positional window three pages wide. A section whose
content spans several clusters silently loses most of its fields — the call
succeeds, returns valid JSON, and never sees the other pages.

- `improvements` spanned pp. 7–14 → window landed [11,12,13] → **`gla`,
  `bedrooms`, `baths`, `year_built`, quality and condition all reported ABSENT**.
- `reconciliation` spanned p26 + p33 + pp.38–40 → window landed [33,34,35] →
  lost `appraised_value` and the entire signature block.

**Engineered:** split into one section per cluster (11 sections). All 11 now land
on their real pages, and the lost fields came back present and correct.

### P14. Page 33 — the grid's free answer key — was being thrown away
Page 33 carries a **Value Reconciliation** table restating every comparable's
adjusted price, weight and weighted contribution. Comp 1: $318,300 / 20% /
$63,660 — matching the grid arithmetic exactly, weights summing to 100%, and
318,300 × 0.20 = 63,660.

It was classified a photo sheet and skipped. And it **cannot be rescued by a
better threshold**:

| | p33 (data table) | p27 (real photo sheet) |
|---|---|---|
| images | 29 | 20 |
| image area | 44.2% | 44.2% |
| drawings | 305 | 304 |

Structurally identical. On a flattened PDF there is no text layer to separate
them, so any rule that drops one drops the other.

**Engineered:** structural page-skipping removed entirely — only genuinely blank
pages are excluded. Reading all 40 pages costs $0.097, 13% of the cap. The cost
lever is DPI and call shape, never discarding evidence.

### P15. The grid spans page PAIRS — merge, don't renumber
p21 carries comps 1–3's line adjustments; **p22 carries the same comps 1–3
continued**, including the Summary block with net adjustment total and adjusted
price. Treating the second sighting as a new comparable both invents phantom
comps and strands the net/adjusted figures away from the line items they must
reconcile against.

**Engineered:** merge by comparable number across the pair.

### P16. A regex label map put vehicle storage under "actual age"
Mapping printed row labels to canonical names by substring: `"age"` matched
`"stor**age**"`. The checksum cannot catch this — the sum is unchanged, only the
meaning is wrong.

**Engineered:** word-boundary matching (which then broke plurals — "Bedrooms" vs
needle "bedroom" — fixed with an optional plural suffix). Later replaced
entirely: the canonical vocabulary is now handed to the model **as a schema
enum**, so the model does the semantic matching and there is no pattern-matching
code to break on a vendor that prints "Garage/Carport".

### P17. Throughput is capped per API key
Measured: **~101 output tokens/sec per key**, 405 tok/s aggregate on 4 keys.
Therefore:

> **wall clock = total output tokens ÷ (keys × 100)**

This is the governing equation. Concurrency is already maxed — all 23 calls start
at t=0 and peak in-flight is 23/23 — so adding threads does nothing.

### P18. Consolidating grid calls cut tokens but broke reliability
Run 14 merged the 12 per-comparable-per-page calls into 6 per-comparable calls
carrying both pages. Total output fell 42% (128,840 → 74,708) as predicted, but
**only 2 of 6 grid calls succeeded**: two exhausted reasoning, one truncated
mid-JSON, one hit a 546s read timeout.

**The lesson:** there is a per-call size sweet spot. Too small and the fixed
reasoning tax dominates; too big and the call truncates or times out. Bigger
calls are cheaper in tokens and *worse* in reliability.

### P19. The "fixed reasoning tax" was overstated 8×, and the throughput equation is wrong
Two numbers in the earlier analysis were fitted from *aggregate* run totals and
are contradicted by the per-call rows in `_run14.json`.

**(a) There is no ~4,000-token fixed cost per call.** Fitting `out = C + F×N`
across the ten clean section calls gives **`out = 515 + 159 × N`** (R² = 0.68).
Three real calls returned under 1,500 output tokens in total — impossible if a
4,132-token floor existed:

| section | fields | output |
|---|---:|---:|
| `value_reconciliation` | 4 | 1,076 |
| `appraiser` | 13 | 1,146 |
| `outbuilding_storage` | 2 | 1,484 |

So reasoning is **not** prompt overhead paid per call — it scales with the page.
The grid confirms it from the other end: one comparable logged **26,760 chars of
reasoning** (~6,700 tokens). Reasoning tracks *page density*, which means it is
doing real work. Suppressing it, or starving the section schemas to save a
supposed 4,000 tokens/call, was the wrong lever and is abandoned.

**(b) `wall = total_output ÷ (keys × 100)` does not hold.** Measured on run 14:
74,708 tokens ÷ 546.5s = **137 tok/s aggregate across 4 keys**, not 405. Per-call
decode ran 25–61 tok/s. And every call starts at t=0, so the run ends when its
**slowest single call** ends — not when a shared bucket drains. The equation
predicts 185s; the run took 555s.

### P20. Every call uploaded its images twice
`gemma-4-31B-it` rejects strict `json_schema` (P5) on *every* call, but the
rejection was rediscovered per call — and the rejected probe carries the full
image payload. Measured on this document: **8.0 MB and 46 image uploads per
order where 4.0 MB and 23 would do.**

Those doubled payloads are the most plausible source of the connection resets and
read timeouts seen at 17-way concurrency.

**Engineered:** `_JSON_SCHEMA_OK` remembers the answer per model, so the probe is
paid once per process instead of once per call.

### P21. An unbounded retry policy, not tokens, set the run's wall clock
Run 14's longest item was `grid:comp6` at **546.5 seconds returning nothing** —
three consecutive 180s read timeouts with backoff, each one re-uploading ~1.5 MB
and starting a fresh generation.

**A read timeout is not a 5xx and must not be retried like one.** A 5xx means the
request was rejected and nothing is running. A read timeout means it was accepted
and the model *is* generating — so re-posting abandons work in progress, pays the
upload again, and usually ends the same way.

Worse, the timeout was incoherent with the ceiling it was guarding: a
9,000-token grid call needs ~360s at the measured 25 tok/s floor, so a 180s
timeout **guaranteed** failure on exactly the calls working hardest.

**Engineered:** at most 2 timeout attempts; a hard 300s wall-clock budget per
logical call covering all retries and backoff; per-attempt timeout derived from
the ceiling being requested; and a warning when a configured ceiling cannot be
generated within the timeout at all.

### P22. The grid crop was cutting the wrong rectangle — and it caused P11 entirely
`label_and_column_clips` assumed the grid spans the full page width with a 28%
label column. Measured off the page's own rules, it does not:

```
grid occupies x ∈ [0.153, 0.847]  —  five equal columns of 0.1385
  label   [0.153, 0.292]      comp 1  [0.431, 0.569]
  subject [0.292, 0.431]      comp 2  [0.569, 0.708]   comp 3 [0.708, 0.847]
```

So comparable 1's crop was taken at **[0.446, 0.654]** where the column actually
lives at **[0.431, 0.569]**. That single rectangle is wrong in both directions at
once: it **clips 1.5% off the left of comp 1's own cell** and **includes 62% of
comparable 2**.

Which is exactly P11's "unavoidable trade-off", and it was never a trade-off:

- Values in these cells are **right-aligned**, so overflowing text runs off the
  **left** edge — hence "24 Floyd Springs Rd NE" for "2324 Floyd Springs Rd NE".
  Widening the padding could not fix that without pulling in more of the
  neighbour, because the crop's left edge was inside the cell to begin with.
- The neighbour was in frame at *any* padding, because the right edge was 0.085
  past where the column ends.

**What it cost, on comparable 1 of the sample report.** The checksum failed with
`sum(lines) = 17,100` against a printed net of `$(1,700)`. Reading the page
directly:

| row | printed | extracted |
|---|---:|---:|
| contract date | $3,500 | $3,500 |
| **site size** | **$(23,800)** | **$0** |
| bathrooms | $9,000 | $9,000 |
| finished area above grade | $11,600 | $11,600 |
| **porch/patio** | **$5,000** | **missing** |
| vehicle storage | $(12,000) | $(12,000) |
| outbuilding | $5,000 | $5,000 |
| **sum** | **-1,700** ✓ | 17,100 ✗ |

The printed rows reconcile to the printed net exactly. Two reads were wrong, and
the 18,800 discrepancy is precisely `23,800 - 5,000`. Note the shape of the
worse one: the largest, most sign-critical adjustment on the page came back as
**$0** — a completely plausible value that nothing downstream could doubt. The
"13 line adjustments where 7 exist" note in the earlier verification message was
itself a misreading: 13 is correct, six of them are $0.

**Engineered:** three changes, all mechanism.

1. `detect_grid_columns()` recovers the boundaries from the page's own rules as
   the longest arithmetic progression among horizontal-rule endpoints (the
   columns are uniform; the value/adjustment sub-dividers are not). Predicted
   boundaries are then **snapped onto real drawn coordinates**, because an
   extrapolated step accumulates rounding drift and dropped comparable 3 off the
   end of the grid. Returns None on a page with no such structure, and the
   proportional estimate remains the fallback.
2. Padding drops from 8% to 2%: guessing needed slack, measuring does not.
3. `render_label_value_composite()` joins the label strip and the value strip
   into **one image** with a rule between them. Two separate images force the
   model to correlate by ordinal position — "row N here is row N there" — which
   is false on this form, where rows vary in height, band headers interrupt the
   sequence, and cells merge across rows. That correlation is the likeliest
   mechanism behind both errors above: `site_size` picked up a `$0` belonging to
   a different row, and one row was skipped entirely.

Verified visually on pages 21 and 22: the full address renders, no neighbouring
column is in frame, and `Site Size | 2.75 Acres | $(23,800)` reads straight
across on one line. Pinned by `tests/test_extraction/test_grid_column_geometry.py`
against a synthetic PDF, so the assumption cannot creep back.

### P23. `json_schema` stopped being rejected and started being SLOW — which was worse
P5 recorded that gemma-4-31B-it rejects strict `json_schema` with a 400, so the
`json_object` fallback was "load-bearing, not defensive". That is no longer true:
Together now **accepts** `json_schema` on this model.

A fast, loud failure quietly became a slow, silent success. Measured back-to-back
on the real 24-field `assignment` schema with the same page image:

| format | wall | output | result |
|---|---:|---:|---|
| `json_object` + schema in prompt | **39.8s** | 2,866 | 24/24 fields |
| `json_schema` (strict) | **107.7s** | 3,813 | 24/24 fields |

**2.7× the wall clock and 33% more output tokens for an identical answer** —
constrained decoding against a 12,472-character grammar is expensive.

This took **run 15 to 4 fields**. Every call spent its whole budget inside the
schema-constrained path and timed out; `falling back` was logged **zero** times,
which is the tell — the fallback that had fired on every call in run 14 never
fired again. A single uncontended probe call reproduced it, which is what ruled
out concurrency, payload size and the composite change.

**Engineered:** `json_object` + schema-in-prompt is now the DEFAULT and
`json_schema` is opt-in (`response_format`). The shape guarantee it buys is
already enforced when the response is parsed; latency is the binding constraint
and it loses. This also removes the capability probe entirely, so the doubled
upload of P20 is gone by construction rather than by caching.

**The transferable lesson:** a vendor fixing a limitation can be a regression. The
fallback path had been carrying the system for so long that the "unsupported"
branch was the tested one, and support arriving routed every call down a path
nobody had measured.

### P24. Concurrency past ~2 calls per key converts completions into timeouts
Run 16 ran 23 calls in flight across 4 keys. Per-call decode rate fell steadily
through the run:

```
first calls to finish   71-121 tok/s
last calls to finish     24- 27 tok/s
```

Aggregate throughput was flat, so the extra concurrency bought **nothing** — it
spread the same tokens more thinly and pushed the slowest calls past their read
timeout. And a timed-out call does not return less, it returns **nothing**:
`market` and `contract_history` each burned the full 300s call budget for zero
output, against real usage of 3,163 and 3,828 tokens.

The three knobs are not independent. The read timeout must cover the ceiling, the
ceiling must cover the call, and how long a call takes to spend its ceiling is set
by how many other calls are contending. Tuning any one alone just moves the
failure.

**Engineered:** concurrency 20 → 8 (~2 per key); grid ceiling 4,500 → 6,000
(eight of twelve grid calls had stopped at exactly 4,500, i.e. truncated); section
ceiling capped 16,000 → 6,500 (headroom a call cannot spend is not safety, it is a
longer way to fail).

### P25. Ten correctly-read values were being discarded after extraction
The plausibility gate suppressed 10 fields per run. Read against the page, they
split three ways — and only one third were actually bad reads.

**Two boolean vocabularies, and the stricter one silently won.** `plausibility`
carried a private `{yes, no, y, n, true, false, 1, 0}` while
`config/normalizer.yaml` already defined `boolean_false: [..., none, ...]`. The
3.6 form answers "Apparent Defects, Damages, Deficiencies" with the word
**"None"** — known to config, rejected by the gate. Fixed by making plausibility
defer to the normalizer's tables, and by *canonicalizing* rather than merely
accepting, so a rule receives `False` instead of a missing field.

**Form vocabulary the schema never listed.** 3.6 prints `Centralized` (schema
wants `Central Air`) and `Typically Motivated` in the grid's Transfer Terms row
(schema wants `Arms-Length`). Added to the enum synonym table.

**Genuine mis-reads — fixed at the source, never by widening the vocabulary.**
These were the gate working correctly, and accepting them would have laundered
extraction errors into trusted values:

| field | returned | why | fix |
|---|---|---|---|
| `dwelling_type` | `Ranch` | the form prints "Attachment Type" on p2, not on the dwelling pages; asked on the wrong page the model took "Dwelling Style" | moved the field to the `assignment` section (P13 again) |
| `stories` | `2-3 Ft.` | there is no story row; it took "Front Door Elevation" | describe now names the trap and requires null |
| `site_area_unit` | `40,511 Sq. Ft.` | number and unit share ONE printed cell, so both fields took the whole string | describe splits them explicitly |
| `special_assessments` | `No` | 1004 asks an AMOUNT, 3.6 asks Yes/No — a type mismatch, not a bad read | new `special_assessments_present` boolean field |

---

## Part 2 — Trial history

| Run | What changed | Time | Fields | Out tokens | Grid calls OK | Result |
|---|---|---:|---:|---:|---|---|
| 1–2 | first wiring | — | — | — | — | died on stdin/import bugs |
| 3 | first full vision run | 119.8s | 23 | — | 0/12 | 5 calls lost to 5xx, no retry |
| 4 | — | — | — | — | — | killed: `_pages_for_spec` signature mismatch |
| 5 | +retry, +DPI fix, per-column grid | 99.7s | 81 | — | — | **91% precision**, 5 of 6 comps |
| 6 | +output ceilings raised | 175.6s | 160 | — | — | **95% precision, all 6 comps** |
| 7 | row-list schema | 366.8s | 206 | — | 10/12 | crop bled: 14 line adjustments vs 7 |
| 8 | whole page, all comps | 248.7s | 92 | — | 2/4 | p21/p23 truncated at 9,000 |
| 9 | whole page, single comp | 175.5s | 83 | — | 7/12 | still truncating |
| 10 | 8% crops | 337.6s | 65 | — | 8/12 | crops back, still truncating |
| 11 | +consistency engine, all 40 pages | 536.1s | 119 | 104,527 | 8/12 | p33 table now read |
| 12 | +sections split to page clusters | 528.0s | 121 | 112,735 | 8/12 | **100% precision (15/15)** |
| 13 | +timing instrumentation | 327.4s | 99 | 111,819 | 7/12 | diagnosed the real bottleneck |
| 14 | 6 grid calls, never-fail sections | 555.0s | 111 | **74,708** | **2/6** | tokens −42%, reliability worse |
| 15 | bounded retries, measured crops, 12 grid calls | 313.9s | **4** | 1,110 | 0/12 | **collapse** — `json_schema` newly accepted and 2.7× slower (P23); every call timed out |
| 16 | `json_object` default (P23) | **310.0s** | **148** | 69,632 | 5/12 | 55.5% coverage, first region ever verified |
| 17 | concurrency 20 → 8 | 494.1s | 150 | 32,633 | 5/12 | **worse** — narrowing the pool serializes into waves (P24) |
| 18 | concurrency back to 20, grid ceiling 6,000, measured crops + composite | 602.8s | **353** | 80,251 | **12/12** | **THE GRID CLOSED — 5 of 6 comparables CERTIFIED, 7/8 regions verified, 0 failures** |

**Reading the table:** accuracy improved monotonically and is now excellent;
coverage set a record at run 16. Latency finally moved — 555s → 310s — once the
response format and the retry policy stopped wasting whole calls.

Run 15 is the instructive one. Every change in it was correct in isolation, and
the run still fell to 4 fields, because an unrelated vendor-side change turned the
fallback path into the primary path. **A run that regresses this hard is usually
not the change you just made** — the per-call evidence (`falling back` logged
zero times, a single uncontended probe reproducing it) found the cause in minutes
where reasoning from the diff would not have.

---

## Part 3 — What is engineered and holding

| Component | What it does | Verified how |
|---|---|---|
| `page_map.py` | flattened/digital/scanned classification; grid pages by long horizontal rules | Grid detection returns **exactly [21,22,23,24]** in 2.9s, zero API calls. Ranking by drawing count instead returns the certification pages — the h-rule signal inverts it correctly (200/114 vs 0/2). |
| `verify.py` | arithmetic checksums: `sum(lines)==net`, `sale+net==adjusted`, sketch, rooms | Comp 1's real page arithmetic **closes**; transposed digit, sign flip and dropped row all **caught**; 6 negative notations parse. |
| `consistency.py` | cross-source fact vote; CONFIRMED / REPAIR / CONFLICT; p33 grid answer key | GLA confirmed from 4 sources; injected misread **localises to page 8 only**; all 6 comps matched against p33, weights 100%, contributions correct; injected digit-swap on comp 3 caught and localised. |
| `resilient.py` | retry with more room, then split the field set — never drop a field | Wired; 1 retry, 0 splits, 0 unresolved fields in run 14. |
| `provider.py` | json_schema→json_object fallback, 5xx retry with jitter, 4-key round-robin, per-call timing | Live. |
| `runtime_config.py` + admin API | frontend-editable settings, allow-listed, validated | 15 keys, range/enum validation rejects bad writes. |
| Section specs | 11 sections, 145 fields, page-clustered | **11/11 land on their real pages.** |

---

## Part 4 — What is still broken, precisely

**1. Wall clock: 327–555s against a 60s target.**
Governed by the SLOWEST CALL, not by an aggregate token bucket (P19b). Run 14's
wall clock was one comparable's 546s retry loop; behind it sat two more grid
calls at ~349s each. The fixes in P20/P21 bound the retry damage, but the
underlying constraint stands: a 9,000-token call at the measured 25 tok/s
contended floor is ~360s on its own. **60s requires no call above ~1,500 output
tokens**, which no grid call currently approaches.

**2. ~~The grid is unreliable at every call size tried~~ — RESOLVED in run 18.**
12 of 12 grid calls succeeded and **five of six comparables now certify
arithmetically**:

```
comp_1  CERTIFIED  net -1,700 == sum of 7 line adjustments
comp_2  CERTIFIED  net 50,300  comp_3  CERTIFIED  net -9,000
comp_4  CERTIFIED  net -7,600  comp_5  CERTIFIED  net  8,900
comp_6  UNREAD     (net never read)
```

comp_1 closing at exactly −1,700 is the **end-to-end proof of P22**: the
`$(23,800)` site-size adjustment that every previous run misread as `$0` is now
read correctly, and the arithmetic confirms it independently rather than on my
say-so. What fixed it was the combination — measured column geometry, the
label/value composite, a 6,000-token ceiling, and full-width concurrency.

Residual: comp_6's net was never read, so it reconciles to UNREAD rather than
CONFLICT. The partial-credit reconciler names the retry.

**3. Comparable checksums are not closing.**
Because of (2), comps arrive with partial line-item sets, so `sum(lines) != net`.
The checksum is *working* — it is correctly refusing to certify — but it means
the arithmetic verification layer is not yet earning its keep. The p33
cross-check partially compensates.

**4. Coverage: ~111–160 fields of 283 schema fields.**
Not a correctness problem (precision is 100% on what it emits) but a
completeness one.

---

## Part 5 — Where I would most value your input

1. **How many Together API keys can you make available?** This is the single
   highest-leverage variable and it is outside my control. The equation is
   linear: 4 keys → ~280s floor; 8 keys → ~140s; 12 keys → ~93s. Nothing else I
   do reaches 60s without this.

2. **Is 60s a hard product requirement or a target?** If orders can be processed
   asynchronously (queued, results reviewed later), a 3-minute order at 100%
   precision may be strictly better than a 60s order that drops fields. The
   architecture supports either; the choice changes what I optimise.

3. **Is `gemma-4-31B-it` fixed?** RESOLVED as far as Qwen goes: Qwen3.5-9B
   (truncated) and Qwen3.7-Plus (HTTP 400) were trialled, rejected, and have now
   been **removed from the project entirely** — pricing table, tier defaults and
   docs — so they are not picked up again. Gemma is the model.

   Note the premise of this question was wrong anyway: see P19. There is no
   ~4,000-token fixed reasoning tax, so "swap to a non-reasoning VLM" was never
   the lever it looked like.

4. **Do you have a second and third 3.6 report?** Everything above is measured on
   one document. The consistency map, the page-cluster hints and the grid
   geometry are all drawn from it, and the standing rule in this project is never
   to judge a QC result from fewer than three orders.
