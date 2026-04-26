# CLAUDE.md — Appraisal QC Platform

> This file is read by Claude Code on every session. It tells Claude exactly how this project works,
> what tools to use, what never to do, and how to think about every decision.
> Keep this file updated as the project evolves.

---

## Project Identity

**What this is:** A production appraisal quality control platform. It ingests appraisal PDFs,
engagement letters, and purchase contracts — extracts structured fields — runs 21 categories
of compliance rules — and flags issues for human review. The system self-learns from operator
corrections over time.

**Who uses it:** Appraisal review operators. Not developers. Results must be clear, sourced,
and explainable. Every FAIL must show exactly what the system found and where.

**Deployment:** Single VPS running Docker. FastAPI backend on port 5001. Next.js frontend
on port 3000. PostgreSQL on port 5432. Redis on port 6379. Ollama on port 11434 (local).

**Live test document:** `96 Baell Trace Ct SE.pdf` — 27 pages, Colquitt County GA, UAD 1004 form.
Use this as the reference document for testing any new feature.

---

## Repository Layout

```
appraisal-qc/
├── CLAUDE.md                        ← YOU ARE HERE
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── routes/
│   │   │   │   ├── qc.py            ← /qc/process, /qc/feedback, /qc/batch
│   │   │   │   ├── admin.py         ← /admin/rules, /admin/models
│   │   │   │   └── health.py        ← /health
│   │   │   └── deps.py              ← shared FastAPI dependencies (auth, db session)
│   │   ├── services/
│   │   │   ├── ocr/
│   │   │   │   ├── ocr_pipeline.py       ← main OCR orchestrator
│   │   │   │   ├── image_preprocessor.py ← OpenCV preprocessing (5-step pipeline)
│   │   │   │   └── checkbox_detector.py  ← OpenCV + moondream2 checkbox logic
│   │   │   ├── extraction/
│   │   │   │   ├── extraction_service.py ← field extraction coordinator
│   │   │   │   ├── subject_extractor.py
│   │   │   │   ├── contract_extractor.py
│   │   │   │   ├── neighborhood_extractor.py
│   │   │   │   ├── site_extractor.py
│   │   │   │   ├── improvement_extractor.py
│   │   │   │   ├── sales_comparison_extractor.py
│   │   │   │   ├── reconciliation_extractor.py
│   │   │   │   └── field_corrector.py    ← OCR error correction (dict + ML)
│   │   │   ├── rules/
│   │   │   │   ├── engine.py             ← rule runner, ordering, isolation
│   │   │   │   ├── subject_rules.py      ← S-1 through S-12
│   │   │   │   ├── contract_rules.py     ← C-1 through C-10
│   │   │   │   ├── neighborhood_rules.py ← N-1 through N-7
│   │   │   │   ├── site_rules.py
│   │   │   │   ├── improvement_rules.py
│   │   │   │   ├── sales_comparison_rules.py
│   │   │   │   ├── reconciliation_rules.py
│   │   │   │   ├── cost_approach_rules.py
│   │   │   │   ├── income_approach_rules.py
│   │   │   │   ├── addendum_rules.py
│   │   │   │   ├── photo_rules.py
│   │   │   │   ├── floorplan_rules.py
│   │   │   │   ├── maps_rules.py
│   │   │   │   ├── additional_docs_rules.py
│   │   │   │   ├── fha_rules.py
│   │   │   │   ├── usda_rules.py
│   │   │   │   ├── multifamily_rules.py
│   │   │   │   └── signature_rules.py
│   │   │   ├── llm/
│   │   │   │   ├── llm_service.py        ← Ollama client + fallback chain
│   │   │   │   ├── commentary_analyzer.py← canned vs specific, market quality
│   │   │   │   └── prompts.py            ← all LLM prompts in one place
│   │   │   └── ml/
│   │   │       ├── correction_model.py   ← OCR correction classifier
│   │   │       ├── confidence_model.py   ← field confidence scorer
│   │   │       ├── commentary_classifier.py ← canned text classifier
│   │   │       └── trainer.py            ← weekly retraining job
│   │   ├── models/
│   │   │   ├── document.py
│   │   │   ├── job.py
│   │   │   ├── rule_result.py
│   │   │   ├── extracted_field.py
│   │   │   ├── feedback_event.py
│   │   │   └── training_example.py
│   │   ├── schemas/                      ← Pydantic request/response shapes
│   │   │   ├── qc_request.py
│   │   │   └── qc_response.py
│   │   └── core/
│   │       ├── config.py                 ← all settings from env vars
│   │       ├── logging.py                ← structured JSON logging + request_id
│   │       ├── exceptions.py             ← custom exception hierarchy
│   │       └── security.py              ← API key check middleware
│   ├── alembic/                          ← database migrations (never edit manually)
│   ├── tests/
│   │   ├── fixtures/                     ← real PDFs for testing (gitignored)
│   │   ├── test_ocr.py
│   │   ├── test_extraction.py
│   │   ├── test_rules.py
│   │   └── test_api.py
│   └── requirements.txt
├── frontend/
│   ├── app/
│   │   ├── page.tsx                      ← upload screen
│   │   ├── results/[jobId]/page.tsx      ← results dashboard
│   │   └── admin/page.tsx               ← rule management
│   ├── components/
│   │   ├── UploadZone.tsx
│   │   ├── ResultsDashboard.tsx
│   │   ├── RuleDetailPanel.tsx           ← the most important UI component
│   │   ├── FeedbackForm.tsx
│   │   ├── PDFViewer.tsx
│   │   └── ConfidenceBar.tsx
│   └── package.json
├── ml/
│   ├── data/                             ← training data (gitignored)
│   └── notebooks/                        ← experimentation only, never production code
├── docker/
│   ├── docker-compose.yml
│   ├── Dockerfile.backend
│   └── Dockerfile.frontend
└── scripts/
    ├── retrain.py                        ← run manually or via cron: Sunday nights
    └── seed_rules.py                     ← populate rules table from scratch
```

