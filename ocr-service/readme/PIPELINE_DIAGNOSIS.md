# Pipeline Diagnosis — Why Results Don't Match HomeVision Standards

**Document:** `96 Baell Trace Ct SE.pdf` (27 pages, UAD 1004, Colquitt County GA)
**DB document_id:** `244aa91e-1ebb-4675-9b33-665d13b74c65`
**Date of analysis:** 2026-05-04
**Status of system:** 138 rules ran in 28.4 s. 33/33 fields flagged low-confidence. 50.7% pass rate, but **most "PASS" results are spurious** — they pass on garbage data because rules can't distinguish "field missing" from "field filled with the next label."

---

## TL;DR — The One Bug That Causes Most of the Damage

In `app/services/phase2_extraction.py:582–625`, the generic extractor pattern looks like:

```python
r"Neighborhood Name[:\s]+([^\n]+)"
```

`[^\n]+` is greedy until end-of-line. On a UAD 1004 form, OCR (PyMuPDF embedded text, in this case — see `processing_metrics.json` `extraction_method=embedded`) emits **all labels in row N first, then all values in row N+1**. So the document text reads:

```
Neighborhood Name
Map Reference
Census Tract
Occupant
…
Sagecreek            ← actual value 4 lines later
12-3
9603.02
Owner
```

The regex matches `Neighborhood Name` then captures everything to the next `\n`, which is the **next label** (`Map Reference`). Same for `Map Reference → Census Tract`, `Census Tract → Occupant`, `County → Legal Description`, `Legal Description → Assessor's Parcel #`, `Assessor's Parcel # → Tax Year`, etc.

**Evidence — `extracted_fields.json`:**

| field_name | extracted value | should be | extraction_method |
|---|---|---|---|
| property_address | `City` | `96 Baell Trace Ct SE` | spatial_anchor |
| city | `null` | `Moultrie` | not_found |
| state | `null` | `GA` | not_found |
| zip_code | `null` | `31788` | not_found |
| county | `Legal Description` | `Colquitt` | spatial_anchor |
| owner_of_public_record | `County` | (actual owner name) | spatial_anchor |
| legal_description | `Assessor's Parcel #` | (actual legal text) | spatial_anchor |
| assessors_parcel_number | `Tax Year` | (actual APN) | spatial_anchor |
| neighborhood_name | `Map Reference` | `Sagecreek` (or similar) | spatial_anchor |
| map_reference | `Census Tract` | (actual map ref) | spatial_anchor |
| census_tract | `Occupant` | `9603.02` | regex_fallback |
| lender_name | `to evaluate the property that is the subject of this appraisal for a mortgage` (boilerplate from page 6) | `Clear2 Mortgage, Inc` | spatial_anchor |
| lender_address | `Is the subject property currently offered for sale or has it been offered for sale in the twelve months prior to the effective date of this appraisal?` | (actual lender address) | spatial_anchor |

This off-by-one explains the cascade of FAIL/VERIFY results in `qc_rule_result.json`:

- **S-1 FAIL**: appraisal address resolves to `"City"` → 10.3% match against the engagement letter `"96 SE Baell Trace Ct Moultrie GA 31788"`.
- **S-6 FAIL**: census_tract = `"Occupant"` → not numeric → fails UAD format check.
- **S-10 FAIL**: lender_name is page-6 boilerplate → mismatch with engagement letter `"Clear2 Mortgage, Inc"`.
- **XF-4 FAIL**: cross-form address mismatch = same root cause.
- All `MANUAL_PASS` rules (48 of them, including SCA-1, SCA-2, SCA-7, SCA-8, SCA-12, SCA-17, SCA-18, FHA-3..14, etc.) are downgraded to "manual" precisely because the underlying field came out wrong or empty.

---

## Diagnosis by Pipeline Layer

### 1. OCR Layer (`app/ocr/ocr_pipeline.py`)

`processing_metrics.json` reports `extraction_method=embedded`, `pages_processed=27`, `ocr_time_ms=28451`. The PDF has embedded text, so PyMuPDF was used and Tesseract was skipped. **OCR itself is not the bottleneck — the *layout* of the embedded text stream is.**

The 1004 form is a tabular layout. PyMuPDF flattens it row-by-row, label-row first, value-row second. The current extractor assumes value follows label on the *same line*. It does not.

#### Coordinate-storing problem
`phase2_extraction.py:653–691` (`_bbox_kwargs`) builds a bbox by counting characters and newlines in the page text. It does **not** use the actual OCR/PDF word geometry except via the soft fallback `self._word_bbox(page_num, value)` (line 667). For embedded-text pages, `_word_bbox` is only populated if `_word_index` was filled — which it is not for the embedded path. Result: every bbox is a coarse, character-position approximation. The frontend's PDF highlight rectangle therefore points at the wrong region for almost every field.

This is the "coordinate storing problem" you mentioned. The fix is to hydrate `_word_index` from `page.get_text("words")` for embedded pages and from Tesseract's `image_to_data` for OCR pages, then call `_word_bbox` first, before falling back to character-position.

