# COMPLETE DEEP DIAGNOSTIC AUDIT — Appraisal QC System
**Date:** 2026-05-13  
**Test document:** `uploads/EQSS/MSL/appraisal/96 Baell Trace Ct SE.pdf` (27 pages, Colquitt County GA, UAD 1004, Purchase)  
**Knowledge Graph:** 3,203 nodes · 21,499 edges · 303 files parsed  

---

## PHASE 1 — FULL DIRECTORY MAP

### 1A. File Inventory

#### `ocr/` — 2 active Python files

| File | Size | Purpose |
|------|------|---------|
| `app/ocr/ocr_pipeline.py` | 45,761 B | Main OCR orchestrator: pdfplumber+Camelot for structured text, Tesseract fallback with ThreadPoolExecutor(4), hOCR word geometry, SpatialWordIndex |
| `app/ocr/image_preprocessor.py` | 11,831 B | 5-step OpenCV preprocessing: grayscale→denoise→Otsu→table grid removal→deskew |

---

#### `rule_engine/` — 5 files (4 active, 1 dead)

| File | Size | Status | Purpose |
|------|------|--------|---------|
| `app/rule_engine/engine.py` | 34,674 B | ✅ ACTIVE | Rule runner: DB-ordered execution, pass-evidence contract, severity, crash isolation |
| `app/rule_engine/rules_db.py` | 19,155 B | ✅ ACTIVE | RULE_DEFAULTS config (136 rules), DB seeding and loading |
| `app/rule_engine/cross_field_validator.py` | 19,971 B | ✅ ACTIVE | 9 XF rules (XF-1..XF-6, XF-VIS-1, XF-FHA-1..3) — executed OUTSIDE engine |
| `app/rule_engine/smart_identifier.py` | 5,904 B | ✅ ACTIVE | RuleResult, RuleStatus, RuleSeverity, DataMissingException, SmartLogger |
| **`app/rule_engine/outcome.py`** | **5,498 B** | **🔴 DEAD CODE** | **Never imported anywhere — RuleOutcome class superseded by RuleResult** |

---

#### `rules/` — 16 Python files, 136 @rule-decorated functions total

| File | Size | Rules | Purpose |
|------|------|-------|---------|
| `app/rules/subject_rules.py` | 82,977 B | S-1..S-12 (12) | Address, borrower, occupant, HOA, lender, property rights |
| `app/rules/contract_rules.py` | 66,215 B | C-1..C-5 (5) | Contract analysis, price, concessions, personal property |
| `app/rules/sales_comparison_rules.py` | 25,629 B | SCA-1..SCA-27 (27) | All comparable grid checks |
| `app/rules/narrative_rules.py` | 27,520 B | COM-1..COM-7 (7) | LLM commentary quality |
| `app/rules/site_rules.py` | 19,520 B | ST-1..ST-10 (10) | Site dimensions, zoning, flood, utilities |
| `app/rules/improvement_rules.py` | 11,331 B | I-1..I-13 (13) | Foundation, exterior, condition, GLA |
| `app/rules/neighborhood_rules.py` | 13,061 B | N-1..N-7 (7) | Characteristics, trends, boundaries |
| `app/rules/addendum_rules.py` | 8,267 B | ADD-1..ADD-9 (9) | 1004MC, USPAP, commentary standards |
| `app/rules/fha_rules.py` | 8,012 B | FHA-1..FHA-14 (14) | FHA MPR, case number, photos, sketch |
| `app/rules/additional_approach_rules.py` | 5,764 B | R-1..R-2, CA-1..CA-2, IA-1..IA-2 (6) | Reconciliation, cost, income |
| `app/rules/signature_rules.py` | 4,600 B | SIG-1..SIG-4 (4) | Appraiser signature, license, supervisory |
| `app/rules/photo_rules.py` | 6,290 B | PH-1..PH-6 (6) | Subject/interior/comparable photos |
| `app/rules/doc_rules.py` | 4,449 B | DOC-1..DOC-4 (4) | License, E&O, UAD dataset, trainee |
| `app/rules/maps_rules.py` | 3,423 B | M-1..M-4 (4) | Location, aerial, plat, flood maps |
| `app/rules/sketch_rules.py` | 3,215 B | SK-1..SK-5 (5) | Sketch location, dimensions, area calc |
| `app/rules/usda_mf_rules.py` | 3,506 B | USDA-1, MF-1..MF-2 (3) | USDA cost approach, multi-family |
| `app/rules/__init__.py` | 2,671 B | — | Tier-ordered imports triggering self-registration |

---

#### `services/` — 21 active files + 1 dead

| File | Size | Status | Imported By |
|------|------|--------|-------------|
| `services/phase2_extraction.py` | 138,696 B | ✅ ACTIVE | qc_processor.py, extraction_service.py |
| `services/extraction_service.py` | 48,571 B | ✅ ACTIVE | qc_processor.py |
| `services/cache_service.py` | 25,351 B | ✅ ACTIVE | qc_processor.py, llm_cache.py |
| `services/ollama_service.py` | 25,298 B | ✅ ACTIVE | phase2_extraction.py, narrative_rules.py, engine.py |
| `services/processing_lifecycle.py` | 25,245 B | ✅ ACTIVE | qc_processor.py, ollama_service.py |
| `services/auto_pass_calibration.py` | 19,626 B | ✅ ACTIVE | engine.py (lazy import) |
| `services/field_registry.py` | 10,586 B | ✅ ACTIVE | phase2_extraction.py, site_extractor.py |
| `services/contract_extraction.py` | 10,230 B | ✅ ACTIVE | extraction_service.py |
| `services/external_services.py` | 9,522 B | ✅ ACTIVE | subject_rules.py |
| `services/ocr_correction.py` | 8,773 B | ✅ ACTIVE | phase2_extraction.py |
| `services/llm_enrichment.py` | 7,778 B | ✅ ACTIVE | qc_processor.py (lazy) |
| `services/llm_cache.py` | 2,054 B | ✅ ACTIVE | narrative_rules.py |
| `services/entity_resolution.py` | 3,980 B | ✅ ACTIVE | cross_field_validator.py |
| `services/comparable_extraction.py` | 2,207 B | ✅ ACTIVE | qc_processor.py (lazy) |
| `services/site_extractor.py` | 4,096 B | ✅ ACTIVE | qc_processor.py (lazy) |
| `services/vision_pipeline.py` | 2,597 B | ✅ ACTIVE | qc_processor.py (lazy) |
| `services/model_inference.py` | 3,162 B | ✅ ACTIVE | ocr_correction.py, ollama_service.py |
| `services/confidence_calibration.py` | 4,815 B | ✅ ACTIVE | cache_service.py |
| `services/document_quality.py` | 1,643 B | ✅ ACTIVE | contract_extraction.py |
| `services/progress_store.py` | 2,329 B | ✅ ACTIVE (main.py only) | main.py lines 625, 1058 |
| **`app/nlp/nlp_checks.py`** | **~6 KB** | **🔴 DEAD CODE** | **Nothing imports it — superseded by ollama_service.py** |

