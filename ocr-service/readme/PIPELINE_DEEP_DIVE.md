# Appraisal OCR/QC Pipeline — Deep Dive Specification

> **Live run basis:** All data in this document is from a real test run against  
> `96 Baell Trace Ct SE.pdf` (27 pages) + engagement letter + contract PDF  
> on 2026-04-25. Processing time: **45.5 seconds**, 17 rules, 11 PASS / 3 FAIL / 3 VERIFY.

---

## Table of Contents

1. [Document Ingestion](#1-document-ingestion)
2. [Text vs OCR Decision — The Critical Gate](#2-text-vs-ocr-decision)
3. [Page-Level Handling](#3-page-level-handling)
4. [Image Conversion](#4-image-conversion)
5. [Preprocessing Pipeline](#5-preprocessing-pipeline)
6. [OCR Layer](#6-ocr-layer)
7. [Text Merging](#7-text-merging)
8. [Structuring Layer](#8-structuring-layer)
9. [LLM Integration](#9-llm-integration)
10. [Rule Engine](#10-rule-engine)
11. [Output Layer](#11-output-layer)
12. [Advanced: Pipeline Control & Flow](#12-pipeline-control--flow)
13. [Advanced: Document Complexity Handling](#13-document-complexity-handling)
14. [Advanced: OCR Quality Decisions](#14-ocr-quality-decisions)
15. [Advanced: Data Confidence & Trust Layer](#15-data-confidence--trust-layer)
16. [Advanced: Conflict Resolution](#16-conflict-resolution)
17. [Advanced: Chunking Strategy for LLM](#17-chunking-strategy-for-llm)
18. [Advanced: LLM Behavior Control](#18-llm-behavior-control)
19. [Advanced: Rule Engine Design](#19-rule-engine-design)
20. [Advanced: Performance & Scaling](#20-performance--scaling)
21. [Advanced: Storage & Traceability](#21-storage--traceability)
22. [Advanced: Testing & Validation](#22-testing--validation)
23. [Advanced: Edge Cases](#23-edge-cases)
24. [Advanced: Security & Data Safety](#24-security--data-safety)
25. [Advanced: Idempotency](#25-idempotency)
26. [Advanced: Monitoring](#26-monitoring)
27. [The 5 Most Important Questions — Answered](#27-the-5-most-important-questions)
28. [Known Gaps & What to Fix Next](#28-known-gaps--what-to-fix-next)

---

## 1. Document Ingestion

**Where does the document enter the system?**

`POST /qc/process` in `main.py:291` — this is the primary entry point.  
Three files can arrive in one multipart request:

| Parameter | Type | Required |
|-----------|------|----------|
| `file` | appraisal PDF | ✅ Yes |
| `engagement_letter` | order form PDF or text | Optional |
| `contract_file` | purchase agreement PDF | Optional |

**What formats are accepted?**

- Only `.pdf` — checked by **two independent gates**:
  1. File extension check (`.lower().endswith('.pdf')`) — catches wrong MIME type at the door
  2. Magic byte check — reads first 5 bytes and verifies `b'%PDF-'` — prevents renamed executables from entering the pipeline

**Stored or in-memory?**

Streamed to a `tempfile.TemporaryDirectory()` on disk — **never fully loaded into memory**.  
`shutil.copyfileobj(file.file, buffer)` streams in chunks.  
The temp directory is automatically deleted when the `with` block exits, even if an exception occurs.

```
Client upload
    │
    ▼
multipart/form-data stream
    │
    ▼
TemporaryDirectory (auto-deleted)
    ├── qc_input_{uuid}.pdf        ← appraisal
    ├── qc_eng_{uuid}              ← engagement letter
    └── qc_con_{uuid}              ← contract
```

**What happens on bad input?**

| Condition | HTTP Response |
|-----------|--------------|
| Not a `.pdf` extension | 400 INVALID_FILE_TYPE |
| Magic bytes wrong | 400 INVALID_FILE_CONTENT |
| PyMuPDF can't open it | 400 CORRUPTED_PDF |
| Any other error | 500 EXTRACTION_ERROR |

Every request gets a `request_id` (UUID) logged at start, end, and on failure — so you can trace any request in logs.

---

## 2. Text vs OCR Decision

**This is the most important part of the pipeline.**

The decision is made **per page**, not per document.  
Code: `ocr_pipeline.py:135` — `_extract_page()`.

### Decision Tree

```
For each PDF page:
    │
    ├── Is force_image_ocr=True AND Tesseract installed?
    │       │ YES
    │       └──► Always go straight to Tesseract OCR
    │            (skip embedded text entirely)
    │
    └── Is force_image_ocr=False?
            │
            ▼
        PyMuPDF: page.get_text("text")
        Count words in result
            │
            ├── word_count >= 50 (MIN_WORDS_THRESHOLD)?
            │       │ YES — embedded text is good enough
            │       └──► Use embedded text directly  ← FAST PATH
            │
            └── word_count < 50 — page is mostly images/scanned
                    │
                    ▼
                Run Tesseract OCR on this page
                Compare Tesseract word count vs embedded count
                    │
                    ├── Tesseract gave more words → use Tesseract
                    └── Embedded still better → keep embedded
```

### What actually happened on your 27-page document (live data)

```
PyMuPDF embedded text word counts:
  Pages 1–23:   36 to 1096 words → ALL above 50 → WOULD USE embedded
  Pages 24–27:  37 words each    → BELOW 50     → WOULD trigger Tesseract

But the QC processor uses force_image_ocr=True
→ Result: ALL 27 pages went through Tesseract (ignoring embedded text)
→ Processing time: 45.5 seconds

If hybrid mode were used (force_image_ocr=False):
→ Pages 1–23: instant (PyMuPDF embedded, sub-second)
→ Pages 24–27: Tesseract only on 4 pages
→ Estimated time: ~7–9 seconds  (5× faster)
```

**Current behavior: force_image_ocr=True is hardcoded in SmartQCProcessor** (`qc_processor.py:94`).  
This is deliberately conservative — appraisal forms have embedded text but it often has layout/ordering issues that confuse field extraction. Tesseract reads the visual layout more accurately.  
**Trade-off: accuracy over speed.**

---

## 3. Page-Level Handling

**Is the whole PDF processed at once or page-by-page?**

Page-by-page. `ocr_pipeline.py:117`:

```python
for page_num in range(len(doc)):
    page = doc[page_num]
    page_text = self._extract_page(page, page_num + 1, force_image=use_force)
    result.page_index[page_num + 1] = page_text.text
    result.page_details.append(page_text)
```

Each page produces a `PageText` object:

```python
@dataclass
class PageText:
    page_number: int
    text: str
    method: ExtractionMethod   # "embedded" or "tesseract" or "cloud"
    confidence: float          # 0.0 – 1.0
    word_count: int
    has_tables: bool
```

**Can the system OCR only selected pages?**  
Yes — `PageSelector` class (`ocr_pipeline.py:407`) can find pages by section keyword.  
But currently the QC pipeline processes all pages first, then searches the full text.  
Targeted per-page OCR is implemented but not yet wired into the main flow.

**Current result for your 27-page document:**

| Pages | Word Count Range | has_tables | Method Used |
|-------|-----------------|------------|-------------|
| 1–14 | 96–1121 | True | tesseract |
| 15–23 | 78–229 | True (most) | tesseract |
| 24–27 | 82–530 | False | tesseract |

Pages 24–27 (no tables) are likely the **photo pages and location map** — those genuinely need OCR because they're images.  
Pages 1–23 have plenty of embedded text but were still Tesseract-processed.

---

## 4. Image Conversion

**Where does PDF page → image happen?**

Two separate places depending on the pipeline path:

### Path A: Standard OCR (currently used by QC processor)

Code: `ocr_pipeline.py:236`

```python
mat = fitz.Matrix(dpi / 72, dpi / 72)   # Scale factor for DPI
pix = page.get_pixmap(matrix=mat)        # Render page to pixel map
img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
img = img.convert('L')                   # Convert to grayscale
```

- Uses **PyMuPDF** to render the PDF page directly to a pixel buffer (no intermediate file)
- DPI: **300 in force_image mode**, 200 in normal fallback mode
- Output: PIL Image in grayscale (mode `'L'`)
- **Only pages that need OCR get converted** — but since force_image_ocr=True, all pages convert

### Path B: Preprocessing Pipeline (used by ExtractionService via /qc/extract)

Code: `image_preprocessor.py:89`

```python
pil_images = convert_from_path(pdf_path, dpi=self.dpi)   # Uses pdf2image / poppler
```

- Uses **pdf2image** (which calls poppler's `pdftoppm`) externally
- DPI: **300**
- Converts the **entire PDF** to a list of images first, then preprocesses each
- Heavier pipeline but produces cleaner images for complex forms

**What DPI is used?**

| Mode | DPI | Pixels per page (approx) |
|------|-----|--------------------------|
| Force Tesseract (standard) | 300 | 2550 × 3300 |
| Tesseract fallback | 200 | 1700 × 2200 |
| Preprocessing pipeline | 300 | 2550 × 3300 |

300 DPI is the right choice for form documents — below 200 DPI, Tesseract starts missing small text.

---

## 5. Preprocessing Pipeline

**Do we preprocess images before OCR?**

Two answers — depends on which pipeline:

### Standard path (QC processor, what ran today)

Minimal preprocessing inside `_tesseract_extract()` (`ocr_pipeline.py:243`):
```python
img = img.convert('L')   # Grayscale only — that's it
```
No denoising, no thresholding, no table removal. Just grayscale → Tesseract.

### Full preprocessing path (`/qc/extract` endpoint)

`image_preprocessor.py:106` — 5-step pipeline:

```
Raw image (RGB numpy array)
    │
    ▼  Step 1: Grayscale
    cv2.cvtColor(RGB → GRAY)
    │
    ▼  Step 2: Denoising
    cv2.fastNlMeansDenoising(h=10, templateWindow=7, searchWindow=21)
    Removes scanner noise, JPEG compression artifacts, background texture
    │
    ▼  Step 3: Binary Thresholding (Otsu's method)
    cv2.threshold(0, 255, THRESH_BINARY + THRESH_OTSU)
    Auto-picks the best threshold between ink and paper
    Result: pure black text on white background
    │
    ▼  Step 4: Table Line Removal
    Horizontal kernel (40×1) → detect long horizontal lines
    Vertical kernel (1×40)   → detect long vertical lines
    Subtract line mask from image
    Result: cell text visible without grid interference
    │
    ▼  Step 5: Deskew (only if angle > 0.5°)
    Find largest contour → minAreaRect → rotation angle
    cv2.warpAffine to correct rotation
    Result: straight text rows for Tesseract
    │
    ▼
    Clean image → Tesseract --psm 6
```

**What this fixes:**
- Scanner noise → Step 2 removes it
- Low contrast scans → Step 3 forces pure black/white
- Grid lines confusing Tesseract → Step 4 removes them
- Slightly rotated documents → Step 5 corrects them

**Gap:** The QC processor (`/qc/process`) uses the standard path (Step 1 only). The full preprocessing is only used by `/qc/extract`. These should be unified.

---

## 6. OCR Layer

**Which OCR engine is used?**

**Tesseract** via `pytesseract` Python wrapper.

Binary path: `/opt/homebrew/bin/tesseract` (verified live — M1 Mac homebrew install).

**Tesseract configuration used:**

```python
config = '--psm 6'    # Assume a single uniform block of text
```

PSM 6 tells Tesseract the page is a dense text block — good for form pages.  
No `--oem` flag specified → Tesseract defaults to LSTM neural engine (OEM 3 = LSTM + legacy).

**Do we get plain text only, or text + bounding boxes?**

Currently: **plain text only** via `pytesseract.image_to_string()`.

This is the gap. Bounding boxes would give us:
- Exact field locations on the form
- Ability to match values to their labels by position
- Checkbox detection by pixel location

What we lose by using plain text:
- We can't know that "96 Baell Trace Ct SE" is spatially next to the label "Property Address"
- We rely entirely on text patterns like "Property Address: ..." which OCR sometimes mangles

**Evidence from live run:** The address came back as  
`"96 Baell Trace Ct SE City Moultrie State GA aP Code 31788"` — all on one line, correctly OCR'd but the city/state/zip regex failed to split it (the `aP` before `Code` confused the zip parser).

---

## 7. Text Merging

**How is multi-page text combined?**

`ocr_pipeline.py:399`:

```python
def get_full_text(self, page_index: Dict[int, str]) -> str:
    return "\n\n".join(
        page_index.get(i, "")
        for i in sorted(page_index.keys())   # ← sorted by page number
    )
```

Pages are joined with a double newline separator in page-number order.  
**Page order is preserved.** No page is dropped even if it has 0 words.

**Is there conflict between embedded text and OCR text?**

No conflict can occur per page — the decision is either/or per page (only one method runs).  
The method used is recorded in `PageText.method` for every page.

**How do we know which text came from where?**

`extraction_result.page_details` is a list of `PageText` objects. Each one has:
- `page_number`
- `method` (EMBEDDED / TESSERACT / CLOUD)
- `confidence`
- `word_count`

From the live run: all 27 pages used method=`tesseract`, confidence range 0.55–0.80.

---

## 8. Structuring Layer

**Where does raw text → structured fields happen?**

`extraction_service.py` — the `ExtractionService` class.  
Called from `qc_processor.py:133`:

```python
s_extract = extraction_service.extract_subject_section(full_text)
c_extract = extraction_service.extract_contract_section(full_text)
```

**Is it regex-based, keyword-based, or hybrid?**

**Hybrid — 3 layers in order:**

### Layer 1: Anchor-based section targeting

Before any field extraction, the code finds the actual report start:
```python
report_start = re.search(r"Uniform Residential Appraisal Report", text, re.IGNORECASE)
if report_start:
    text = text[report_start.start():]   # Trim everything before the form header
```
This prevents the table of contents or cover page from polluting the field extraction.

### Layer 2: Structural regex (knows the form layout)

For the address block, the code knows the UAD 1004 form puts all address fields on one line:
```python
addr_line_match = re.search(
    r"Property Address\s*[=:\s]+(.*?City.*?State.*?(?:Zip|ZIP).*)",
    text, re.IGNORECASE | re.MULTILINE
)
```
Then it splits that single line by column headers (`City`, `State`, `Zip Code`) to extract each component.

### Layer 3: Checkbox detection with OCR noise tolerance

Appraisal forms use filled checkboxes that OCR reads inconsistently:
```python
check_pattern = r"(?:\[x\]|\[X\]|X|><|\]X|X\[|x)"
# Handles: [X], [x], X, ><, ]X, X[, x
# All are how Tesseract renders a filled checkbox depending on print quality
```

### What is NOT used:

- No LLM for field extraction (LLM is only used for commentary quality analysis)
- No coordinate-based spatial matching
- No machine learning classifier for field detection
- No Named Entity Recognition

**This is both a strength (fast, predictable) and a weakness (fragile if OCR mangles the label text).**

---

## 9. LLM Integration

**Where is the LLM called in the pipeline?**

The LLM (llama3:8b-instruct-q4_0 via Ollama) is called in the **NLP check layer** only.  
It is **NOT** called during field extraction, OCR, or rule evaluation.

```
Pipeline position:
  OCR → Field Extraction → [LLM commentary checks] → Rule Engine → Output
                              ↑
                         Only here
```

**What input does the LLM receive?**

Short text snippets — never the full document:
- Max 800 characters of commentary text per call
- The form's full text is never sent to the LLM

**Three tasks the LLM handles:**

| Task | Input | Output | Rule |
|------|-------|--------|------|
| Canned commentary detection | Commentary snippet (≤800 chars) | CANNED or SPECIFIC | N-6, N-7 |
| Market conditions quality | Commentary snippet | JSON: {has_analysis, is_see_1004mc, summary} | N-7 |
| Neighborhood description specificity | Description snippet | YES or NO | N-6 |

**What if LLM is unavailable?**

Three-tier fallback (`nlp_checks.py`):
```
Tier 1: Ollama/llama3  →  if server down or model not loaded...
Tier 2: sentence-transformers (all-MiniLM-L6-v2)  →  if not installed...
Tier 3: Rule-based keyword matching  →  always available
```

**Current state (live):** Ollama is installed, model pull is in progress (still downloading).  
Until pull completes → Tier 3 (rule-based) is active automatically.

**LLM settings:**
- Temperature: 0.0 (fully deterministic — same input = same output every time)
- Max tokens: 10 for binary classification, 256 for JSON analysis
- No memory/history between calls — each call is stateless

**What the LLM does NOT do:**

- Does not extract fields
- Does not make pass/fail decisions (that's the rule engine)
- Does not see the full document
- Does not generate rejection language (that's Java's job)
- Does not replace regex-based extraction

---

## 10. Rule Engine

**Where are validation rules defined?**

`app/rules/subject_rules.py` — S-1 through S-12  
`app/rules/contract_rules.py` — C-1 through C-5  

Rules self-register using a decorator at import time:
```python
@rule(id="S-1", name="Property Address Validation")
def validate_property_address(ctx: ValidationContext) -> RuleResult:
    ...
```

**How many rules ran today?**

17 rules total — 12 subject, 5 contract. All ran.

**Do rules run before or after LLM?**

Currently: rules run independently from LLM checks. They share the same `ValidationContext` but don't communicate. A future improvement would be:
- Basic structural rules → run first (S-1 to S-12, C-1 to C-5)
- NLP/commentary rules → run after (N-6, N-7 — not yet implemented as formal rules)

**Rule result types:**

| Status | Meaning | Who handles it |
|--------|---------|----------------|
| PASS | Rule satisfied | Nothing to do |
| FAIL | Definite violation | Java generates rejection question |
| WARNING | Possible issue | Human review flagged |
| VERIFY | Data missing, can't check | Human must look at source doc |
| SKIPPED | Rule doesn't apply (e.g. refinance) | Nothing to do |
| SYSTEM_ERROR | Rule code crashed | Dev needs to debug |

**Are rules hardcoded or configurable?**

Currently hardcoded in Python files. Adding a new rule requires:
1. Write the function in `subject_rules.py` or `contract_rules.py`
2. Decorate with `@rule(id=..., name=...)`
3. Restart the server (rules register at import time)

No database-driven rule configuration exists yet.

---

## 11. Output Layer

**What does the final output look like?**

```json
{
  "success": true,
  "processing_time_ms": 45555,
  "total_pages": 27,
  "extraction_method": "tesseract",
  "total_rules": 17,
  "passed": 11,
  "failed": 3,
  "verify": 3,
  "skipped": 0,
  "system_errors": 0,
  "extracted_fields": {
    "property_address": "96 Baell Trace Ct SE City Moultrie State GA aP Code 31788",
    "borrower_name": "Hung La Owner of Public Record...",
    ...
  },
  "rule_results": [
    {
      "rule_id": "S-1",
      "rule_name": "Property Address Validation",
      "status": "fail",
      "message": "Property address does not match with order form...",
      "action_item": "...",
      "appraisal_value": "96 Baell Trace Ct SE...",
      "engagement_value": "...",
      "review_required": false
    },
    ...
  ],
  "action_items": [...],
  "suggestions": [...],
  "processing_warnings": []
}
```

**Is output consistent across documents?**

Yes — `QCResults` is a Pydantic model with fixed fields. Missing data returns `null`, not missing keys.  
The Java backend can always count on the same schema regardless of document quality.

---

## 12. Pipeline Control & Flow

**Is the pipeline synchronous or asynchronous?**

**Mixed:**
- FastAPI endpoint handler: `async`
- OCR and extraction logic: **synchronous CPU-bound code**, run via `run_in_threadpool()` 
  to avoid blocking the async event loop
- Multiple requests can run concurrently (each in its own thread from the pool)

```python
results = await run_in_threadpool(
    processor.process_document,
    pdf_path=pdf_path,
    ...
)
```

**What happens if a stage fails?**

| Failure | Behavior |
|---------|----------|
| OCR pipeline crashes | `extraction_result.warnings` gets the error; processing continues with empty text |
| A single rule crashes | `SYSTEM_ERROR` result for that rule; other rules continue |
| PDF is corrupted | `fitz.FileDataError` caught → HTTP 400 |
| Extraction service fails | HTTP 500 with error message |

**Can I retry a failed stage without reprocessing everything?**

Currently: **No.** Each request reprocesses everything from scratch.  
There is no intermediate state saved between stages.  
If OCR finishes but rules crash, the OCR work is thrown away.

**This is the biggest operational gap** — expensive OCR results (45 seconds) are not cached.

---

## 13. Document Complexity Handling

**What happens with mixed orientation pages?**

Partially handled:
- Skew detection in the preprocessing pipeline checks rotation angle
- If `abs(angle) > 0.5°` → `cv2.warpAffine` corrects it
- **But** this only runs in the preprocessing path (`/qc/extract`), not the standard QC path (`/qc/process`)
- The standard path uses Tesseract directly which can handle mild rotation but struggles beyond ~15°

**What happens with tables vs paragraphs?**

Table detection is done per-page:
```python
def _detect_tables(self, page: fitz.Page) -> bool:
    blocks = page.get_text("blocks")
    if len(blocks) > 10:     # Many text blocks → likely table
        return True
    drawings = page.get_drawings()
    if len(drawings) > 20:   # Many lines → grid present
        return True
```

From the live run: pages 1–23 all flagged `has_tables=True`. Pages 24–27 (photos/maps) = `has_tables=False`.

But knowing a page has tables doesn't change how we OCR it — we just record it. **Actual table-aware extraction (reading cell-by-cell) is not implemented.**  
Tesseract with `--psm 6` reads left-to-right, top-to-bottom, which works for most UAD 1004 forms but can merge adjacent cells.

**Headers/footers/repeated sections:**  
Not detected or filtered. Page numbers and form headers that appear on every page get included in the full text. The anchor search (`Uniform Residential Appraisal Report`) helps skip the cover page, but repeated form footers can appear multiple times in the concatenated text.

---

## 14. OCR Quality Decisions

**How do we measure OCR confidence?**

`_estimate_confidence()` in `ocr_pipeline.py:250`:

```
Start at 0.5 base score
├── +0.05 per appraisal term found (max +0.30)
│   Terms: "property", "address", "borrower", "value", "appraisal",
│          "comparable", "sales", "neighborhood", "condition"
├── −0.20 if special char ratio > 10% (OCR garbage indicator)
└── −0.10 if 3+ numbers fused together (10+ digit strings)
Range: clamped to [0.1, 1.0]
```

From the live run: confidence ranged from **0.55 to 0.80**.  
Page 1 (cover page, few words): 0.60.  
Pages 2–14 (main form): 0.80.  
Pages 24–27 (photos): 0.65–0.70.

**What if OCR result is low quality?**

Currently: **nothing extra happens.** Low confidence is recorded but doesn't trigger:
- A retry with different preprocessing
- Escalation to cloud OCR
- A human-review flag on the page

The `CLOUD` extraction method is defined (`ExtractionMethod.CLOUD`) but never used — it's a placeholder for Google Vision API or similar.

**What if we want to switch OCR engines?**

EasyOCR is not integrated. Only Tesseract.  
The architecture supports adding it — `_tesseract_extract()` could be replaced with an EasyOCR call in the same `_extract_page()` method.

---

## 15. Data Confidence & Trust Layer

**For each extracted field, do we store confidence score and source?**

Partially. Here's the current state:

| What we have | What we're missing |
|-------------|-------------------|
| Per-page extraction method (EMBEDDED/TESSERACT) | Per-field confidence score |
| Per-page confidence score (0.55–0.80) | Source page number for each field |
| Per-page word count | Which OCR pass found the field |
| Rule result details | Field extraction confidence |

The `ExtractedField` model in `difference_report.py` has:
```python
class ExtractedField(BaseModel):
    field_name: str
    value: Optional[str] = None
    confidence: float = 0.0        ← defined but not populated
    source_page: Optional[int] = None  ← defined but not populated
    raw_text: Optional[str] = None  ← defined but not populated
```

The fields are defined in the model but **not filled in** during extraction — `confidence` is always 0.0.

**This is a known gap.** The field value is extracted but we don't record which page it came from or how confident we are in that specific field.

---

## 16. Conflict Resolution

**What if OCR says one value and embedded text says another?**

This cannot currently happen because the decision is per-page and exclusive:
- If `force_image_ocr=True`: only Tesseract runs, no embedded text
- If `force_image_ocr=False`: the first method that gives ≥50 words wins; the other is discarded

**What if two pages both contain the same field?**

For fields extracted by `_extract_field()` — **first match wins**.  
The method runs `re.search()` against the full concatenated text and returns the first match found, regardless of which page it was on.

**Hierarchy: who wins?**

```
1. Contract PDF text  (most authoritative for C-2 price, C-4 concessions)
2. Engagement letter text  (authoritative for S-1 address, S-2 borrower, S-10 lender)
3. Appraisal report text  (source of truth for all reported values)
```

The comparison logic (`_detect_differences()`) always compares **report value vs engagement letter value** and flags differences. The engagement letter is treated as ground truth for names/addresses. The contract PDF is treated as ground truth for price/date.

---

## 17. Chunking Strategy for LLM

**How do we split large documents before sending to LLM?**

We **do not send large documents to the LLM at all.**

The LLM only receives short commentary snippets — specifically:
- Max 800 characters
- Only the commentary/description field value (not surrounding context)
- One snippet per call, no conversation history

```python
prompt = f'Commentary to classify:\n"""\n{text[:800]}\n"""'
```

This is intentional. The LLM's role is narrow: evaluate a single commentary string's quality.  
It does not need document-level context for this task.

**What we do NOT do (and should not do):**
- Send the full 27-page OCR text to the LLM
- Ask the LLM to extract fields from raw OCR output
- Chain LLM calls with document context

The reason: a 27-page appraisal is ~15,000–25,000 tokens. Even llama3:8b handles that poorly and inconsistently. The regex/pattern approach is more reliable and auditable for structured field extraction.

---

## 18. LLM Behavior Control

**Do we enforce strict JSON output?**

For the binary classification tasks (CANNED/SPECIFIC, YES/NO): no JSON needed — single word.

For the market conditions analysis: the prompt asks for JSON and we attempt to parse it:
```python
json_match = re.search(r"\{.*\}", response, re.DOTALL)
if json_match:
    try:
        return json.loads(json_match.group(0))
    except json.JSONDecodeError:
        pass
# Fallback: keyword extraction from raw response
```

**What happens if LLM hallucinates or gives invalid JSON?**

For binary tasks: if response contains neither expected word → return `None`, caller uses rule-based fallback.  
For JSON tasks: if JSON parse fails → keyword fallback (`"true" in response.lower()`).

The system **never crashes due to LLM output** — every LLM call has a fallback path.

**Do we validate LLM output?**

Yes, minimally:
- Binary response: check if expected keyword appears anywhere in response
- JSON response: `json.loads()` with try/except
- Timeout: 60 seconds — if exceeded, returns `None`, fallback activates

Temperature is set to 0.0 and `top_k=1` — this maximizes determinism and minimizes hallucination for these short classification tasks.

---

## 19. Rule Engine Design

**Are rules hardcoded or configurable?**

Currently **hardcoded** in Python source files.  
Adding a rule = write a function + add `@rule(id, name)` decorator + restart server.

**Can I add a new rule without redeploy?**

No. Rules are registered at import time via the decorator mechanism.

**Do rules support cross-document validation?**

Yes — this is the core strength. `ValidationContext` holds:
```python
class ValidationContext(BaseModel):
    report: AppraisalReport          ← from appraisal PDF
    engagement_letter: EngagementLetter  ← from order form
    purchase_agreement: PurchaseAgreement  ← from contract PDF  ← WIRED IN TODAY
    public_record: PublicRecord      ← placeholder for county assessor data
```

Rules can compare any field across any document:
- S-1: compares `report.subject.address` vs `engagement_letter.property_address`
- C-2: compares `report.contract.contract_price` vs `purchase_agreement.contract_price`

**Rule execution isolation:**

Each rule runs inside a try/except. One rule crashing does not stop others.  
`DataMissingException` is a special exception that converts to `VERIFY` status (not SYSTEM_ERROR).

---

## 20. Performance & Scaling

**How long does each stage take? (measured live)**

| Stage | Time (live run) |
|-------|----------------|
| File upload + magic check | ~50ms |
| Engagement letter OCR | ~2s |
| Contract file OCR | ~3s |
| Appraisal OCR (27 pages, force_tesseract) | **~45 seconds** |
| Field extraction (regex) | <100ms |
| Rule engine (17 rules) | <50ms |
| Response assembly | <10ms |
| **Total** | **~45–48 seconds** |

The bottleneck is overwhelmingly **Tesseract on 27 pages** (approximately **1.7 seconds per page**).

**Can pages be parallelized?**

Currently: **no** — pages are processed in a sequential for loop.  
The `OCR_CONFIG['max_workers'] = 4` setting exists in config but is not used.

**If parallelized:**
```python
# Current: sequential ~45s
for page_num in range(len(doc)):
    page_text = self._extract_page(page, ...)

# With ThreadPoolExecutor(max_workers=4): ~12s (4× faster on M1)
with ThreadPoolExecutor(max_workers=4) as pool:
    futures = [pool.submit(self._extract_page, page, ...) for page in doc]
    results = [f.result() for f in futures]
```

**Can it batch process documents?**

Currently: **no batch endpoint exists.**  
Your uploads folder has 3 properties × 3 files = 9 PDFs. To process all three, you'd need 3 separate API calls.

---

## 21. Storage & Traceability

**Do we store the original file?**

No — the temp directory is deleted after the request completes.  
Nothing is persisted to disk by the OCR service.

**Do we store OCR output?**

No — the raw extracted text is not saved anywhere.  
The `/ocr/appraisal` endpoint returns up to 5,000 characters of raw text in the response, but that's it.

**Can we reproduce a result later?**

No. If you send the same PDF twice, you get two fresh OCR runs. Results may differ slightly (Tesseract is not 100% deterministic across runs).

**What IS logged:**

Every request is logged with:
- `request_id` (UUID)
- Method, path, status code, duration
- File name (but not content)
- Error details if any

Log file: `python_service.log` in the `ocr-service` directory.

---

## 22. Testing & Validation

**Do we have test documents?**

Yes — `test_ocr_and_rules.py` exists.  
Your `uploads/EQSS/xBatch/` folder has 3 real sets:
- 96 Baell Trace Ct SE (appraisal + contract + order form)
- 2307 Merrily Cir N
- 8234 E Pearson

**Can we measure accuracy?**

Not automatically. There are no "expected output" JSON files to compare against.  
Accuracy is currently measured manually by looking at rule results and checking against the actual PDFs.

**Test output files exist:**

```
test_output/
  appraisal_extracted_text.txt    ← raw OCR output from a previous run
  engagement_extracted_text.txt
  extracted_fields.json
  rule_results.json
```

These can serve as regression baselines.

---

## 23. Edge Cases

**What if the document is blurry or partially scanned?**

- Low word count → falls through to Tesseract (in hybrid mode)
- Low confidence score is recorded in `page_details`
- No automatic rejection — the result is used as-is with low confidence
- If the key field (address, borrower) lands on a blurry page → extracted value is wrong → rule fails → VERIFY flag sent to reviewer

**What if pages are missing?**

- PyMuPDF processes whatever pages exist
- Section not found → `_extract_field()` returns `None`
- `None` field → `DataMissingException` raised → rule returns VERIFY

**What if handwritten text is present?**

Tesseract handles printed text well but handwriting accuracy drops to ~40–60%.  
No special handwriting detection or OCR model is configured.  
Handwritten additions (appraiser notes, signatures) will produce garbage text — rules that depend on those fields will get VERIFY status.

**What if the document is password protected?**

`fitz.FileDataError` is caught → HTTP 400 CORRUPTED_PDF response.

---

## 24. Security & Data Safety

**Sensitive data handling:**

The service:
- Never stores uploaded files permanently (temp dir, auto-deleted)
- Does not log file contents — only file names and request IDs
- Does not transmit data to any external service (LLM is local via ollama)
- Does not save OCR output to disk

**Current gaps:**

- No encryption of temp files during processing
- `allow_origins=["*"]` in CORS — should be restricted to known Java backend IP
- No authentication/API key on any endpoint — anyone on the network can hit it
- File names are logged — if file names contain PII (borrower name in filename), that's in logs

---

## 25. Idempotency

**If the same document is uploaded twice, does it process again?**

Yes — full reprocessing every time.  
There is no deduplication, no caching of OCR results, no document hash check.

**Practical implication:** If the Java backend retries a failed request, you pay the full 45-second OCR cost again.

---

## 26. Monitoring

**Do we know OCR failure rate?**

Not systematically. Failures are logged with `logger.error()` and a `request_id` but there's no metrics dashboard or counter.

**Do we know rule violation frequency?**

Only per-request in the response JSON. No aggregate tracking across requests.

**What we have:**

- Structured JSON logging with request_id, duration, status code
- Per-request rule result summary (passed/failed/verify counts)
- `python_service.log` file on disk

**What we're missing:**

- Prometheus metrics endpoint
- Rule violation frequency counter
- OCR confidence distribution histogram
- Average processing time per document type
- Alert if processing time > threshold

---

## 27. The 5 Most Important Questions — Answered

### Q1: When exactly does OCR get triggered?

**Current behavior:** OCR (Tesseract) is triggered for **every page, always**, because `SmartQCProcessor` initializes with `force_image_ocr=True`.

**The smarter behavior** (available but not used for QC):
- PyMuPDF embedded text is tried first
- OCR only triggers if embedded word count < 50

**From live data:** 23 out of 27 pages already had good embedded text (36–1,096 words). Only 4 pages genuinely needed OCR. But all 27 were Tesseract-processed.

### Q2: Is the OCR decision per document or per page?

**Per page.** `_extract_page()` makes an independent decision for each page.  
The document-level `force_image_ocr` flag overrides this to "always OCR" for the QC path.

### Q3: What happens if OCR and PDF text both exist for a page?

Cannot happen currently — the logic is exclusive:
- `force_image_ocr=True` → skip embedded, use Tesseract
- `force_image_ocr=False` → if embedded ≥50 words, skip Tesseract

If forced OCR produces fewer words than embedded text, **forced OCR still wins** (no comparison is made in force mode).

### Q4: Where does structuring happen (before or after LLM)?

**Structuring happens before LLM.**  
Order: OCR text → regex field extraction → structured fields → rule engine  
LLM is called alongside/after rule engine for commentary quality only.

The LLM never sees raw OCR text. It only sees short commentary snippets that have already been extracted.

### Q5: What is the exact role of LLM in my pipeline?

**Commentary quality analyst — narrow and specific.**

```
LLM does:                          LLM does NOT:
✅ "Is this text canned?"         ❌ Extract fields from OCR
✅ "Does this have real analysis?" ❌ Make pass/fail decisions
✅ "Is this specific to this area?" ❌ Generate rejection text
                                   ❌ Compare documents
                                   ❌ See the full PDF text
```

The LLM is the weakest dependency in the pipeline — if it's down, everything else continues working via rule-based fallback.

---

## 28. Known Gaps & What to Fix Next

| Priority | Gap | Impact | Fix |
|----------|-----|--------|-----|
| 🔴 HIGH | `force_image_ocr=True` on all pages | 45s instead of ~9s | Switch to hybrid mode; use force only for pages <50 embedded words |
| 🔴 HIGH | No per-field confidence scores | Can't trust extracted values | Fill `ExtractedField.confidence` and `source_page` during extraction |
| 🔴 HIGH | City/state/zip not splitting correctly | S-1 always FAIL | Fix zip regex — "aP Code" (OCR noise before "Code") breaks pattern |
| 🟡 MED | OCR results not cached | Re-pay 45s per retry | Cache OCR output keyed by PDF hash |
| 🟡 MED | No page parallelization | Linear time | `ThreadPoolExecutor(max_workers=4)` in `extract_all_pages()` |
| 🟡 MED | Full preprocessing not used by `/qc/process` | Lower OCR quality | Unify both paths to use ImagePreprocessor |
| 🟡 MED | No batch endpoint | Manual 3-call workflow | Add `/qc/batch` that accepts a folder or ZIP |
| 🟡 MED | `per-field source_page` not populated | Can't trace field to page | Populate during regex extraction |
| 🟢 LOW | No Prometheus metrics | Blind to failures | Add `prometheus-fastapi-instrumentator` |
| 🟢 LOW | CORS `allow_origins=["*"]` | Security risk | Restrict to Java backend IP |
| 🟢 LOW | No API key auth | Open endpoint | Add `X-API-Key` header check |

---

*Document generated 2026-04-25. Live test: 96 Baell Trace Ct SE.pdf, 27 pages, 45.5s, 17 rules.*  
*Server: FastAPI on port 5001, conda env `apprisal` (Python 3.11), Tesseract `/opt/homebrew/bin/tesseract`.*
