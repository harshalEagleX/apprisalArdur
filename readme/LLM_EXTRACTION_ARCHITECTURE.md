# Ardur — LLM Usage & Extraction Architecture (SCA / Subject / Neighborhood / Contract)

**Purpose:** exactly how each section is extracted, **where the LLM is used, how, and why**, what data the LLM receives (**image vs text — with real captured examples**), and **what breaks if the LLM is removed.**

**Method:** every claim below is grounded in code (`app/qc/transaction.py`, `app/extraction/*`) and in **real prompts captured from a live run** (LLM stubbed, zero Groq tokens) via `scripts/loadtest/dump_llm_prompts.py` on `28203 Fantail Dr` (appraisal + contract + engagement). The 12 captured calls are in `/tmp/apprisal-loadtest/prompts/`.

---

## 0. Direct answers to your questions

| Question | Answer |
|---|---|
| Are SCA / Subject / Neighborhood / Contract extraction **implemented (done)?** | **Yes** — all four run today; the live run produced 186 rule results with these sections populated. |
| Do they **send PNG images** to the LLM? | **No** for SCA grid / Subject / Neighborhood / Contract — those are **TEXT**. **Yes** only for the **comparable-photo** check (SCA-27/16V) and the sketch — those send a **PNG image (~1.5 MB)** to the *vision* model. |
| Do they **OCR first, then send to the LLM?** | **Yes.** The PDF is read into **spatially-reconstructed text** (PyMuPDF/pdfplumber row-clustered, or Tesseract/Paddle for scans), and **that text** is what the LLM receives — never the raw PDF. |
| **Where** is the LLM actually used? | As a **repair/confirm overlay** on the SCA currency grid, and as a **gap-fill** for Subject/Neighborhood/Contract fields the deterministic layers missed. Plus **evaluative yes/no judgments** for a few commentary rules. |
| **How deeply** is it used? | **Shallow on purpose.** Deterministic extraction runs first for everything; the LLM only refines the weak SCA currency columns and fills named gaps. It is **not** in the path for most fields. |
| **Without the LLM, how much is affected?** | Subject/Neighborhood/Contract: **mostly fine** (deterministic-first; only gap-fills lost → a few more VERIFYs). **SCA currency grid (sale price / net adj / adjusted / GLA): materially degraded** — this is the known-weak deterministic spot the LLM repairs. |

**One-line architecture:** *Deterministic-first extraction (OCR → spatial text → regex/positional parsers), with the LLM layered on top only to (a) repair the compact SCA currency grid and (b) gap-fill named missing fields — on TEXT, not images. Images go only to the separate vision comp-photo check.*

This is actually close to the HomeVision pattern you described — the gap is that Ardur's *deterministic SCA currency reader is weak*, so the LLM is leaned on there, and the SCA LLM currently runs whenever available (not only on deterministic failure), which inflates call count.

---

## 1. The pipeline flow (what runs, in order)

```
PDF
 └─► Layer 0–5 extraction (app/extraction/layers/orchestrator.py) — ALL DETERMINISTIC
        • PyMuPDF embedded text / Tesseract / PaddleOCR (scanned)  → page text
        • pdfplumber row-clustered "spatial text"                  → labeled lines
        • Camelot lattice + pdfplumber bands                       → table cells
 └─► Overlays (app/qc/transaction.py) applied in sequence onto the ExtractionResultSet:
        _overlay_comp_grid     ── DETERMINISTIC SCA grid (comp_grid + Camelot)         [no LLM]
        _overlay_sca_llm       ── LLM REPAIR of SCA currency columns (TEXT)            [LLM ✓]
        _overlay_subject/...   ── form_llm_extractor GAP-FILL of missing fields (TEXT) [LLM ✓ only for gaps]
        _overlay_comp_photos   ── VISION comp-photo condition (PNG IMAGE)              [VISION ✓ if enabled]
        _overlay_contract      ── deterministic contract parse + LLM gap-fill (TEXT)   [LLM ✓ only for gaps]
 └─► Rule engine (app/qc/rules/*) runs against the EXTRACTED STRUCTURE  ── mostly pure Python
        • a handful of commentary rules call assess_text() (TEXT yes/no judgment)      [LLM ✓ evaluative]
 └─► QCReport → PythonQCResponse → Java
```