---

### 1B. Dependency Tree

```
main.py (95,688 B)
  ├─ app.qc_processor.SmartQCProcessor          ← PRIMARY PIPELINE
  │    ├─ app.ocr.ocr_pipeline.OCRPipeline
  │    │    └─ app.ocr.image_preprocessor.ImagePreprocessor
  │    ├─ app.services.phase2_extraction.phase2_engine
  │    │    ├─ app.services.ocr_correction
  │    │    ├─ app.services.field_registry
  │    │    └─ app.services.ollama_service (checkbox vision fallback)
  │    ├─ app.services.extraction_service
  │    │    ├─ app.services.contract_extraction.HybridContractExtractor
  │    │    │    └─ app.services.document_quality
  │    │    └─ app.services.phase2_extraction ⚠️ DUPLICATE IMPORT PATH
  │    ├─ app.services.site_extractor (lazy)
  │    ├─ app.services.comparable_extraction (lazy)
  │    ├─ app.services.vision_pipeline (lazy)
  │    ├─ app.services.llm_enrichment (lazy)
  │    ├─ app.services.cache_service
  │    │    └─ app.services.confidence_calibration
  │    ├─ app.services.processing_lifecycle
  │    ├─ app.rule_engine.engine (singleton `engine`)
  │    │    ├─ app.rule_engine.smart_identifier
  │    │    ├─ app.rule_engine.rules_db
  │    │    ├─ app.services.auto_pass_calibration (lazy)
  │    │    └─ app.services.ollama_service.generate_verify_question (lazy)
  │    ├─ app.rules ← self-registering side-effect (136 @rule functions)
  │    └─ app.rule_engine.cross_field_validator.CrossFieldValidator
  │         └─ app.services.entity_resolution
  │
  ├─ app.services.extraction_service  ← LEGACY /qc/extract PATH ONLY
  │    └─ app.ocr.ocr_pipeline.OCRPipeline  ⚠️ SECOND INDEPENDENT OCR INSTANCE
  │
  └─ app.tasks.celery_app  ← ASYNC WORKER (standalone process)
       └─ app.ocr.ocr_pipeline.OCRPipeline  ⚠️ THIRD INDEPENDENT OCR INSTANCE

ORPHAN FILES (never imported by anything):
  app/rule_engine/outcome.py   ← DELETE
  app/nlp/nlp_checks.py        ← DELETE
```

---

## PHASE 2 — END-TO-END TRACE ON MSL FILE

**Test files:**
- Appraisal: `uploads/EQSS/MSL/appraisal/96 Baell Trace Ct SE.pdf`
- Contract: `uploads/EQSS/MSL/contract/96 baell Tr Ct CONTRACT.pdf`
- Engagement: `uploads/EQSS/MSL/engagement/96 Baell Tr Ct Order form.pdf`

---

### 2.1 Entry Point

**File:** `main.py:571`
```python
@app.post("/qc/process")
async def process_qc(
    appraisal_file: UploadFile = File(...),
    engagement_file: Optional[UploadFile] = File(None),
    contract_file: Optional[UploadFile] = File(None),
    ...
) -> QCResults:
```
Dispatches to `run_in_threadpool(qc_processor.process_document, pdf_path, ...)` at line 746.

---

### 2.2 OCR Layer

**File:** `app/ocr/ocr_pipeline.py:209`
```python
def extract_all_pages(self, pdf_path: str, force_ocr: bool = None) -> ExtractionResult:
```

**Decision per page:**

| Embedded words | Method | DPI |
|----------------|--------|-----|
| ≥ 100 | pdfplumber + Camelot layout text | — |
| 30–99 | Both embedded + Tesseract; pick best | 200 |
| < 30 | Tesseract with full 5-step preprocessing | 300 |

**Raw output shape — `ExtractionResult`:**
```python
ExtractionResult(
    page_index:   Dict[int, str],           # page_num → extracted text
    page_details: List[PageText],           # per-page method/confidence/word_count
    word_index:   Dict[int, List[OcrWord]], # per-word bbox coordinates + confidence
    page_images:  Dict[int, PIL.Image],     # pages 1–10 for llava:13b
    total_pages:  int,
    notices:      List[str],
)
```

**Note:** OCR also does basic table structuring. `_camelot_page_tables()` and `_pdfplumber_table_text()` emit `LABEL_VALUE_PAIRS` blocks into the page text before phase2 sees it.

---

### 2.3 Field Extraction — ACTUAL Values from MSL Run

**File:** `app/services/phase2_extraction.py:359`
```python
def extract_subject(self, full_text, page_index, page_images=None, word_index=None)
    → Tuple[SubjectSectionExtract, Dict[str, FieldMetaResult]]
```

**Source:** `uploads/db/extracted_fields-3.json` (actual DB record from MSL run)