---

## How to Run Everything

```bash
# Start all services
docker-compose up -d

# Backend only (development)
cd backend
uvicorn app.main:app --reload --port 5001

# Frontend only (development)
cd frontend
npm run dev

# Run all tests
cd backend && pytest tests/ -v

# Run retraining manually
python scripts/retrain.py

# Check Ollama models available
curl http://localhost:11434/api/tags

# Pull moondream for checkbox detection (if not already pulled)
ollama pull moondream
```

---

## Environment Variables

All secrets live in `.env` (never committed to git). Claude Code must never hardcode any of these.

```bash
# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/appraisal_qc

# Redis
REDIS_URL=redis://localhost:6379

# Ollama (local — no API key needed)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_LLM_MODEL=llama3:8b-instruct-q4_0
OLLAMA_VISION_MODEL=moondream

# Security
API_KEY=<generated on deploy>
ALLOWED_ORIGINS=http://localhost:3000

# Processing limits
MAX_FILE_SIZE_MB=50
MAX_PAGES=100
OCR_WORKERS=4

# OCR
TESSERACT_PATH=/opt/homebrew/bin/tesseract
OCR_DPI=300
MIN_WORDS_THRESHOLD=100
```

---

## The Most Critical Rules for Claude Code to Follow

### Rule 1 — Never Use LLM for Structured Field Extraction

LLM (Ollama/llama3) must NEVER be used to extract structured fields from appraisal text.
Fields like address, borrower name, contract price, dates — always use regex + spatial anchoring.

LLM is ONLY allowed for:
- Commentary quality analysis (canned vs specific)
- Market conditions narrative quality
- Reconciliation sufficiency evaluation

If Claude Code suggests using LLM to extract a field, that is wrong. Correct it.

### Rule 2 — Checkbox Detection Uses OpenCV First, moondream2 Second

Never call moondream2 for a checkbox unless OpenCV pixel analysis returned confidence < 75%.
Do not call any external API (Claude API, GPT) for checkbox detection — moondream2 is local and free.

The checkbox_detector.py must always follow this exact order:
1. OpenCV pixel analysis (0ms, always runs first)
2. moondream2 via Ollama only if step 1 is uncertain
3. Result cached by `document_id + page_number + checkbox_bbox`

### Rule 3 — Every Extracted Field Must Have These Four Properties Populated

When extraction_service.py extracts any field, all four must be set. Never leave them as defaults:
- `confidence_score` (float 0.0–1.0) — never leave as 0.0
- `source_page` (int) — which page of the PDF did this come from
- `extraction_method` (enum: EMBEDDED / TESSERACT / ML_CORRECTED)
- `raw_ocr_text` (str) — what OCR literally produced before any correction

This data feeds the ML training loop. Missing it means the model cannot learn.

### Rule 4 — Rules Must Never Crash the Whole Pipeline

Every rule function is wrapped in try/except. If one rule raises any exception:
- That rule returns `status=SYSTEM_ERROR`
- All other rules continue running
- The error is logged with rule_id and request_id
- The response still returns with all other rule results

The rule engine in engine.py enforces this. Do not write rule functions that can propagate exceptions.

### Rule 5 — Address Parsing Must Use Data Patterns, Not Label Words

The zip code parser must find the 5-digit number pattern, not search for the word "Code".
OCR mangles label words ("aP Code", "Zip Gode") but rarely mangles the actual 5-digit zip.

Correct approach:
1. Find 5-digit number at end of address block → zip code
2. Find 2-letter uppercase before it → state
3. Find text between "City" anchor and the state → city
4. Find text before "City" anchor → street

Never write a regex that depends on the word "Code" or "Zip" appearing correctly.

### Rule 6 — Raw OCR Text Must Be Saved to Database

After every OCR operation, `per_page_ocr_results` row must be inserted with raw_text column populated.
This is the training signal for the correction ML model.
Do not skip this to save time or because the text seems unimportant.

### Rule 7 — Parallel Page Processing Always Uses ThreadPoolExecutor

OCR processes pages with `ThreadPoolExecutor(max_workers=OCR_WORKERS)` — never sequentially.
The `OCR_WORKERS` env var defaults to 4. This is already in config. Wire it in everywhere.
Sequential page processing is a regression. If you see a for loop over pages in OCR code, fix it.

### Rule 8 — File Hash Before OCR, Always

Before running OCR on any uploaded PDF:
1. Compute SHA-256 hash of the file bytes
2. Check `documents` table for existing hash
3. If found: return cached extraction result — do not re-run OCR
4. If not found: run OCR, then save hash + results to database

This prevents paying 14 seconds of OCR on retry requests.

### Rule 9 — LLM Calls Must Always Have a Fallback