### 2. Extraction Layer (`app/services/phase2_extraction.py`)

| Bug | Location | What's wrong | Why it matters |
|---|---|---|---|
| **B1. Off-by-one greedy regex** | `_extract()` lines 582–625; pattern definitions throughout (e.g. lines 184, 189, 194, 265) | `[^\n]+` captures the next label when the value is on a different line | Source of >70% of garbage extractions |
| **B2. No "value vs label" sanity check** | `_extract()` line 598 | `match.group(1)` is returned without checking if the captured text *is itself* a known form label | Silently emits labels-as-values |
| **B3. Lender extractor reads the whole document** | `meta["lender_name"]` lines 254–262 | `text` is the entire document concatenated. Pattern matches "Lender/Client" inside page-6 boilerplate ("…the Lender/Client and HUD/FHA…") | Returns the FHA Intended Use boilerplate as the lender |
| **B4. Comparable section bounds break on OCR noise** | `_extract_comparables()` lines 1190–1269 | When the section regex fails to find `COMPARABLE 2` boundary, it captures the rest of the document. The first street-number pattern hit becomes the comp address — that's the appraiser's office on the signature page (`304 Janet St. Suite E Valdosta, G2 31602`) | All three comp addresses came back as the appraiser's office |
| **B5. Bbox is character-position approximation** | `_bbox_kwargs()` lines 653–691; `_word_bbox()` lines 696–719 | `_word_index` not populated for embedded path; bbox derived from `\n` counts | Frontend highlights wrong region |
| **B6. Tax Year regex too narrow** | line 173 | Only matches `r"Tax Year[:\s]+(\d{4})"` — works only when year is on same line | Captured `2025` here only because the year happened to be one of the next tokens |
| **B7. Census Tract has wrong fallback ordering** | lines 192–195 | First pattern is strict `\d{4}\.\d{2}` (correct). The fallback `[^\n]+` then over-captures on flatten | Returned `"Occupant"` |
| **B8. Lender post-clean regex wrong** | line 262 (`post_clean`) | Strips trailing `Address|Client Address` text but doesn't help when the match ate boilerplate from a different page | No post-process can fix a wrong-page match |
| **B9. Owner-of-record does not exist as a real anchor** | line 12 area (S-3 region) | `r"Owner of (?:Public )?Record[:\s]+([^\n]+)"` would similarly grab next label — confirmed: extracted value = `"County"` | S-3 PASSes wrongly |

### 3. Rule Engine (`app/rule_engine/engine.py`)

The engine itself is structurally sound. Concerns:

- **Status casing inconsistency**: `qc_rule_result.json` shows mixed `pass` vs `FAIL` vs `MANUAL_PASS`. The schema in `CLAUDE.md` is upper-case (`PASS|FAIL|VERIFY|...`). Sort/filter logic that does case-sensitive compares will lose rows.
- **`MANUAL_PASS` is being used as a shrug** — 48 rules return `MANUAL_PASS` whenever extracted data is missing. That should be `VERIFY` per the documented schema. Operators reading the dashboard see "manual pass" and assume "OK" — it is not OK; it means we don't know.
- All 138 rules execute (confirmed via `app/rules/__init__.py` import chain), so non-Phase-3 categories (FHA/USDA/PH/SK/SCA-12+/etc.) are all running but most are gated on fields that don't extract correctly, hence the 48× `MANUAL_PASS`.

### 4. Java Side

I have not yet finished auditing `qc/`, `common/`, `batch/`, `app/`, `user/`. From the directory listing in the project root they are present and active. Listed as a follow-up in the fix plan below — I will not touch Java until you confirm the Python fix order, because changes to the rule_result schema (status casing, new fields) propagate into Java DTOs and break the frontend.

### 5. Rule Coverage vs `QCChceklistOpus.md`

The full QC checklist defines ~140 rules across 21 categories. `rules_config.json` has **138 rule rows**, so coverage is *registered*. But several are not actually evaluating, only emitting placeholder messages (look at the `MANUAL_PASS` list: SCA-7, SCA-8, SCA-12, SCA-17, SCA-18, SCA-23..27, FHA-3..14, ADD-1, ADD-5, ADD-6, ADD-8, ADD-9, MF-1, MF-2, IA-1, etc.). Their messages all read `"<thing> evidence found. Verify <thing>."` — that's a stub, not an evaluation.

So your gut feeling is correct: **the rules under `app/rules/*.py` are partly stub-only — they're not actually computing the QC checks defined in `QCChceklistOpus.md`.** The rules are *wired in* but most do not reach the validations described in the checklist.

---

## Why This Doesn't Match HomeVision

HomeVision-class output requires three things this pipeline currently lacks:

1. **Geometry-aware extraction.** Their extractor reads the PDF as a 2-D grid (column-aware), not as a text stream. Until our extractor uses word bounding boxes to find the value cell *next to* the label cell, every tabular field will be at the mercy of OCR row-flattening order.
2. **Cross-document reconciliation that knows what "missing" means.** When `lender_name` is page-6 boilerplate, S-10 should refuse to compare and emit `VERIFY (extraction failed)` — not `FAIL (mismatch)` and not `MANUAL_PASS`. Right now it emits FAIL, which is "false negative" feedback to the operator.
3. **Real rule logic, not stubs.** ~50 rules currently emit "evidence found, please verify" boilerplate. They need actual checks against extracted values, with clear FAIL conditions and rejection-template messages from the checklist.