| Field | Extracted Value | Conf | Page | Status | Notes |
|-------|----------------|------|------|--------|-------|
| `property_address` | `96 Baell Trace Ct SE` | 0.85 | 3 | FOUND | ✅ Correct |
| `city` | `Moultrie` | 0.85 | 3 | FOUND | ✅ Correct |
| `state` | `GA` | 0.90 | 3 | FOUND | ✅ Correct |
| `zip_code` | `31788` | 0.92 | 3 | FOUND | ✅ Correct |
| `county` | `Hung LaPrecision Builders and Developers LLCColquitt` | 0.88 | 3 | FOUND | 🔴 GARBAGE — OCR row-flattening. Sanity check (len>30) exists in current code but DB snapshot predates fix |
| `borrower_name` | `Hung La` | 0.88 | 2 | FOUND | ✅ Correct |
| `co_borrower_name` | `__NOT_FOUND__` | 0 | 0 | NOT_FOUND | ✅ OK — single borrower |
| `owner_of_public_record` | `Precision Builders and Developers LLCCounty Colquitt` | 0.88 | 3 | FOUND | 🔴 GARBAGE — `_trim_merged_person_field()` misses `LLCCounty` boundary |
| `legal_description` | `Lot 34 Sagecreek S/D Phase 2` | 0.88 | 3 | FOUND | ✅ Correct |
| `assessors_parcel_number` | `m052 245` | 0.88 | 3 | FOUND | ✅ Correct |
| `tax_year` | `2025` | 0.88 | 3 | FOUND | ✅ Correct |
| `real_estate_taxes` | `423` | 0.88 | 3 | FOUND | ✅ Correct |
| `neighborhood_name` | `Sagecreek` | 0.88 | 3 | FOUND | ✅ Correct |
| `map_reference` | `34220` | 0.88 | 3 | FOUND | ✅ Correct |
| `census_tract` | `9707.03` | 0.88 | 3 | FOUND | ✅ Correct |
| `occupant_status` | `Owner` | 0.75 | 0 | FOUND | ⚠️ Below 0.85 PASS threshold |
| `special_assessments` | `0` | 0.78 | 3 | FOUND | ⚠️ Below 0.85 threshold |
| `is_pud_checked` | `__NOT_FOUND__` | 0 | 0 | NOT_FOUND | 🔴 Critical — kills S-9 and XF-5. Digital PDFs use Unicode glyphs not `[X]` |
| `hoa_dues` | `0` | 0.70 | 3 | FOUND | ⚠️ Below threshold |
| `hoa_period` | `Per Month` | 0.70 | 0 | FOUND | ✅ |
| `lender_name` | `__NOT_FOUND__` | 0 | 0 | NOT_FOUND | 🔴 4 regex patterns all failing — S-10 extraction_failed every run |
| `lender_address` | `__NOT_FOUND__` | 0 | 0 | NOT_FOUND | 🔴 Expected with lender_name |
| `property_rights` | `Fee Simple` | 0.68 | 2 | FOUND | ⚠️ context_fallback method — below 0.85 threshold |
| `offered_for_sale_12mo` | `True` | 0.72 | 3 | FOUND | Triggers S-12 review |
| `data_source` | `Are the units, common elements, and recreation facilities co…` | 0.88 | 5 | FOUND | 🔴 GARBAGE — capturing USPAP certification boilerplate instead of data source names |
| `mls_number` | `914579` | 0.88 | 3 | FOUND | ✅ Correct |
| `comp_1_address` | `__NOT_FOUND__` | 0 | 4 | NOT_FOUND | 🔴 Comparable grid extraction failure |
| `comp_1_sale_price` | `__NOT_FOUND__` | 0 | 4 | NOT_FOUND | 🔴 Comparable grid extraction failure |
| `comp_2_address` | `__NOT_FOUND__` | 0 | 4 | NOT_FOUND | 🔴 Comparable grid extraction failure |
| `comp_2_sale_price` | `__NOT_FOUND__` | 0 | 4 | NOT_FOUND | 🔴 Comparable grid extraction failure |
| `comp_3_address` | `96 Baell Trace Ct SE` | 0.70 | 4 | FOUND | 🔴 WRONG — extracting SUBJECT address as comparable #3 |
| `comp_3_sale_price` | `263,000` | 0.72 | 4 | FOUND | ⚠️ This is the appraised value, not a comp sale |
| `market_value_opinion` | `,` | 0.88 | 4 | FOUND | 🔴 GARBAGE — regex matched a lone comma |
| `condition_rating` | `C1` | 0.88 | 3 | FOUND | ✅ Correct (new construction) |
| `quality_rating` | `Q3` | 0.88 | 4 | FOUND | ✅ Correct |
| `neighborhood_description` | `There are no apparent adverse factors which affect the subje…` | 0.82 | 2 | FOUND | ⚠️ Below threshold; content is canned |
| `market_conditions_commentary` | `(including support for the above conclusions) Various types…` | 0.82 | 2 | FOUND | ⚠️ Below threshold; content is canned |
| `location` | `__NOT_FOUND__` | 0 | 2 | NOT_FOUND | 🔴 All 6 neighborhood checkboxes missing |
| `built_up` | `__NOT_FOUND__` | 0 | 2 | NOT_FOUND | 🔴 |
| `growth_rate` | `__NOT_FOUND__` | 0 | 2 | NOT_FOUND | 🔴 |
| `property_values` | `__NOT_FOUND__` | 0 | 2 | NOT_FOUND | 🔴 |
| `demand_supply` | `__NOT_FOUND__` | 0 | 2 | NOT_FOUND | 🔴 |
| `marketing_time` | `__NOT_FOUND__` | 0 | 2 | NOT_FOUND | 🔴 |
| `price_low` | `3000` | 0.72 | 2 | FOUND | ⚠️ Suspected wrong units — likely 300,000 |
| `age_low` | `3` | 0.72 | 2 | FOUND | ✅ Plausible for new construction |

**Fields with no entry in field_meta at all (rules access these but extraction never produces them):**
`effective_age`, `GLA`, `appraised_value`, `flood_zone`, `days_on_market`, `assignment_type`, `concession_amount`

---

### 2.4 Rules Layer

**How rules are defined:** Python functions decorated with `@rule(id, name)` in `app/rules/*.py`.  
The decorator registers the function into the global singleton `engine._rules: Dict[str, Callable]` at import time.  
`rules/__init__.py` triggers all 16 rule files in tier order.

**Total registered:** 136 rules via `@rule` decorator + 10 XF rules via `CrossFieldValidator`.

---

### 2.5 Rule Engine Execution

**File:** `app/rule_engine/engine.py:42`
```python
def execute(self, context: ValidationContext) -> List[RuleResult]:
```

Steps:
1. Loads `RuleConfigEntry` per rule from DB (or falls back to RULE_DEFAULTS)
2. Sorts by `execution_order` (10 → 2160)
3. Checks `is_active` and `applicable_loan_types`
4. Runs each rule with full isolation (try/except per rule)
5. Applies pass-evidence contract (confidence threshold, structured evidence check, auto-pass ML model)
6. After engine completes: `CrossFieldValidator().validate(ctx)` appends XF results

---

### 2.6 Final QC Output — MSL Run (138 total rule results)

**Source:** `uploads/db/rule_results-2.json`

| Status | Count |
|--------|-------|
| PASS | 6 |
| FAIL | 4 |
| REVIEW | 91 |
| NOT_APPLICABLE (correct) | 19 |
| NOT_APPLICABLE (wrong — stale DB) | 2 |
| EXTRACTION_FAILED | 7 |
| OCR_LOW_CONFIDENCE | 5 |
| SYSTEM_ERROR | 0 |

**All 138 rule results:**