Every call to Ollama LLM must have a fallback that activates on:
- Timeout (> 30 seconds)
- Connection refused
- Invalid/unexpected response format
- Empty response

The fallback for commentary analysis is keyword-based matching in `prompts.py`.
The pipeline must never return a 500 error because Ollama is down.

### Rule 10 — Feedback Must Be Stored With Full Context

Every operator correction stored in `feedback_events` must include:
- `original_ocr_text` — what OCR produced
- `system_extracted_value` — what extraction produced from OCR
- `operator_provided_value` — what the operator says is correct
- `rule_id` — which rule was involved
- `source_page` — which page the field came from

Missing any of these makes the training example useless for the ML model.

---

## Rule Categories and File Ownership

| Section | Rule IDs | File | Status |
|---------|----------|------|--------|
| Subject | S-1 to S-12 | subject_rules.py | Phase 3 |
| Contract | C-1 to C-10 | contract_rules.py | Phase 3 |
| Neighborhood | N-1 to N-7 | neighborhood_rules.py | Phase 3 |
| Site | SI-1 to SI-8 | site_rules.py | Phase 3 |
| Improvements | IM-1 to IM-10 | improvement_rules.py | Phase 3 |
| Sales Comparison | SC-1 to SC-15 | sales_comparison_rules.py | Phase 3 |
| Reconciliation | R-1 to R-5 | reconciliation_rules.py | Phase 3 |
| Cost Approach | CA-1 to CA-6 | cost_approach_rules.py | Post-V1 |
| Income Approach | IA-1 to IA-4 | income_approach_rules.py | Post-V1 |
| Addendum/Commentary | AC-1 to AC-8 | addendum_rules.py | Phase 4 |
| Photographs | PH-1 to PH-6 | photo_rules.py | Post-V1 |
| Floor Plan Sketch | FP-1 to FP-5 | floorplan_rules.py | Post-V1 |
| Maps | MP-1 to MP-4 | maps_rules.py | Post-V1 |
| Additional Docs | AD-1 to AD-5 | additional_docs_rules.py | Post-V1 |
| FHA Requirements | FH-1 to FH-12 | fha_rules.py | Post-V1 |
| USDA Requirements | US-1 to US-8 | usda_rules.py | Post-V1 |
| Multi-Family | MF-1 to MF-10 | multifamily_rules.py | Post-V1 |
| Signature | SG-1 to SG-4 | signature_rules.py | Phase 3 |

**Phase 3 (28-day target):** Subject, Contract, Neighborhood, Site, Improvements, Sales Comparison, Reconciliation, Signature.
**Post-V1:** Everything else. Architecture must support adding them as plugins without restructuring engine.py.

---

## Rule Result Schema

Every rule must return exactly this structure. No exceptions.

```python
{
    "rule_id": "S-1",
    "rule_name": "Property Address Match",
    "status": "FAIL",           # PASS | FAIL | VERIFY | WARNING | SKIPPED | SYSTEM_ERROR
    "severity": "BLOCKING",     # BLOCKING | STANDARD | ADVISORY
    "message": "Address in appraisal report does not match engagement letter",
    "detail": "Report: '96 Baell Trace Ct SE' | Order: '96 Bell Trace Ct SE'",
    "appraisal_value": "96 Baell Trace Ct SE",
    "reference_value": "96 Bell Trace Ct SE",
    "source_page": 1,
    "confidence": 0.82,
    "action_required": "Confirm correct address with appraiser. OCR may have misread street name.",
    "auto_correctable": False,
    "rule_version": "1.0.0"
}
```

Never return partial structures. Every key must be present. Missing values use `null`, not absent keys.

---

## OCR Decision Logic (The Most Important Flow)

```
For each PDF page:

    Step 1: Try PyMuPDF embedded text
        word_count = count words in page.get_text("text")

        if word_count >= 100:
            use embedded text
            method = EMBEDDED
            confidence = HIGH
            skip OCR entirely

        elif 30 <= word_count < 100:
            run OCR in parallel (do not wait for it)
            compare embedded vs OCR word count
            use whichever gives more clean words
            method = HYBRID

        else:  # word_count < 30
            must OCR — page is image-heavy (photos, maps, signatures)
            run full 5-step preprocessing first
            method = TESSERACT

    Step 2: Full preprocessing before Tesseract (always, for any page going to OCR)
        1. Grayscale conversion
        2. Denoising (fastNlMeansDenoising)
        3. Otsu threshold → pure black/white
        4. Table grid line removal (horizontal + vertical kernels)
        5. Deskew if abs(angle) > 0.5°

    Step 3: Tesseract config
        config = '--psm 6'   # uniform text block
        # Do NOT change psm without testing on real documents first

    Step 4: Store result
        Insert row into per_page_ocr_results with all fields populated
```

---

## Checkbox Detection Logic

```
For each checkbox on the form:

    Step 1: OpenCV pixel analysis
        crop = page_image[bbox_y:bbox_y+h, bbox_x:bbox_x+w]
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        dark_pixel_ratio = (gray < 128).sum() / gray.size

        if dark_pixel_ratio > 0.40:
            return CHECKED, confidence=0.90
        elif dark_pixel_ratio < 0.15:
            return UNCHECKED, confidence=0.90
        else:
            # Ambiguous — go to step 2

    Step 2: moondream2 via Ollama (only if step 1 uncertain)
        Check cache first: key = f"{doc_id}:{page}:{bbox}"
        If cache hit: return cached result

        response = ollama.generate(
            model="moondream",
            prompt="Is the checkbox in this image marked with a check or X? Answer YES or NO only.",
            images=[base64_encoded_crop]
        )

        parse "YES" or "NO" from response
        store in cache
        return result with confidence=0.88

    Step 3: If both steps uncertain (rare — <2% of cases)
        return status=VERIFY
        flag for human review in results
```