---

## Fix Plan (Phased — review before I proceed)

### Phase A — Stop emitting wrong values (1 day)
1. Add a label-stop set + value-vs-label sanity check inside `_extract()` so the extractor returns `not_found` instead of "the next label." This alone will turn ~13 fake PASSes into honest `VERIFY` results. **Surgical, ~30 lines, low risk.** I'm shipping this in this turn.
2. Tighten `lender_name` and `lender_address` to search only pages 1–2 of the appraisal text by passing a `text_window` argument keyed off the page-position map.
3. Tighten `_extract_comparables` so a missing `COMPARABLE 2` boundary results in a graceful `not_found` rather than swallowing the rest of the document.

### Phase B — Geometry-aware extraction (3–5 days)
1. Hydrate `_word_index` from PyMuPDF `page.get_text("words")` (returns `(x0, y0, x1, y1, word, block, line, word_no)`) for embedded pages and from `pytesseract.image_to_data` for OCR pages. Persist into `page_ocr_results` as JSON `word_boxes`.
2. Replace label-anchored regex with **column-search**: locate the label's word box, then look in the cell *to the right of* (and on tabular UAD forms, sometimes *below*) the label box.
3. Use the same word boxes to compute real `bbox_x/y/w/h` for `extracted_fields`. The frontend highlight will then point at the value, not at "approximately where line 4 column 30 might be."

### Phase C — Replace stub rules with real evaluations (per category, 1–2 days each)
1. Convert each `"<X> evidence found. Verify <X>."` rule into actual checks against the extracted values, using the rejection templates already documented in `QCChceklistOpus.md`.
2. Standardize status casing (`PASS|FAIL|VERIFY|WARNING|SKIPPED|SYSTEM_ERROR` upper-case) and remove the ad-hoc `MANUAL_PASS` status.
3. Add unit tests against the three reference PDFs from `CLAUDE.md`: `96 Baell Trace Ct SE`, `2307 Merrily Cir N`, `8234 E Pearson`.

### Phase D — Java audit (1 day)
1. Audit `qc/`, `common/`, `batch/`, `app/`, `user/` for: status-casing assumptions, response DTOs that omit new bbox fields, frontend payload contracts.
2. Update Java DTOs and any persistence mapping where Python now emits richer extraction metadata.

### Phase E — Coordinate persistence (bundled with Phase B)
- Already covered: hydrate word boxes → store `bbox_x/y/w/h` from real geometry → frontend highlights reflect actual on-page position.

---

## What Will Change in `extracted_fields` After Phase A (this commit)

Before:

| field | value | method |
|---|---|---|
| neighborhood_name | `Map Reference` | spatial_anchor |
| county | `Legal Description` | spatial_anchor |
| census_tract | `Occupant` | regex_fallback |
| owner_of_public_record | `County` | spatial_anchor |

After:

| field | value | method |
|---|---|---|
| neighborhood_name | `null` | not_found |
| county | `null` | not_found |
| census_tract | `null` | not_found |
| owner_of_public_record | `null` | not_found |

Rules will then emit `VERIFY` (with an honest "extractor could not locate value") instead of fake PASS/FAIL. This is a **correctness improvement, not a regression** — operators will see fewer false positives and more accurate "we don't know" flags. Phase B will turn most of those `not_found` into real values.

---

## Summary Matrix — Bug → File → Severity → Fix Phase

| ID | Where | Severity | Phase |
|---|---|---|---|
| B1 | phase2_extraction.py:582–625 (greedy `[^\n]+`) | 🔴 Critical | A (now) |
| B2 | phase2_extraction.py:598 (no label-vs-value check) | 🔴 Critical | A (now) |
| B3 | phase2_extraction.py:254–262 (lender no page-scope) | 🔴 Critical | A (now) |
| B4 | phase2_extraction.py:1190–1269 (comp section bounds) | 🔴 Critical | A (now) |
| B5 | phase2_extraction.py:653–719 (bbox approximation) | 🟡 High | B |
| B6 | phase2_extraction.py:173 (Tax Year regex) | 🟡 High | A |
| B7 | phase2_extraction.py:192–195 (Census Tract fallback) | 🟡 High | A |
| B8 | phase2_extraction.py:262 (post_clean weak) | 🟢 Low | A |
| B9 | Subject S-3 owner-of-record | 🔴 Critical | A |
| Stubs | rules/*.py — ~50 rules emit "evidence found" boilerplate | 🟡 High | C |
| Status casing | rule_engine + Java DTOs | 🟡 High | C+D |
| Coordinate storage | phase2_extraction + page_ocr_results schema | 🟡 High | B |

---

*This file is a living diagnosis. Update as Phase A/B/C/D fixes land.*