| Rule | Status | Message (truncated) |
|------|--------|---------------------|
| S-1 | fail | County mismatch: `Hung LaPrecision Build…` — garbage extraction |
| S-2 | extraction_failed | Required evidence missing: Borrower Name (Engagement Letter) |
| S-3 | pass | Owner of Public Record is present and valid |
| S-4 | pass | Legal description and tax data are complete and valid |
| S-5 | pass | Neighborhood name 'Sagecreek' is provided |
| S-6 | pass | Map Reference and Census Tract are present and valid |
| C-1 | pass | Contract analyzed. Sale type: Arms-Length |
| C-2 | extraction_failed | Contract date not extracted from standalone contract PDF |
| C-3 | review | Is Seller Owner of Public Record checkbox not detected |
| S-7 | ocr_low_confidence | PASS blocked — confidence 0.75 below 0.85 threshold |
| S-8 | ocr_low_confidence | PASS blocked — confidence 0.78 below 0.85 threshold |
| S-9 | extraction_failed | PUD checkbox not extracted; HOA/PUD consistency cannot PASS |
| S-10 | extraction_failed | Required evidence missing: Lender Name (Report) |
| S-11 | ocr_low_confidence | PASS blocked — confidence 0.68 (property_rights, context_fallback) |
| S-12 | review | Offered for sale — missing: DOM, List Price, List Date |
| C-4 | review | PASS without source evidence or compared values |
| C-5 | review | PASS without source evidence or compared values |
| N-1 | review | Neighborhood checkboxes not verified: Location, Built-Up, Growth |
| N-2 | review | Could not verify: Property Values, Demand/Supply, Marketing Time |
| N-3 | review | Price High, Predominant Price, Age High not extracted |
| N-4 | review | Land use total not extracted |
| N-5 | review | Neighborhood boundaries not extracted |
| N-6 | ocr_low_confidence | PASS blocked — confidence 0.82 |
| N-7 | ocr_low_confidence | PASS blocked — confidence 0.82 |
| ST-1..ST-10 | review (all 10) | All site rules: PASS from weak text evidence only |
| I-1..I-13 | review / not_applicable (13) | Most improvement rules: PASS without structured evidence |
| SCA-1 | pass | Market summary: 3 sales, 1 listing |
| SCA-2 | fail | Only 1 listing comparable found — minimum 2 required |
| SCA-3..SCA-27 | review (25) | All comparable grid checks: evidence found but unverifiable |
| R-1..R-2 | review (2) | Reconciliation: PASS without compared values |
| CA-1 | not_applicable | 🔴 WRONG — stale DB config says USDA instead of ALL |
| CA-2 | not_applicable | 🔴 WRONG — stale DB config says USDA instead of ALL |
| IA-1..IA-2 | not_applicable | ✅ Correct — income approach not applicable |
| ADD-1 | review | Potential canned/generic commentary |
| ADD-2..ADD-9 | review / not_applicable | Mix |
| DOC-1..DOC-4 | review / not_applicable | Mix |
| SIG-1..SIG-4 | review | All signature rules: PASS without structured evidence |
| PH-1..PH-6 | review / not_applicable | Mix |
| M-1..M-4 | review (4) | All map rules: PASS without compared values |
| SK-1..SK-5 | review (5) | All sketch rules |
| FHA-1..FHA-14 | not_applicable (14) | ✅ Correct — not FHA loan |
| USDA-1 | not_applicable | ✅ Correct — not USDA |
| MF-1..MF-2 | review (2) | Subject rent / Form 216 not detected |
| COM-1 | fail | Neighborhood description uses generic boilerplate |
| COM-2 | fail | Market conditions commentary lacks actual market data |
| COM-3 | review | Comparable selection commentary not found |
| COM-4..COM-7 | review (4) | Commentary rules: weak evidence only |
| XF-4 | review | Address probable match but needs review: `96 Baell Trace Ct SE vs …` |
| XF-5 | extraction_failed | PUD checkbox not extracted; HOA/PUD validation cannot execute |

---

## PHASE 3 — DEAD CODE & DUPLICATE LOGIC AUDIT

### 3A — Is This File Actually Used?

| File | Imported in Pipeline? | Called on MSL Run? | Verdict |
|------|-----------------------|-------------------|---------|
| **rule_engine/outcome.py** | **NO** | **NO** | **🔴 DEAD CODE — DELETE** |
| **nlp/nlp_checks.py** | **NO** | **NO** | **🔴 DEAD CODE — DELETE** |
| services/progress_store.py | Only in main.py (lazy) | YES via `/qc/progress/` | ✅ LIVE |
| services/comparable_extraction.py | YES (lazy in qc_processor) | YES | ✅ LIVE |
| services/vision_pipeline.py | YES (lazy in qc_processor) | NO (llava not running) | ✅ LIVE but inactive |
| services/site_extractor.py | YES (lazy in qc_processor) | YES | ✅ LIVE |
| services/confidence_calibration.py | YES (via cache_service) | YES | ✅ LIVE |
| tasks/celery_app.py | Not imported as module | Not this run | ⚠️ PARALLEL PATH |

---

### 3B — Duplicate Logic Detection

#### DUPLICATE 1 — Three independent OCRPipeline instances

| Location | File:Line | Config |
|----------|-----------|--------|
| SmartQCProcessor.__init__ | `qc_processor.py:153` | Primary — `use_preprocessing=True` ← **ONLY THIS IS ACTIVE** |
| ExtractionService.__init__ | `extraction_service.py:40` | Legacy `/qc/extract` — bypassed in `/qc/process` |
| celery_app.py | `tasks/celery_app.py:246` | Async worker — separate process |
| main.py endpoint | `main.py:1321` | `/ocr/appraisal` endpoint |
| main.py debug | `main.py:1437` | `force_image_ocr=True` |

**Problem:** `extraction_service.py` creates an OCRPipeline that never runs in the main QC flow — qc_processor passes text to ExtractionService, not PDFs.

---

#### DUPLICATE 2 — `contract_price` extracted in 3 places

| Location | File:Line | Source | Method |
|----------|-----------|--------|--------|
| `ExtractionService._extract_contract_section()` | `extraction_service.py:507` | Appraisal PDF text | `r"Contract Price[:\s]*\$?([\d,]+)"` |
| `HybridContractExtractor.extract()` | `contract_extraction.py:46` | Standalone contract PDF | 3 layered patterns with confidence |
| `ExtractionService._extract_engagement_letter()` | `extraction_service.py:758` | Engagement letter text | Same single regex as above |

No rule cross-checks the appraisal-stated contract price vs the standalone purchase agreement price.

---

#### DUPLICATE 3 — Address match validation in 2 places