**Never call any external API (Anthropic, OpenAI) for checkbox detection. moondream2 is local.**

---

## LLM Integration — Ollama Only

All LLM calls go through `llm_service.py`. Nothing calls Ollama directly from rule files.

```
LLM is allowed for:
    - Commentary quality: "Is this text canned or specific to this property?"
    - Market conditions quality: "Does this narrative contain actual market data?"
    - Reconciliation sufficiency: "Does this explain why the final value was chosen?"

LLM is NOT allowed for:
    - Field extraction (use regex)
    - Field validation (use rules engine)
    - Checkbox detection (use OpenCV + moondream)
    - Document classification (use keyword matching)
    - Anything where a simpler tool works
```

**Ollama models in use:**

| Purpose | Model | Max input |
|---------|-------|-----------|
| Commentary analysis | llama3:8b-instruct-q4_0 | 800 chars |
| Checkbox detection | moondream | 100×100px crop |

**LLM call settings — never change without documenting why:**
- Temperature: 0.0 (deterministic — same input must give same output)
- Max tokens: 10 for binary, 256 for JSON responses
- Timeout: 30 seconds — fallback activates after this

---

## Database — Important Notes

**ORM:** SQLAlchemy with async sessions.
**Migrations:** Alembic only. Never run `ALTER TABLE` manually in production.
**Never drop a column** without a migration that first makes it nullable.

**Key tables:**

```sql
documents           -- one row per uploaded file set (appraisal + engagement + contract)
processing_jobs     -- tracks pipeline stage per document
per_page_ocr_results-- one row per page, stores raw_text (critical for ML)
extracted_fields    -- one row per extracted field per document
rule_results        -- one row per rule per document
feedback_events     -- operator corrections (ML training source)
training_examples   -- processed feedback ready for model training
rules_config        -- active rules, severity, loan type applicability
```

**Index requirements** — these must exist or queries will be slow:
```sql
CREATE INDEX idx_documents_hash ON documents(file_hash);
CREATE INDEX idx_feedback_untrained ON feedback_events(used_in_training) WHERE used_in_training = false;
CREATE INDEX idx_rule_results_document ON rule_results(document_id);
CREATE INDEX idx_ocr_results_document ON per_page_ocr_results(document_id);
```

---

## API Endpoints

| Method | Path | What It Does |
|--------|------|-------------|
| GET | /health | Returns service status and Ollama connectivity |
| POST | /qc/process | Main endpoint — accepts 3 PDFs, returns full QC results |
| POST | /qc/feedback | Operator submits correction on a rule result |
| GET | /qc/results/{job_id} | Poll for async job status |
| GET | /admin/rules | List all rules and their active/inactive status |
| PATCH | /admin/rules/{rule_id} | Toggle rule active/inactive |
| POST | /admin/retrain | Trigger manual model retraining |

**Authentication:** Every endpoint except /health requires `X-API-Key` header.
CORS: Only allow `ALLOWED_ORIGINS` from env var. Never `allow_origins=["*"]` in production.

---

## Testing Standards

Every new rule or extractor must have tests against real documents before being considered done.

**The 3 real test documents (in `tests/fixtures/` — gitignored):**
- `96_baell_trace_ct_se/` — appraisal.pdf + engagement.pdf + contract.pdf
- `2307_merrily_cir_n/` — same structure
- `8234_e_pearson/` — same structure

**Test a rule is done when:**
- It produces correct result on all 3 test documents
- It produces VERIFY (not crash) when a required field is missing
- It handles SYSTEM_ERROR correctly (rule crashes but others continue)
- Processing time for the rule alone is under 200ms (excluding LLM calls)

**LLM-dependent rules additionally must:**
- Produce correct result when Ollama is down (fallback path tested)
- Return same result on identical input (temperature 0.0 verified)

---

## Common Mistakes to Avoid

**Do not do these things. If Claude Code suggests them, refuse.**

1. `force_image_ocr=True` on all pages — use hybrid mode with the decision tree above
2. Processing pages in a sequential for loop — always use ThreadPoolExecutor
3. Discarding raw OCR text after extraction — always save it to per_page_ocr_results
4. Leaving `confidence_score=0.0` on extracted fields — always compute and store it
5. Calling Ollama for field extraction — only regex and spatial patterns
6. Using `allow_origins=["*"]` — always use the env var
7. Hardcoding any secret, path, or URL — always use env vars via config.py
8. Writing a rule that can raise an uncaught exception — always wrap in try/except
9. Searching for "Zip Code" literally — search for 5-digit pattern instead
10. Calling moondream for a checkbox without checking OpenCV result first
11. Calling any external API for checkbox detection (Anthropic, OpenAI)
12. Running OCR on a page with 100+ embedded words — use PyMuPDF directly

---

## When Things Go Wrong