**Key principle (P-3/P-14a):** the rule engine reads *structured extracted fields*, not the LLM. The LLM lives in the **extraction** layer (repair/gap-fill) and in a few **evaluative** commentary judgments — never as the decider of a rule's pass/fail.

---

## 2. The 12 LLM calls for one real appraisal (captured, zero quota)

| # | Type | What it is | Data sent | Tokens (approx) | reasoning / max_tokens |
|---|---|---|---|---|---|
| 1–2 | TEXT | **SCA grid extraction** (per grid page) | spatial grid TEXT | 681 / 560 | medium / 4096 |
| 3–4 | TEXT | **Form gap-fill** (page-1 subject/contract, neighborhood) | spatial page TEXT | 2232 / 2373 | low / 2048 |
| 5–6 | TEXT | **Form gap-fill** (reconciliation, cost) | spatial page TEXT | 1581 / 1545 | low / 2048 |
| 7–8 | TEXT | **Form gap-fill** (signature, USPAP) | spatial page TEXT | 1531 / 1301 | low / 2048 |
| 9–10 | **VISION** | **Comparable-photo condition** (SCA-27) | **PNG IMAGE ~1.5 MB** + prompt | image | — |
| 11 | TEXT | **Contract gap-fill** (concessions) | contract TEXT excerpt | 2823 | low / 1024 |
| 12 | TEXT | **Commentary judgment** (assess_text) | commentary TEXT | 188 | low / 800 |

So per doc: **10 TEXT calls + 2 VISION calls.** The TEXT calls dominate token usage; only 2 calls send an image, and those are the comp-photo check, *not* the four sections you asked about.

---

## 3. SCA (Sales Comparison Approach) grid — DEEP DIVE

### How it's extracted
1. **Deterministic first** (`_overlay_comp_grid`, transaction.py:124):
   - `comp_grid_extractor.extract_comp_grid` — pdfplumber row-clustered cells.
   - `sca_grid_matrix.extract_sca_grid` — **Camelot lattice** for right-aligned currency columns.
   - Per-field validators reject garbled cells (e.g. `condition_rating` must match `C[1-6]`).
   - Descriptive fields (address, proximity, date, condition, quality, GLA, location) → **deterministic, method `comp_grid`/`sca_lattice`, confidence 0.88–0.92.**
2. **LLM repair overlay** (`_overlay_sca_llm`, transaction.py:197) — runs `sca_llm_extractor.extract_sca_grid_llm(pdf)`:
   - Reads the **grid page TEXT only — no OCR re-run, no image** (per the docstring).
   - Validates `adjusted == sale_price + net_adjustment`; **only overwrites the comps it confidently reads**, so a correct deterministic value is simply confirmed.
   - Targets the **currency columns** (`sale_price`, `net_adjustment`, `adjusted_sale_price`, `gross_adj_pct`, `gla`) — the "known-weak spot" where the deterministic readers leak cost-approach/opinion-of-value into the adjusted row.

### What the LLM receives — REAL example (call 1)
**System:** `You read the Sales Comparison Approach grid of a URAR / Form 1004 residential appraisal report. Output ONLY one valid JSON object and nothing else.`
**User (real captured TEXT, the spatially-reconstructed grid):**
```
COLUMN STRUCTURE (critical): FEATURE-label | SUBJECT | COMPARABLE SALE A | B | C. IGNORE the SUBJECT column…
Return JSON: {"comps":[{"comp":1,"sale_price":<number>,"net_adjustment":<signed>,"gross_adj_pct":<number>,"gla":<number>}, …]}

GRID PAGE TEXT:
There are 38 comparable sales in the subject neighborhood … ranging in sale price from $ 320,000 to $ 540,000 .
FEATURE  SUBJECT  COMPARABLE SALE # 1  COMPARABLE SALE # 2  COMPARABLE SALE # 3
Sale Price  $ 380,000  $ 360,000  $ 370,000  $ 380,000
Gross Living Area  2,301 sq.ft.  2,369 sq.ft. -3,400  2,308 sq.ft. -350  2,284 sq.ft. +850
Net Adjustment (Total)  + - $ 20,360  + - $ 7,015  + - $ 2,175
```
→ **It is TEXT** — row-clustered OCR of the grid. Note how compact/garbled it is ("`+ - $ 20,360`", GLA and adjustment glued on one line). **This is exactly why deterministic column-alignment fails here and the LLM is used.**