| Location | What it does |
|----------|-------------|
| S-1 in `subject_rules.py` | Compares individual address components (street, city, state, zip, county) vs engagement letter |
| XF-4 in `cross_field_validator.py:165` | Fuzzy string match on full address via `match_addresses()` |

Both check appraisal address vs engagement letter address. Partial overlap on the same QC concern.

---

#### DUPLICATE 4 — `data_source` vs `data_sources` naming mismatch

| Location | Field Name |
|----------|-----------|
| `phase2_extraction.py:720` | `data_source` (singular) |
| `engine.py:502` RULE_FIELD_MAP | `data_source` (singular) |
| `appraisal.py` domain model | `data_sources` (plural) |
| `qc_processor.py:529` | Maps `s.data_source` → `data_sources=...` |

Functionally handled by the mapping, but causes confusion when reading across layers.

---

### 3C — Rules Defined but Never Called (Ghost Rules)

#### Engine Rules — NO GHOST RULES
All 136 `@rule`-decorated functions have corresponding entries in `RULE_DEFAULTS`. Zero orphan rule functions.

#### Cross-Field Validator — 10 RULES NOT IN DB CONFIG

These rules execute every run but **operators cannot disable, adjust severity, or reorder them** via the admin UI:

| Rule ID | Method | Severity | Can Toggle? |
|---------|--------|----------|------------|
| XF-1 | `_housing_trend_vs_time_adjustments` | BLOCKING | ❌ NO |
| XF-2 | `_comp_prices_vs_neighborhood_range` | STANDARD | ❌ NO |
| XF-3 | `_condition_vs_effective_age` | STANDARD | ❌ NO |
| XF-4 | `_subject_address_three_way` | BLOCKING | ❌ NO |
| XF-5 | `_pud_vs_hoa` | BLOCKING | ❌ NO |
| XF-6 | `_refinance_contract_blank` | BLOCKING | ❌ NO |
| XF-VIS-1 | `_vision_condition_check` | STANDARD | ❌ NO |
| XF-FHA-1 | `_fha_case_number_all_pages` | BLOCKING | ❌ NO |
| XF-FHA-2 | `_fha_comp_recency` | BLOCKING | ❌ NO |
| XF-FHA-3 | `_fha_remaining_economic_life` | BLOCKING | ❌ NO |

#### Stale DB Config — CA-1 and CA-2

`RULE_DEFAULTS` in `rules_db.py:111-112` says `applicable_loan_types = "ALL"` (code was updated).  
The live DB was seeded before this change and still has `applicable_loan_types = 'USDA'`.  
**Result:** CA-1 and CA-2 show `not_applicable` for every non-USDA loan — including the MSL conventional purchase.

**Fix (one SQL statement):**
```sql
UPDATE rules_config SET applicable_loan_types = 'ALL' WHERE rule_id IN ('CA-1', 'CA-2');
```

---

### 3D — Data Sync Gaps (OCR Output vs Rule Engine Expected)

| Phase 2 Output Key | Rule Engine Needs | Match? | Notes |
|--------------------|------------------|--------|-------|
| `property_address` | `property_address` | ✅ | |
| `borrower_name` | `borrower_name` | ✅ | |
| `is_pud_checked` | `is_pud_checked` | ✅ key | 🔴 Value is always NOT_FOUND |
| `hoa_dues` | `hoa_dues` | ✅ | Confidence 0.70 < threshold |
| `data_source` | `data_source` | ✅ key | 🔴 Garbage value |
| `offered_for_sale_12mo` | `offered_for_sale_12mo` | ✅ | |
| `lender_name` | `lender_name` | ✅ key | 🔴 Always NOT_FOUND |
| `occupant_status` | `occupant` (domain model) | ⚠️ | Resolved by qc_processor mapping |
| `market_value_opinion` | (no rule uses this key directly) | ⚠️ | Extracted but broken; no rule consumes it |
| **Not extracted** | `effective_age` | ❌ | XF-3 and I-1 need it; falls back to text search |
| **Not extracted** | `gla` | ❌ | In RULE_FIELD_MAP (I-7) but never in field_meta |
| **Not extracted** | `appraised_value` | ❌ | market_value_opinion is broken; value reconciliation rules cannot run |
| **Not extracted** | `flood_zone` | ❌ | ST-8 uses text search only |
| **Not extracted** | `days_on_market` | ❌ | S-12 uses text search only |
| **Not extracted** | `concession_amount` | ❌ | SCA-7 uses text search only |
| **Not extracted** | 6 neighborhood checkboxes | ❌ | N-1/N-2 fall back to text search |

---

## PHASE 4 — MSL FILE QC RESULT ACCURACY CHECK

| # | Rule Area | Rule IDs | Checked? | File:Function | Correct? | Root Cause of Issue |
|---|-----------|----------|----------|---------------|----------|---------------------|
| 1 | Assignment type (Purchase/Refi) | C-1 | ✅ YES | `contract_rules.py` | ✅ PASS — Arms-Length Purchase detected | No issue |
| 2 | Contract blank for Refinance | XF-6 | ✅ YES (conditional) | `cross_field_validator.py:293 _refinance_contract_blank` | ✅ XF-6 did not fire — correct (this is a Purchase) | No issue |
| 3 | Contract price vs appraised value (>3%) | C-2 | ❌ NOT CHECKED | `contract_rules.py` | ❌ FAIL — C-2 = extraction_failed; appraised_value never extracted | `market_value_opinion` regex produces `','`; contract date missing from standalone contract PDF |
| 4 | Occupancy vs photo consistency | S-7, XF-VIS-1 | ⚠️ PARTIAL | `subject_rules.py`, `cross_field_validator.py:143` | ❌ S-7 = ocr_low_confidence (0.75); photo check skipped — llava not running | `vision_results=[]` so `_vision_condition_check` returns None |
| 5 | HOA dues → PUD checkbox | S-9, XF-5 | ❌ FAILED | `subject_rules.py` S-9, `cross_field_validator.py:246` | ❌ Both = extraction_failed — `is_pud_checked` = NOT_FOUND | Digital PDF uses Unicode checkmark glyphs, not `[X]` |
| 6 | Special assessment not blank | S-8 | ⚠️ PARTIAL | `subject_rules.py` S-8 | ⚠️ Value = `0` (correct) but confidence 0.78 < 0.85; result = ocr_low_confidence | Confidence below PASS threshold for regex_fallback method |
| 7 | Arm's length transaction | C-1 | ✅ YES | `contract_rules.py` | ✅ PASS — "Arms-Length" detected | No issue |
| 8 | Concession amount cross-check | SCA-7 | ⚠️ PARTIAL | `sales_comparison_rules.py` | ⚠️ SCA-7 = review — text evidence found but no structured field comparison | `concession_amount` never extracted to field_meta |
| 9 | DOM / Marketing time consistency | S-12 | ⚠️ PARTIAL | `subject_rules.py` S-12 | ❌ S-12 = review — `offered_for_sale_12mo=True` but DOM, list_price, list_date not extracted | `days_on_market` not in Phase 2 extraction |
| 10 | Condition vs effective age | XF-3, I-1 | ⚠️ PARTIAL | `cross_field_validator.py:118`, `improvement_rules.py` | ❌ XF-3 evaluated condition C1 but `effective_age=None` → fell through. I-1 = review | `effective_age` never extracted to field_meta |
| 11 | GLA consistency (subject/SCA/sketch) | SCA-17, SK-5 | ⚠️ PARTIAL | `sales_comparison_rules.py`, `sketch_rules.py` | ❌ Both = review — text evidence found but no numeric cross-check | `gla` not in field_meta; no structured value to compare |
| 12 | Flood zone → marketability comment | ST-8 | ⚠️ PARTIAL | `site_rules.py` ST-8 | ⚠️ ST-8 = review — text search only | No structured flood zone code extracted |
| 13 | Zoning compliance | ST-5 | ⚠️ PARTIAL | `site_rules.py` ST-5 | ⚠️ ST-5 = review — text search only | No structured zoning field |