**OCR quality is poor on a specific page:**
- Check: was the full 5-step preprocessing applied?
- Check: was DPI=300 used?
- Check: is the page flagged as `has_tables=True`? Table grid lines must be removed before OCR.
- Last resort: check page confidence score in per_page_ocr_results — if < 0.5, flag for human review

**A rule is consistently VERIFY when it should PASS:**
- The field it depends on is probably not being extracted correctly
- Check extracted_fields table for that document — is the value there?
- If value is NULL: fix the extractor for that field first, then retest the rule
- Check source_page — is the extractor looking at the right page?

**moondream2 gives wrong checkbox answers:**
- Run `ollama pull moondream` to ensure you have the latest version
- Check that the crop sent to moondream is at least 50×50 pixels
- Check that full preprocessing was applied to the page image before cropping
- If consistently wrong on one document: that document has unusual checkbox style — add to test fixtures

**Processing time exceeds 20 seconds:**
- Check: is ThreadPoolExecutor actually being used? (check logs for parallel page messages)
- Check: is OCR cache working? (second upload of same file should be <1 second)
- Check: how many LLM calls are in the pipeline? Each adds 2–5 seconds. Batch them.
- Check: is force_image_ocr being applied to pages with plenty of embedded text?

---

## ML Model — What Each Model Does

All models live in `backend/app/services/ml/`. Never run training inline in a request.
Training only happens in `scripts/retrain.py` which runs as a background job.

| Model | File | Input | Output | Retrain frequency |
|-------|------|-------|--------|------------------|
| OCR corrector | correction_model.py | Raw OCR character sequence | Corrected text | Weekly |
| Field confidence | confidence_model.py | Extraction features | 0.0–1.0 score | Weekly |
| Commentary classifier | commentary_classifier.py | Text snippet | CANNED / SPECIFIC | Monthly |

**Until enough training data exists (<50 examples per model), use rule-based fallbacks:**
- OCR corrector → correction dictionary in `field_corrector.py`
- Field confidence → heuristic scoring in `extraction_service.py`
- Commentary classifier → keyword list in `prompts.py`

**Never deploy a new model version that has lower accuracy than the current one.**
Always store previous model version so you can roll back.

---

## Phase Completion Status

Update this section as phases are completed.

| Phase | Description | Status | Completed |
|-------|-------------|--------|-----------|
| 0 | Foundation, Docker, DB setup | ⬜ Not started | — |
| 1 | Smart OCR pipeline with caching | ⬜ Not started | — |
| 2 | Field extraction engine | ⬜ Not started | — |
| 3 | Rule engine (8 core sections) | ⬜ Not started | — |
| 4 | LLM commentary analysis | ⬜ Not started | — |
| 5 | Operator UI | ⬜ Not started | — |
| 6 | Feedback & ML learning loop | ⬜ Not started | — |
| 7 | Production deploy | ⬜ Not started | — |

**Do not mark a phase complete until its achievement gate is fully passed.**
Achievement gates are defined in `docs/build_plan.md`.

---

## Known Issues (From Live System Analysis — Fix in Order)

| Priority | Issue | Fix location |
|----------|-------|-------------|
| 🔴 HIGH | Zip code parser fails on "aP Code" OCR noise | subject_extractor.py — use 5-digit pattern |
| 🔴 HIGH | force_image_ocr=True on all pages wastes 30s | ocr_pipeline.py — implement hybrid decision |
| 🔴 HIGH | Raw OCR text not saved to database | ocr_pipeline.py — insert per_page_ocr_results row |
| 🔴 HIGH | confidence_score always 0.0 on extracted fields | extraction_service.py — compute and set it |
| 🔴 HIGH | source_page always null on extracted fields | extraction_service.py — track and set it |
| 🟡 MED | Pages processed sequentially not in parallel | ocr_pipeline.py — wire in ThreadPoolExecutor |
| 🟡 MED | No OCR caching by file hash | ocr_pipeline.py — add hash check before OCR |
| 🟡 MED | Full preprocessing not used by /qc/process | ocr_pipeline.py — unify both paths |
| 🟡 MED | Checkbox detection reads text only, misses visual marks | checkbox_detector.py — OpenCV + moondream |
| 🟢 LOW | CORS allow_origins is wildcard | main.py — restrict to env var |
| 🟢 LOW | No API key auth on endpoints | security.py — add X-API-Key middleware |

---

*Last updated: 2026-04-25*
*System: FastAPI port 5001 | Next.js port 3000 | PostgreSQL | Redis | Ollama (local)*
*Reference document: 96 Baell Trace Ct SE.pdf — 27 pages — UAD 1004 — Colquitt County GA*# CLAUDE.md — Appraisal QC Platform

> This file is read by Claude Code on every session. It tells Claude exactly how this project works,
> what tools to use, what never to do, and how to think about every decision.
> Keep this file updated as the project evolves.

---

## Project Identity

**What this is:** A production appraisal quality control platform. It ingests appraisal PDFs,
engagement letters, and purchase contracts — extracts structured fields — runs 31 compliance
rules — and flags issues for human review. The system self-learns from operator corrections.

**Who uses it:** Appraisal review operators. Not developers. Results must be clear, sourced,
and explainable. Every FAIL must show exactly what the system found and where.

**Deployment:** Local Mac (dev). FastAPI backend on port 5001. Next.js frontend on port 3000.
PostgreSQL@18 (Homebrew) on port 5432. Redis (Homebrew) on port 6379. Ollama on port 11434.

