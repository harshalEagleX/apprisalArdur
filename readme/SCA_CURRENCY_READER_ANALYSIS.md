# SCA Currency Grid — Why the Deterministic Reader Misaligns (analysis, no code changes)

**Question:** why do the SCA currency columns (sale price / net adjustment / adjusted sale price / GLA %) misalign deterministically, forcing the LLM repair — and what would a stronger deterministic parser need?

**Method:** read-only analysis of `app/extraction/comp_grid_extractor.py` (pdfplumber) and `app/extraction/sca_grid_matrix.py` (Camelot), plus a real failure observed in the live run (`Camelot lattice failed for 28203 Fantail Dr ... Sequence index out of range`). No code was changed.

---

## 1. There are two deterministic readers, and only one of them even *tries* currency

| Reader | File | Reads | Currency columns? |
|---|---|---|---|
| pdfplumber x-band | `comp_grid_extractor.py` | descriptive fields (address, proximity, date, condition, quality, GLA, location) | **No** — its own docstring (line 30): *"DESCRIPTIVE fields only — the currency columns (sale price, net adjustment, adjusted sale price) are right-aligned … **left to Camelot.**"* |
| Camelot lattice | `sca_grid_matrix.py` | the bordered table as a cell matrix | **Yes** — this is the *only* deterministic currency path |

So the currency grid rests **entirely on Camelot lattice**. When Camelot can't read the page, there is **no deterministic currency fallback** — which is exactly the gap the SCA-LLM fills.

---

## 2. Why Camelot (the currency reader) misaligns — root causes

### Cause A — Lattice needs ruling lines that often aren't there (the #1 cause)
`sca_grid_matrix.py:128` calls `camelot.read_pdf(..., flavor="lattice", line_scale=40)`. **Lattice detects cells from the table's drawn grid lines.** On:
- **scanned / flattened / faxed URARs** (no vector lines),
- **forms with faint or partial borders**,

…Camelot finds no cell matrix and either **raises** (the live run's `Sequence index out of range`) or returns no tables → the function returns `{}` → **zero deterministic currency** → the pdfplumber fallback (which doesn't read currency) leaves it empty → **the LLM is the only thing that produces the numbers.** There is **no `flavor="stream"` / positional fallback** for borderless grids.

### Cause B — Fixed column offsets assume one exact layout
Camelot's mapping is hardcoded by position:
- `subj_col = comp_cols[0] - 2` (line 147) — subject is assumed two columns left of comp 1.
- `adj_col = cc + 2` (line 210) — each comp's +/- adjustment is assumed two columns right of its value.

When an AMC form variant, or Camelot's own column-splitting, shifts these by even one column, the `+2` points at the **wrong cell** → the adjustment is read from a neighboring field or comes back empty. The geometry is **assumed, not detected per-form.**

### Cause C — Row merges silently drop adjustments
When horizontal rule lines are missing, Camelot **merges adjacent rows**. The code detects this (line 204–209): a discrete-code cell carrying extra tokens (`"Q3 18"`) means a merge, so *"the value in the +/- column belongs to one of the OTHER merged rows"* — and it **skips the adjustment** to avoid a false zero-adj finding. Correct defensively, but the result is a **missing adjustment** the LLM then has to supply.

### Cause D — The adjusted-price dollar is deliberately *not* read here
On the "Adjusted Sale Price" row, the code reads only **net% / gross%** (line 158–167) and **excludes the right-aligned `$` (cc+2)** so a dollar isn't mistaken for a percent. So `comp_i_adjusted_sale_price` is **not produced by Camelot at all** — it's reconstructed as `sale_price + net_adjustment` or comes from the LLM. If `net_adjustment` is missing/misread (Causes A–C), the adjusted price is wrong — and this is precisely the "cost-approach value leaks into the adjusted row" symptom `_overlay_sca_llm` exists to repair.

### Cause E — pdfplumber's fallback can't rescue currency either
Even where pdfplumber runs (`comp_grid_extractor.py`), its own comments admit the geometry is fragile for right-aligned numbers:
- **Hardcoded 55% value/adjustment split** (line 213: `half = ax + (nxt-ax)*0.55`). Right-aligned currency and wide adjustments **cross that boundary**, landing in the wrong sub-cell.
- **The "glue" problem** (line 229–255): pdfplumber concatenates a comp's adjustment with the **next** comp's value/date (`"+11,160s05/26;c04/26"`). Dates are recovered with a regex scan, but **site size is explicitly given up** (*"a positional scan yields WRONG numbers … We keep band-based … else → SCA-11 VERIFY"*). Currency has the same glue with no delimiter to split on.
- **Column anchors are derived from the Address row** (`_column_anchors`, line 76). A garbled/missing Address row → wrong anchors → the whole grid shifts.

---

## 3. The one-sentence root cause
**The deterministic currency reader is lattice-only with fixed column offsets, so it works on clean vector-bordered URARs in the expected layout and fails — outright or by mis-offset — on scanned/flattened/faint-line PDFs and AMC layout variants; there is no right-alignment-aware, borderless-table fallback, so on those documents the LLM is the only thing that reads the currency grid.** That is why CLAUDE.md P-14a marks the SCA-LLM load-bearing.