### Where the LLM is used / how deeply
Only the **currency columns**, and only as **confirm-or-repair**. Everything else in the grid is deterministic.

### Without the LLM
- Descriptive grid fields: **unaffected** (deterministic).
- **Currency columns degrade**: the adjusted-sale-price row frequently mis-aligns (cost-approach value leaks in). SCA rules that depend on net/gross adjustment %, value support, and adjusted-price sanity become **unreliable → more false flags / misses.** This is the one section where removing the LLM has real accuracy cost — which is why CLAUDE.md **P-14a** marks it load-bearing.

---

## 4. SUBJECT section — DEEP DIVE

### How it's extracted
- **Deterministic first**: the layered extractors read page-1 labeled fields (Property Address, Borrower, Owner of Public Record, APN, Tax Year, R.E. Taxes, Legal Description, etc.) by label + spatial position.
- **LLM gap-fill** (`form_llm_extractor.extract_gap_fields_llm`, "subject" group): fires **only for fields the deterministic layers left empty** ("skips populated fields"). Reads **page-1 spatial TEXT**, returns verbatim values, and **every value is verbatim-validated against the page** before acceptance (`_validate`/`_field_sane`).

### What the LLM receives — REAL example (page-1 gap-fill)
```
Below is the spatially-reconstructed text of page 1 (SUBJECT and CONTRACT sections)… Extract ONLY these fields:
- "sale_type": …   - "financial_assistance_amount": …   - "financial_assistance_description": …
Rules: Copy VERBATIM … OMIT any field not present. Never guess.

PAGE TEXT:
Property Address 28203 Fantail Dr City Katy State TX Zip Code 77494
Borrower Anton Deineko  Owner of Public Record Lance & Holly Sheffield  County Fort Bend
Legal Description  Firethorne, Section 4, Block 1, Lot 17
Assessor's Parcel # 3105-04-001-0170-914  Tax Year 2025  R.E. Taxes $ 8,555
```
→ **TEXT** (page-1 spatial OCR). Image is never sent.

### Without the LLM
**Mostly fine.** Cleanly-labeled subject fields are deterministic. Only the *gap-fills* (fields with unusual labels/layouts the regex missed) are lost → those land on extraction-gap **VERIFY** instead of auto-filled. No silent wrong values (verbatim validation).

---

## 5. NEIGHBORHOOD section — DEEP DIVE