**Live test documents:**
- `96 Baell Trace Ct SE.pdf` — 27 pages, Colquitt County GA, UAD 1004 form
- `2307 Merrily Cir N.pdf` — 37 pages, Hillsborough County FL
- `8234 E Pearson.pdf` — 33 pages, Macomb County MI

---

## Repository Layout (Actual — ocr-service/)

```
ocr-service/
├── CLAUDE.md                        ← YOU ARE HERE
├── main.py                          ← FastAPI app, all endpoints
├── app/
│   ├── config.py                    ← env vars, binary paths, limits
│   ├── database.py                  ← SQLAlchemy engine + session
│   ├── logging_config.py
│   ├── qc_processor.py              ← orchestrates full QC pipeline
│   ├── models/
│   │   ├── appraisal.py             ← Pydantic domain models (ValidationContext etc.)
│   │   ├── db_models.py             ← SQLAlchemy ORM models (all 9 DB tables)
│   │   ├── difference_report.py     ← SubjectSectionExtract, ContractSectionExtract
│   │   └── field_meta.py            ← FieldMetaResult (value + confidence + source_page)
│   ├── ocr/
│   │   ├── ocr_pipeline.py          ← parallel page OCR (ThreadPoolExecutor, 4 workers)
│   │   └── image_preprocessor.py   ← 5-step OpenCV pipeline (gray→denoise→Otsu→grid→deskew)
│   ├── services/
│   │   ├── phase2_extraction.py     ← Phase 2 field extraction (spatial anchor + OCR correction)
│   │   ├── extraction_service.py    ← engagement letter + contract extraction
│   │   ├── ocr_correction.py        ← 51-pattern OCR error correction dictionary
│   │   ├── cache_service.py         ← SHA-256 OCR cache (page_ocr_results table)
│   │   ├── ollama_service.py        ← LLM calls: classify_commentary, analyze_market
│   │   └── llm_cache.py             ← LLM response cache (llm_response_cache table)
│   ├── rule_engine/
│   │   ├── engine.py                ← rule runner: DB config, ordering, isolation
│   │   ├── rules_db.py              ← seed + load rule configs (is_active, severity, order)
│   │   └── smart_identifier.py     ← RuleResult, RuleStatus, RuleSeverity, DataMissingException
│   ├── rules/
│   │   ├── __init__.py              ← imports: subject → contract → neighborhood → narrative
│   │   ├── subject_rules.py         ← S-1 to S-12
│   │   ├── contract_rules.py        ← C-1 to C-5
│   │   ├── neighborhood_rules.py    ← N-1 to N-7 (structural completeness)
│   │   └── narrative_rules.py       ← COM-1 to COM-7 (LLM commentary quality)
│   ├── extraction/
│   │   └── normalizers.py
│   ├── nlp/
│   │   └── nlp_checks.py            ← NLPChecker: tier1=ollama, tier2=embeddings, tier3=keywords
│   └── tasks/
│       └── celery_app.py            ← Celery worker for async processing
├── alembic/                         ← DB migrations (never edit manually)
├── training/
│   ├── train_nlp.py                 ← sklearn + ollama auto-labelling
│   └── data_loader.py
├── frontend/                        ← Next.js 16 + shadcn/ui + Tailwind
│   ├── app/page.tsx                 ← root: routes between Upload/Results/Detail screens
│   └── components/
│       ├── UploadScreen.tsx         ← 3-file drag-drop, progress bar, "Run QC" button
│       ├── ResultsDashboard.tsx     ← FAIL/VERIFY/PASS sections, confidence bars
│       └── RuleDetailView.tsx       ← side-by-side comparison + feedback form
├── uploads/EQSS/xBatch/             ← test PDFs (appraisal/ + eagagement/ + contract/)
└── docker-compose.yml               ← postgres + redis for Docker environments
```

---

## How to Run Everything

```bash
# Start all services (Homebrew on Mac)
brew services start postgresql@18
brew services start redis
ollama serve &

# Backend (development)
cd ocr-service
conda activate apprisal
uvicorn main:app --port 5001 --reload

# Frontend (development)
cd frontend
npm run dev   # → http://localhost:3000

# Pull vision model for checkbox detection
ollama pull moondream

# Apply DB migrations
alembic upgrade head

# Check Ollama models
curl http://localhost:11434/api/tags | python3 -m json.tool
```

---

## Environment Variables

All secrets live in env vars. Never hardcode any of these.

```bash
DATABASE_URL=postgresql://qc_user:qc_password@localhost:5432/appraisal_qc
REDIS_URL=redis://localhost:6379/0
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_LLM_MODEL=llama3:8b-instruct-q4_0
OLLAMA_VISION_MODEL=moondream
MAX_FILE_SIZE_BYTES=52428800   # 50 MB
MAX_PAGE_COUNT=100
TESSERACT_CMD=/opt/homebrew/bin/tesseract
OCR_DPI=300
MIN_WORDS_THRESHOLD=100
```

---

## The Most Critical Rules for Claude Code to Follow

### Rule 1 — Never Use LLM for Structured Field Extraction

LLM (Ollama/llama3) must NEVER be used to extract structured fields from appraisal text.
Fields like address, borrower name, contract price, dates — always use regex + spatial anchoring
in `app/services/phase2_extraction.py`.