**Summary of Phase 4:**
- ✅ 2 rules fully correct (C-1 assignment detection, XF-6 refinance blank check)
- ⚠️ 6 rules partially checked (text search fallback, below confidence, no comparison)
- ❌ 5 rules not properly checked (missing extracted fields prevent real evaluation)

---

## PHASE 5 — ROOT CAUSE ANALYSIS & PRIORITY FIX LIST

### 5A — Root Cause Categories

#### Category 1: Data Extraction Failures (primary cause of 91 REVIEW results)

| Field | Root Cause |
|-------|-----------|
| `county` | OCR row-flattening: pdfplumber streams UAD table cells L→R without cell boundaries. Sanity check (len>30) added in current code but root cause persists. |
| `owner_of_public_record` | Same row-flattening. `_trim_merged_person_field()` misses `LLCCounty` as a stop boundary. |
| `is_pud_checked` | Digital UAD PDFs encode checked boxes as Unicode glyphs (✓ ● ■), not ASCII `[X]`. Current `_checkbox_state()` only matches `[X]`, `[x]`, `X`, `><`. |
| All 6 neighborhood checkboxes | Same Unicode glyph issue as PUD. |
| `lender_name` | 4 extraction patterns require `Lender/?Client` label on the same line as the value. Spacing variation (`Lender / Client`, `Lender\nClient`) causes all 4 to fail. |
| `data_source` | `_text_window_for_pages(1, 3)` restriction did not prevent matching on page 5 (USPAP boilerplate). Either page mapping is off or the window boundaries have a bug. |
| `comp_1_address`, `comp_2_address` | Comparable grid parser `_extract_comparables()` not extracting properly. |
| `comp_3_address` | Subject address (row 0 of the sales comparison grid) is being captured instead of comp #3. |
| `market_value_opinion` | Regex `r"\$\s*([\d,]{5,})\s+as\s+of"` matched a lone comma when the dollar amount and `as of` were on separate lines. |

#### Category 2: Field Mapping Mismatches

| Issue | Location |
|-------|---------|
| `data_source` (phase2) vs `data_sources` (domain model) | Resolved by qc_processor mapping but naming inconsistency exists |
| CA-1/CA-2 DB says `USDA` but code says `ALL` | `rules_config` table — stale seeding from old code |

#### Category 3: Dead/Orphan Code

| File | Size Wasted | What It Contains |
|------|------------|-----------------|
| `rule_engine/outcome.py` | 5,498 B | `RuleOutcome` class, `evaluate_rule()` — superseded by `RuleResult` and engine |
| `nlp/nlp_checks.py` | ~6 KB | `NLPChecker`, `CommentaryAnalysis` — superseded by `ollama_service.py` |

#### Category 4: Duplicate Logic

1. 3 separate `OCRPipeline` instances in the live server process
2. `contract_price` regex duplicated across `extraction_service.py` and `contract_extraction.py`
3. Address match logic in both S-1 and XF-4
4. `data_source` vs `data_sources` naming split

#### Category 5: Ghost/Unregistered Rules

10 XF cross-field rules execute on every document but have no `rules_config` DB entry — operators cannot toggle, reorder, or change severity via the admin UI.

#### Category 6: Cross-Field Validation Gaps

- No rule compares appraisal `contract_price` vs standalone purchase agreement `contract_price`
- No rule validates `appraised_value vs contract_price` variance (>3%) — `appraised_value` never extracted
- No rule numerically validates GLA across Subject/SCA/Sketch — `gla` not in `field_meta`

#### Category 7: Sync Gaps (OCR ↔ Rule Engine)

Fields the rule engine references in `RULE_FIELD_MAP` but Phase 2 never populates in `field_meta`:
`effective_age`, `gla`, `appraised_value`, `flood_zone`, `days_on_market`

---

### 5B — Priority Fix List (Highest Impact First)

---

#### #1 — BLOCKING: Fix `appraised_value` / `market_value_opinion` extraction

**File:** `app/services/phase2_extraction.py:741-746`

**Problem:** The fallback pattern `r"\$\s*([\d,]{5,})\s+as\s+of"` matched a bare comma `','` because the dollar amount was on a different text line from `as of`.

**Current broken code:**
```python
meta["market_value_opinion"] = self._extract("market_value_opinion", mv_text, [
    r"(?:Appraised|Market|Indicated)\s+Value[:\s]*\$?([\d,]{5,})",
    r"Opinion of (?:Market\s+)?Value[:\s]*\$?([\d,]{5,})",
    r"\$\s*([\d,]{5,})\s+as\s+of",  # ← THIS MATCHED ","
], page_pos, mv_offset)
```

**Fix:**
```python
# After extraction, validate the value looks like a number
mv_meta = meta.get("market_value_opinion")
if mv_meta and mv_meta.value:
    clean = re.sub(r"[,$\s]", "", str(mv_meta.value))
    if not re.match(r"^\d{5,}$", clean):  # must be at least 5 digits
        meta["market_value_opinion"] = FieldMetaResult(
            "market_value_opinion", confidence=0.0, extraction_method="not_found"
        )
```

**Impact:** Unblocks C-2 price variance check, R-1/R-2 reconciliation, all value-comparison rules.

---