---

## 4. What a stronger deterministic parser would need (design only — NOT implemented)

To shrink the LLM from "load-bearing" to "true last-resort fallback":

1. **Borderless-table fallback.** Add a `flavor="stream"` (whitespace) Camelot pass, or a custom positional reader, for when lattice finds no lines. Today it's lattice-or-nothing.
2. **Right-alignment-aware column model.** Currency cells right-align to the column's right edge. Instead of a 55% split, detect each comp column's **right edge** from the header `COMPARABLE SALE #` x-positions (or the Sale-Price row `$` anchors) and assign each number to the nearest right edge. This is the single biggest robustness win for right-aligned numbers.
3. **+/- checkbox anchoring.** The "+ –" marks sit at fixed x inside each comp cell. Locate them to split *value* vs *adjustment* precisely, replacing the heuristic 55% boundary.
4. **De-glue by column boundary.** Split a concatenated token (`"+11,160s05/26"`) at the detected column-boundary x, rather than relying on delimiters — fixes the glue for currency and site size, not just dates.
5. **Per-form geometry, not fixed offsets.** Derive `subj_col` / `adj_col` from the detected header + checkbox positions per document, instead of hardcoded `-2` / `+2`.
6. **Table-structure OCR for scans.** For image-only grids, run PaddleOCR PP-Structure (table recognition) to get a cell matrix before parsing — today scanned grids go straight to the LLM.
7. **Confidence-gate the LLM.** `sca_grid_matrix` already computes `_sca_grid_accuracy`. Today `_overlay_sca_llm` runs the LLM **"whenever available"** (it says so) — even on clean-lattice docs Camelot nailed. Gating the LLM to fire **only when Camelot accuracy is low, the page is borderless, or `adjusted` looks implausible** would skip it on the easy documents — an **accuracy-safe** call reduction (unlike batching/caching), and the most immediate token win.

---

## 4b. MEASURED — Camelot success across the corpus (zero Groq, `measure_camelot_success.py`)

Ran the real Camelot reader on every unique appraisal PDF on hand. The result **refines the story above**:

| Doc (7 unique) | status | Camelot accuracy | comp sale-prices | adjustments |
|---|---|---|---|---|
| 28203 Fantail Dr | OK | 88% | 6 | 28 |
| 8234 E Pearson | OK | 86% | 6 | 14 |
| 96 Baell Trace Ct SE | OK | 88% | 6 | 6 |
| 2307 Merrily Cir N | OK | 88% | 9 | 38 |
| 1718 Theon St | OK | 85% | 3 | 10 |
| 90 NE 32nd St | OK | 88% | 4 | 8 |
| 191 Neeley Pl | OK | 85% | 3 | 19 |

**Key correction:** on these (all **digital/vector** PDFs), **Camelot does NOT fail — it succeeds on 100%**, producing the full comp sale prices (6 = 2 grid pages × 3 comps on most). The catastrophic "lattice raises / returns empty" path (Cause A) hit the **contract and order-form pages** in the live run, **not the appraisal grid pages** of these digital reports.

Two honest consequences:
1. **Raw Camelot accuracy is a poor gate.** Every doc clusters at **85–88%** — there is no clean threshold that separates "trust it" from "call the LLM." (My initial 90% cutoff scored 0% skippable, which is a threshold artifact, not a real signal.)
2. **On digital docs the LLM is a *repair/confirm* layer, not the sole reader.** Camelot already returns the sale prices; the LLM's marginal value is fixing **adjustment-column** misalignment (the `+2`-offset / right-alignment weakness), and confirming `adjusted ≈ sale + net`.
3. **The "LLM is the only option" case is SCANNED PDFs** — and there are **none in this corpus**, so that failure rate is **unmeasured here**. It will appear as soon as scanned/faxed appraisals enter the feed.

**Better gate than raw accuracy:** `_overlay_sca_llm` *already computes* a `suspect` flag (adjusted differs from sale by >25%, lines 226–237) but **runs the LLM anyway**. Gating the SCA-LLM to fire only when **sale prices are missing/partial, OR `suspect` is true, OR accuracy is very low (<~70, i.e. a real scan)** would skip it on every clean self-consistent doc — accuracy-safe, because the LLM still fires exactly where the deterministic numbers don't validate.

---

## 5. How this ties back to the optimization goal

- **Item 7 (confidence-gating the SCA-LLM) is the highest-value, lowest-risk lever.** It cuts LLM calls on every clean-lattice document without touching extraction quality (the LLM still fires exactly where the deterministic reader is weak). It is measurable with the existing harness (PASS/FAIL/VERIFY off-vs-on, plus call count).
- **Items 1–6 are the durable HomeVision-style fix:** make the deterministic currency reader strong enough (right-edge alignment + borderless fallback + per-form geometry) that the LLM is needed only on genuinely unreadable scans. That's what moves Ardur from ~11.6K tokens/doc toward HomeVision's ~1–3K — *and* it's the foundation the existing spatial-bounding-box work is already heading toward.
- **Caching/batching were stopgaps; this is the real headroom.** None of items 1–7 are implemented here — this is analysis only, to inform whether/how to proceed.