LLM is ONLY allowed for:
- Commentary quality analysis (canned vs specific) — COM-1, COM-2, COM-5
- Market conditions narrative quality — COM-2
- Reconciliation sufficiency evaluation — COM-5

### Rule 2 — Checkbox Detection: Three-State Logic

Checkboxes in OCR text come in three states. Handle all three:

```python
# [X] or [x] near label → CHECKED (YES, applies) → True
# [ ] near label         → UNCHECKED (NO, explicitly not selected) → False
# Nothing found          → UNKNOWN (OCR couldn't read) → None → VERIFY

def _checkbox_state(text, label) -> Optional[bool]:
    if re.search(r"(?:\[x\]|\[X\]|X|><)\s*{label}|{label}\s*(?:\[x\]|\[X\]|X|><)", text, re.I):
        return True   # [X] = YES, proceed with this rule
    if re.search(r"\[\s\]\s*{label}|{label}\s*\[\s\]", text, re.I):
        return False  # [ ] = NO, skip this rule
    return None       # not found = VERIFY
```

**NEVER return FAIL from None checkbox — always VERIFY.**
**NEVER confuse `[ ]` (explicit NO) with not-found (UNKNOWN).**

### Rule 3 — Every Extracted Field Must Have Four Properties

When `phase2_extraction.py` extracts any field, all four must be populated:
- `confidence_score` (float 0.0–1.0)
- `source_page` (int — which PDF page)
- `extraction_method` (spatial_anchor / regex_primary / regex_fallback / not_found)
- `raw_value` (what OCR literally produced before correction)

### Rule 4 — Rules Must Never Crash the Pipeline

Every rule function is wrapped in try/except in `engine.py`. If one rule raises:
- That rule → `status=SYSTEM_ERROR`
- All other rules continue running
- Response still returns all other results

### Rule 5 — Address Parsing Uses Data Patterns, Not Label Words

```python
# WRONG — depends on OCR reading "Code" correctly:
re.search(r"Zip\s*Code[:\s]+(\d{5})", text)

# RIGHT — anchors on the 5-digit data pattern:
zip_match = re.search(r'\b(\d{5}(?:-\d{4})?)\b', full_address_line)
# Then find state (2 uppercase) before zip
# Then find city between "City" keyword and state
# Then street = rest
```

### Rule 6 — Raw OCR Text Must Be Saved

After OCR, `page_ocr_results.raw_text` column must be populated. This is the ML training signal.

### Rule 7 — Parallel OCR Always

OCR uses `ThreadPoolExecutor(max_workers=4)` in `ocr_pipeline.py`. Sequential page processing
is a regression. If you see a for loop over pages in OCR code, fix it.

### Rule 8 — File Hash Before OCR

Before OCR: SHA-256 hash → check `page_ocr_results` table → if found, return cached → skip OCR.

### Rule 9 — LLM Calls Must Have Fallback

Every Ollama call in `ollama_service.py` has a keyword-based fallback. Pipeline never 500s
because Ollama is down. LLM is the last tier, never the only tier.

### Rule 10 — Feedback Stored With Full Context

Every `feedback_events` row must include: original_value, corrected_value, rule_id, source_page.
Missing these makes the training example useless.

---

## Rule IDs and File Ownership

| Category | IDs | File | Severity |
|----------|-----|------|---------|
| Subject | S-1..S-12 | subject_rules.py | S-1,S-2: BLOCKING; rest: STANDARD/ADVISORY |
| Contract | C-1..C-5 | contract_rules.py | C-1,C-2: BLOCKING; rest: STANDARD |
| Neighborhood structural | N-1..N-7 | neighborhood_rules.py | STANDARD |
| Narrative/Commentary | COM-1..COM-7 | narrative_rules.py | STANDARD/ADVISORY |

**Execution order:** S/C structural (10-90) → S/C logic (110-180) → N structural (190-202) → COM LLM (210-270)

Toggle any rule via: `PATCH /admin/rules/{rule_id}?is_active=false` — no restart needed.

---

## Checkbox Detection Logic

```
For each checkbox field:

    Step 1: _checkbox_state(text, label)  [in phase2_extraction.py]
        Find [X]/[x] near label → CHECKED (True)
        Find [ ] near label → UNCHECKED (False)
        Neither found → UNKNOWN (None)

        CHECKED  → conf=0.90, extraction_method="regex_primary"
        UNCHECKED → conf=0.30, extraction_method="regex_fallback"
        UNKNOWN  → conf=0.00, extraction_method="not_found" → VERIFY

    Future (Phase 6 / when moondream downloaded):
        Step 2: OpenCV pixel analysis on page image region
            dark_pixel_ratio > 0.40 → CHECKED, conf=0.90
            dark_pixel_ratio < 0.15 → UNCHECKED, conf=0.90
            0.15-0.40 → ambiguous → Step 3

        Step 3: moondream2 via Ollama (only if Steps 1+2 both uncertain)
            ollama.generate(model="moondream", prompt="Is checkbox checked? YES or NO", images=[crop])
            Cache result: key = f"{doc_id}:{page}:{label}"
```

---

## OCR Decision Logic