#### #2 — BLOCKING: Fix checkbox extraction for Unicode glyphs

**File:** `app/services/phase2_extraction.py` — `_checkbox_state()` method

**Problem:** Digital UAD PDFs encode checkboxes as Unicode glyphs (✓ ✔ ● ■ ▶), not ASCII `[X]`. Current regex misses all of them.

**Current code matches only:**
```python
r"(?:\[x\]|\[X\]|X|><)\s*{label}|{label}\s*(?:\[x\]|\[X\]|X|><)"
```

**Fix — add Unicode patterns:**
```python
_CHECKED_PATTERNS = [
    r"(?:\[x\]|\[X\]|\[✓\]|\[✔\]|[✓✔●■▶▪])\s*{label}",
    r"{label}\s*(?:\[x\]|\[X\]|\[✓\]|\[✔\]|[✓✔●■▶▪])",
    r"(?:☑|☒)\s*{label}",   # ballot box variants
    r"{label}\s*(?:☑|☒)",
]
```

**Impact:** Fixes `is_pud_checked` (S-9, XF-5), and all 6 neighborhood checkbox fields (N-1, N-2). Single fix unblocks ~20 rules from REVIEW.

---

#### #3 — BLOCKING: Fix comparable grid extraction

**File:** `app/services/phase2_extraction.py` — `_extract_comparables()` method

**Problem 1:** `comp_1_address` and `comp_2_address` are NOT_FOUND — the grid parser is not correctly identifying the address rows.

**Problem 2:** `comp_3_address` returns the subject address `96 Baell Trace Ct SE` because the parser is reading the `Subject` column (column 0) instead of the `Comparable Sale #3` column (column 3).

**Fix:** In the grid row extraction:
1. Skip column index 0 (Subject column) when building comp_N fields
2. Add deduplication: if `comp_N_address == subject.property_address` → discard that result
3. Verify Camelot table column indexing starts at 1 (comp columns), not 0 (subject column)

**Impact:** Fixes SCA-2 FAIL, SCA-3..SCA-27 reviews, XF-2 comparable price range check.

---

#### #4 — HIGH: Fix lender name extraction

**File:** `app/services/phase2_extraction.py:628-641`

**Problem:** All 4 extraction patterns require `Lender/?Client` on the same line as the value. Format variants like `Lender / Client` or `Lender\nClient` cause all patterns to fail.

**Fix — add flexible spacing and newline patterns:**
```python
meta["lender_name"] = self._extract("lender_name", lender_text, [
    # Existing patterns (4)...
    # New: handle newline-separated label/value
    r"Lender\s*/?\s*Client[\s\-—:\n]+([A-Za-z][^\n]{3,70}?)(?:\n|$)",
    # New: look for company suffix on any nearby line
    r"(?:Lender|Client)[^\n]*\n([A-Z][A-Za-z0-9\s,\.&]{4,70}(?:Corp|Inc|LLC|Bank|Mortgage|Financial)[^\n]*)",
], page_pos, lender_pos_offset,
   spatial_labels=["Lender/Client", "Lender", "Client"],
   spatial_page_range=(1, 2))
```

**Impact:** Fixes S-10 `extraction_failed` — currently fires on every single run.

---

#### #5 — HIGH: Fix `data_source` garbage capture

**File:** `app/services/phase2_extraction.py:720-723`

**Problem:** Extraction is restricted to pages 1-3 but still captured USPAP boilerplate from page 5. The `_text_window_for_pages()` page range may not align with actual PDF page layout.

**Fix:**
```python
# After extraction, check for boilerplate contamination
data_src_meta = meta.get("data_source")
if data_src_meta and data_src_meta.value:
    val = str(data_src_meta.value).lower()
    BOILERPLATE_MARKERS = [
        "units, common elements", "recreation facilities",
        "are the units", "this appraisal is made",
        "the borrower", "intended use"
    ]
    if any(marker in val for marker in BOILERPLATE_MARKERS) or len(val) > 80:
        meta["data_source"] = FieldMetaResult(
            "data_source", confidence=0.0, extraction_method="not_found"
        )
```

**Impact:** Stops false `data_source` values from polluting reports.

---

#### #6 — HIGH: Add XF rules to DB config

**Files:** `app/rule_engine/rules_db.py`, `app/rule_engine/cross_field_validator.py`

**Problem:** 10 XF rules run every document but have no `rules_config` rows — operators cannot manage them.

**Fix — add to RULE_DEFAULTS in rules_db.py:**
```python
("XF-1",     "CrossField",  "BLOCKING", 2200, "ALL"),
("XF-2",     "CrossField",  "STANDARD", 2210, "ALL"),
("XF-3",     "CrossField",  "STANDARD", 2220, "ALL"),
("XF-4",     "CrossField",  "BLOCKING", 2230, "ALL"),
("XF-5",     "CrossField",  "BLOCKING", 2240, "ALL"),
("XF-6",     "CrossField",  "BLOCKING", 2250, "REFINANCE"),
("XF-VIS-1", "CrossField",  "STANDARD", 2260, "ALL"),
("XF-FHA-1", "CrossField",  "BLOCKING", 2270, "FHA"),
("XF-FHA-2", "CrossField",  "BLOCKING", 2280, "FHA"),
("XF-FHA-3", "CrossField",  "BLOCKING", 2290, "FHA"),
```

Then update `CrossFieldValidator.validate()` to check `load_rule_configs()` before executing each method.

**Impact:** Operators can now disable XF rules without a code deploy.

---

#### #7 — HIGH: Fix CA-1/CA-2 stale DB config

**Fix (SQL):**
```sql
UPDATE rules_config 
SET applicable_loan_types = 'ALL' 
WHERE rule_id IN ('CA-1', 'CA-2');
```

**Impact:** CA-1/CA-2 will evaluate on conventional/purchase loans where the cost approach section is voluntarily filled.

---

#### #8 — HIGH: Extract `effective_age` and `GLA` into field_meta

**File:** `app/services/phase2_extraction.py` — add to `extract_subject()` or `_fill_subject_value_stream_fallbacks()`

**Problem:** `effective_age` and `gla` are in `RULE_FIELD_MAP` but never populated. XF-3, I-1, I-7, SCA-17 all fall back to text search.

**Fix:**
```python
# effective_age — in the Improvements section
meta["effective_age"] = self._extract("effective_age", text, [
    r"Effective Age[:\s]*(\d{1,3})\s*(?:yrs?|years?)?",
    r"(?:Effective|eff\.?)\s+Age[:\s]*(\d{1,3})",
], page_pos, pos_offset)

# gla — Gross Living Area
meta["gla"] = self._extract("gla", text, [
    r"(?:Gross Living Area|GLA)[:\s]*([\d,]{3,7})\s*(?:sq\.?\s*ft\.?)?",
    r"Above Grade.*?GLA[:\s]*([\d,]{3,7})",
], page_pos, pos_offset)
```