Same pattern as Subject (it's another `form_llm_extractor` group). Deterministic-first for the labeled neighborhood characteristics (one-unit housing %, price/age ranges, present land use, boundaries); **LLM gap-fills** the narrative-ish fields (`neighborhood_boundaries`, `neighborhood_description`, `market_conditions_commentary`) that deterministic layers read confidently-wrong or miss.

- **Data:** TEXT — the spatial text of the neighborhood page (same page-1/2 region). No image.
- **`_field_sane` guard:** rejects a land-use `%` label mis-returned as the boundaries text — so even the gap-fill can't inject a wrong neighborhood value.
- **Without LLM:** labeled ranges fine (deterministic); narrative gap-fills lost → those go VERIFY. Modest impact.

---

## 6. CONTRACT — DEEP DIVE

### How it's extracted
- **Deterministic first** (`_overlay_contract`, transaction.py:474): `contract_extractor.extract_contract_fields` — Tesseract OCR for scanned contracts, parses price/date/concessions. **Only sets a field when confidently found** — an unreadable contract leaves C-2/C-4 at **VERIFY rather than a false mismatch.**
- **LLM gap-fill** (`contract_extractor`, call 11): fills specific missing fields (e.g. `concessions_amount`) from the contract TEXT.

### What the LLM receives — REAL example (call 11)
```
System: You read residential real-estate purchase contracts. Output ONLY one valid JSON object.
User: Extract ONLY these fields … - "concessions_amount": total seller-paid concessions (digits only); omit if none
CONTRACT TEXT (relevant excerpts):
… ONE TO FOUR FAMILY RESIDENTIAL CONTRACT (RESALE) …
1. PARTIES: … Lance Sheffield, Holly Sheffield (Seller) and Anton Deineko, Viktoriia Domanska (Buyer).
2. PROPERTY: … Lot 17 Block 1; FIRETHORNE SEC 4 … 28203 Fantail Dr 77494 …
```
→ **TEXT** (OCR excerpts of the purchase contract). No image.

### Without the LLM
Price/date/parties are deterministic; only the harder gap-fills (e.g. concessions buried in prose) are lost → those rules go VERIFY. Low impact.

---

## 7. The VISION path (the ONLY place images are sent)

`_overlay_comp_photos` (transaction.py:452) → `comp_photo_extractor.extract_comp_photo_signals` renders the comparable-photo addendum **page to a PNG** and sends it to the **vision** model (`vision_chat_json`) for SCA-27/16V.

### What the LLM receives — REAL example (call 9)
- **type = VISION(IMAGE), image_bytes ≈ 1,548,757 (~1.5 MB PNG)**, prompt 1,953 chars:
```
This image is a page from a mortgage appraisal report's COMPARABLE SALES PHOTO addendum.
Assess the PHYSICAL CONDITION using the Fannie Mae UAD scale. Respond ONLY as JSON:
  is_building: bool   mls_watermark: bool   distress: bool   condition: C1..C6 | unknown
```
→ **This is the only image-based call.** Gated by vision availability (`VISION_ENABLED` / Gemini or Groq-vision key). When vision is unavailable it **degrades to page-count-only and the photo rules go VERIFY** (P-6) — never a hard failure. (In the captured run, Gemini returned 403 and it fell back to Groq vision.)

---

## 8. Evaluative judgments (assess_text) — small TEXT yes/no

A few commentary rules ask the LLM a **yes/no question** about a narrative block, *after* a deterministic keyword check fails first. Real example (call 12):
```
System: Answer with ONLY a JSON object {"answer": true|false}.
User: Does this sales-comparison commentary justify the CONSTRUCTION QUALITY of the comparables …?
TEXT: Most of the emphasis was placed upon the Sales Comparison Approach …
```
These are **evaluative, not extraction** (the legitimate LLM use per CLAUDE.md), gated behind a regex short-circuit, and **never change a rule's deterministic pass/fail** — they only resolve a borderline narrative to PASS vs VERIFY.

---

## 9. Edge cases (every one observed or coded)

| Edge | Behavior |
|---|---|
| Deterministic SCA reads currency correctly | LLM **confirms** (same value → no change); no harm. |
| Deterministic SCA leaks adjusted price | LLM **repairs** (validates adjusted = sale + net) → correct value wins. |
| LLM returns a value not on the page | **Discarded** — `_validate` requires the value to literally appear on the page. |
| LLM returns a cross-cell mis-map (e.g. land-use % as boundaries) | **Rejected** by `_field_sane`. |
| Field already filled deterministically | Gap-fill **skips it** (no LLM call for it). |
| LLM unavailable / disabled | Overlays **no-op**; deterministic results stand; gaps → VERIFY (P-6). |
| Vision unavailable | Comp-photo rules → **VERIFY**, page-count only. |
| Contract unreadable | C-2/C-4 → **VERIFY**, never a false mismatch. |
| Scanned (image-only) PDF | PaddleOCR/Tesseract produces the text the LLM then reads — still TEXT, not image. |

---

## 10. Bottom line for the optimization question

- **SCA / Subject / Neighborhood / Contract all receive TEXT** (spatially-reconstructed OCR), never images. Only the **comp-photo** check sends a PNG.
- The LLM is **shallow and gated** — deterministic-first everywhere; LLM repairs the SCA currency grid and gap-fills named misses.
- **Removing the LLM hurts mainly the SCA currency grid** (the compact, right-aligned columns deterministic readers misalign). Subject/Neighborhood/Contract survive with more VERIFYs.
- **The HomeVision-style fix** = strengthen the deterministic **SCA currency reader** (positional/Camelot column mapping) so the LLM is needed only as a true fallback. That is the change that would cut tokens/calls *without* losing accuracy — and it's exactly the spatial-bounding-box direction already in flight. Until then, the SCA-LLM repair is load-bearing (CLAUDE.md P-14a).