```
For each PDF page:

    word_count = len(page.get_text("text").split())

    if word_count >= 100:                    # MIN_WORDS_THRESHOLD
        use embedded text (PyMuPDF)           → FAST (0.01s)
        method = EMBEDDED

    elif 30 <= word_count < 100:             # HYBRID_OCR_THRESHOLD
        run both embedded + Tesseract
        pick whichever gives more clean words
        method = HYBRID

    else:  # word_count < 30
        full 5-step preprocessing first:
            1. Grayscale (cv2.cvtColor)
            2. Denoising (fastNlMeansDenoising h=10)
            3. Otsu threshold → pure black/white
            4. Table grid removal (40×1 + 1×40 kernels)
            5. Deskew if abs(angle) > 0.5°
        then Tesseract --psm 6
        method = TESSERACT

    Render pages in main thread (fitz not thread-safe)
    Run Tesseract in ThreadPoolExecutor(max_workers=4)
```

---

## LLM Integration — Ollama Only

| Purpose | Model | Max input | Rule |
|---------|-------|-----------|------|
| Commentary analysis | llama3:8b-instruct-q4_0 | 800 chars | COM-1,COM-2,COM-5 |
| Checkbox detection (future) | moondream | 100×100px crop | S-7,S-9,S-11,C-1,C-3,C-4 |

**Settings — never change without documenting why:**
- Temperature: 0.0 (deterministic)
- Max tokens: 10 for binary, 256 for JSON
- Timeout: 60s (fallback activates after)
- All responses cached by SHA-256(task + input_text) in `llm_response_cache` table

---

## Database Tables

```
documents           -- one row per uploaded appraisal PDF set
page_ocr_results    -- one row per page (raw_text, method, confidence) ← ML training signal
extracted_fields    -- one row per field per document (confidence, source_page, raw_ocr_text)
rule_results        -- one row per rule per document
feedback_events     -- operator corrections (ML training source)
training_examples   -- processed feedback ready for model training
rules_config        -- active rules, severity, loan type applicability (toggle without restart)
llm_response_cache  -- cached Ollama responses by SHA-256 input hash
```

---

## API Endpoints

| Method | Path | What It Does |
|--------|------|-------------|
| GET | /health | Service status, Tesseract available, DB reachable |
| POST | /qc/process | Main: appraisal PDF + optional engagement + contract → full QC results |
| POST | /qc/feedback | Operator submits correction → stored + auto-creates training_example |
| GET | /qc/rules | List all 31 rules with severity, execution order, is_active |
| PATCH | /admin/rules/{id} | Toggle rule on/off without restart |
| WS | /qc/ws | WebSocket: real-time progress during processing |

**Authentication:** `allow_origins=["*"]` currently (dev). Must be restricted before production.
**No API key yet** — Phase 7.

---

## Phase Completion Status

| Phase | Description | Status | Gate Passed |
|-------|-------------|--------|------------|
| 0 | Foundation: DB, Redis, Alembic, logging | ✅ Done | Health 200, 9 tables, UUID logging |
| 1 | Smart OCR: parallel, caching, 15s gate | ✅ Done | 14.5s cold, 114ms cached, raw text in DB |
| 2 | Field extraction: address split, confidence, source_page | ✅ Done | All 3 docs address/city/state/zip extracted |
| 3 | Rule engine: 31 rules, DB config, severity, ordering | ✅ Done | 31 rules, toggle works, 93ms on cached |
| 4 | LLM commentary: COM-1..7, ollama, caching, fallback | ✅ Done | N-2 fires on real docs, fallback active |
| 5 | Operator UI: upload, results, detail, feedback | ✅ Done | Frontend at :3000, corrections stored |
| 6 | Feedback & ML learning loop | ⬜ Not started | — |
| 7 | Production deploy | ⬜ Not started | — |

---

## Known Issues (Fix in Order)

| Priority | Issue | Status | Fix |
|----------|-------|--------|-----|
| ✅ FIXED | Zip code parser on "aP Code" | Fixed | `_extract_address_robust` uses 5-digit pattern |
| ✅ FIXED | `force_image_ocr=True` on all pages | Fixed | Parallel + 14.5s target met |
| ✅ FIXED | Raw OCR text not saved | Fixed | `page_ocr_results.raw_text` populated |
| ✅ FIXED | `confidence_score=0.0` always | Fixed | Phase 2 `FieldMetaResult` computes per-field |
| ✅ FIXED | `source_page` always null | Fixed | Phase 2 `page_position_map` tracks pages |
| ✅ FIXED | Checkbox: only checked state detected | Fixed | `_checkbox_state` returns True/False/None |
| ✅ FIXED | `[ ]` treated same as not-found | Fixed | Three-state: True/False/None now distinct |
| 🟡 OPEN | S-10 lender sometimes extracts garbage | Fix | Stricter regex in `phase2_extraction.py` |
| 🟡 OPEN | COM-3 comparable count = 0 | Fix | `_extract_comparables` regex improvement |
| 🟡 OPEN | CORS `allow_origins=["*"]` | Phase 7 | Restrict to env var |
| 🟡 OPEN | No API key auth | Phase 7 | `X-API-Key` middleware |
| 🟡 OPEN | moondream not yet wired into checkbox | Phase 6 | After `ollama pull moondream` completes |

---

*Last updated: 2026-04-25*
*System: FastAPI :5001 | Next.js :3000 | PostgreSQL@18 | Redis | Ollama :11434*
*31 rules: S-1..S-12 + C-1..C-5 + N-1..N-7 + COM-1..COM-7*