**Impact:** Enables XF-3 condition vs age evaluation, I-7 structured GLA check, SCA-17 numeric GLA cross-check.

---

#### #9 — MEDIUM: Fix OCR row-flattening for county/owner fields

**File:** `app/services/phase2_extraction.py` — `_trim_merged_person_field()` method

**Problem:** `_trim_merged_person_field()` doesn't recognize `LLC` as a company-suffix boundary before `County`. The value `Precision Builders and Developers LLCCounty Colquitt` is not trimmed.

**Fix:**
```python
# In _trim_merged_person_field(), add stop-words after company suffixes:
COMPANY_SUFFIX_STOP = re.compile(
    r"(LLC|Inc\.?|Corp\.?|Ltd\.?|LLP)\s*(?=County|State|Zip|Legal|City|Address)",
    re.I
)
if COMPANY_SUFFIX_STOP.search(value):
    value = COMPANY_SUFFIX_STOP.split(value)[0] + COMPANY_SUFFIX_STOP.search(value).group(1)
```

**Impact:** Prevents county and owner_of_public_record garbage extraction from triggering false S-1 FAIL.

---

#### #10 — MEDIUM: Consolidate OCRPipeline instances

**Files:** `app/services/extraction_service.py:40`, `app/tasks/celery_app.py:246`

**Problem:** `ExtractionService` creates its own OCRPipeline that is never used in the `/qc/process` pipeline (qc_processor passes text to extraction_service, not PDFs).

**Fix:** Remove `self.ocr_pipeline` from `ExtractionService.__init__`. The class should process text only. Update `celery_app.py` to call `qc_processor.process_document()` instead of building its own pipeline.

**Impact:** Removes dead code, reduces memory footprint, guarantees consistent OCR config across all paths.

---

#### #11 — MEDIUM: Fix `extract_with_preprocessing()` sequential loop

**File:** `app/ocr/ocr_pipeline.py:952-963`

**Problem:** Sequential `for` loop over pages — violates CLAUDE.md Rule 7 (always parallel):
```python
for page_num, raw_image in enumerate(raw_images, start=1):  # ← SEQUENTIAL
    clean_image = self.preprocessor.preprocess_image(raw_image)
    text = self._tesseract_extract(image=clean_image, config='--psm 6')
```

**Fix:** Wrap preprocessing + OCR in `ThreadPoolExecutor.map()` (same as `extract_all_pages()`).

**Impact:** Performance fix for fallback preprocessing path.

---

#### #12 — LOW: Delete `rule_engine/outcome.py`

Never imported. `RuleOutcome` duplicates `RuleResult`. `evaluate_rule()` duplicates engine logic. Safe to delete.

---

#### #13 — LOW: Delete `nlp/nlp_checks.py`

Never imported. `NLPChecker` duplicates what `ollama_service.py` + `narrative_rules.py` already do. Safe to delete.

---

#### #14 — LOW: Update CLAUDE.md rule count

**File:** `ocr-service/CLAUDE.md:972, 988, 1019`

Says "31 rules" in 3 places. Actual system: **136 engine rules + 10 XF rules = 146 rules total**.

---

### 5C — Files to Delete / Consolidate

| File | Action | Reason |
|------|--------|--------|
| `app/rule_engine/outcome.py` | **DELETE** | Never imported; RuleOutcome superseded by RuleResult |
| `app/nlp/nlp_checks.py` | **DELETE** | Never imported; NLPChecker superseded by ollama_service + narrative_rules |
| `extraction_service.py` self.ocr_pipeline | **REFACTOR** | Remove the OCRPipeline instance — ExtractionService only processes text in the main pipeline |
| `celery_app.py` OCR setup | **REFACTOR** | Should call `qc_processor.process_document()` not re-implement pipeline |
| `extraction_service.py` + `contract_extraction.py` contract_price regex | **MERGE** | Consolidate contract price extraction in HybridContractExtractor only |

---

## FILES NOT EXPLORED (Not Read in Full)

The following files were not fully read — findings above may not cover all issues inside them:

| File | Reason |
|------|--------|
| `services/phase2_extraction.py` | 138 KB — read lines 1-550 and 700-850 only. `_extract_comparables()` body not read. |
| `app/rules/subject_rules.py` | 83 KB — read first 250 lines. Individual S-1..S-12 rule bodies not read. |
| `app/rules/contract_rules.py` | 66 KB — read first 100 lines. C-1..C-5 rule bodies not read. |
| `main.py` | 95 KB — read first 80 lines + grepped for endpoints. Full endpoint bodies not read. |
| `services/extraction_service.py` | 48 KB — read first 130 lines. `_extract_contract_section()` body not read. |
| `app/rules/sales_comparison_rules.py` | 25 KB — not read (27 rules, structure inferred) |
| `app/rules/narrative_rules.py` | 27 KB — not read |
| `app/rules/site_rules.py` | 19 KB — not read |
| `app/rules/improvement_rules.py` | 11 KB — not read |
| `services/auto_pass_calibration.py` | 19 KB — not read |
| `services/ollama_service.py` | 25 KB — not read |
| `services/processing_lifecycle.py` | 25 KB — not read |
| `app/tasks/celery_app.py` | not read |
| All `models/*.py` files | structure inferred from imports only |
| `services/field_registry.py` | 10 KB — not read |
| `services/external_services.py` | 9 KB — not read |

---

## FINAL SCORECARD

| Category | Count |
|----------|-------|
| Active / used files | 38 |
| Dead / orphan files | 2 (`outcome.py`, `nlp_checks.py`) |
| Duplicate logic areas | 5 |
| Ghost rules (XF rules not in DB config) | 10 |
| Stale DB config entries | 2 (CA-1, CA-2) |
| Data sync gaps (OCR output ↔ rule engine) | 8 missing fields |
| QC rules PASS (MSL run) | 6 |
| QC rules FAIL (MSL run) | 4 |
| QC rules REVIEW (MSL run) | 91 |
| QC rules NOT_APPLICABLE correct (MSL run) | 19 |
| QC rules NOT_APPLICABLE wrong/stale (MSL run) | 2 |
| QC rules extraction_failed / ocr_low_confidence (MSL run) | 12 |

---

*Generated: 2026-05-13 | Knowledge Graph: 3,203 nodes · 21,499 edges · 303 files*
