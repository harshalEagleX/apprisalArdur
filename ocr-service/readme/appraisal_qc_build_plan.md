# Appraisal QC Software — Complete Build Plan
### Better Than HomeVision | 1 Month | Phase-by-Phase

> **Goal:** Build a production-ready appraisal quality control platform where an operator uploads a PDF and gets instant, trustworthy results — and where the system gets smarter every time someone corrects it.

---

## Table of Contents

1. [What You Are Building (Big Picture)](#1-what-you-are-building)
2. [The Core Intelligence Strategy — OCR vs LLM vs ML](#2-the-core-intelligence-strategy)
3. [Architecture Overview](#3-architecture-overview)
4. [Phase 0 — Foundation (Days 1–3)](#4-phase-0--foundation)
5. [Phase 1 — Document Ingestion & Smart OCR (Days 4–8)](#5-phase-1--document-ingestion--smart-ocr)
6. [Phase 2 — Field Extraction Engine (Days 9–13)](#6-phase-2--field-extraction-engine)
7. [Phase 3 — Rule Engine (Days 14–18)](#7-phase-3--rule-engine)
8. [Phase 4 — LLM Commentary Analysis (Days 19–21)](#8-phase-4--llm-commentary-analysis)
9. [Phase 5 — Operator UI (Days 22–25)](#9-phase-5--operator-ui)
10. [Phase 6 — Feedback & Self-Learning Loop (Days 26–28)](#10-phase-6--feedback--self-learning-loop)
11. [Phase 7 — Polish, Test & Deploy (Days 29–30)](#11-phase-7--polish-test--deploy)
12. [When to Use OCR vs LLM vs ML — Decision Guide](#12-when-to-use-ocr-vs-llm-vs-ml)
13. [How the ML Model Learns From Feedback](#13-how-the-ml-model-learns-from-feedback)
14. [Phase Achievement Gates](#14-phase-achievement-gates)
15. [Daily Hours Plan](#15-daily-hours-plan)
16. [What Makes This Better Than HomeVision](#16-what-makes-this-better-than-homevision)
17. [Risk Register](#17-risk-register)

---

## 1. What You Are Building

Think of this software as a **very fast, very smart appraisal reviewer** that never gets tired, never misses a rule, and gets smarter every day. Here is what it does in plain English:

### The User Journey (Operator Perspective)

```
Operator uploads 3 files:
  1. Appraisal report PDF (27 pages)
  2. Engagement letter (order form)
  3. Purchase contract

     ↓  (30 seconds or less)

System shows:
  ✅ 11 rules PASSED
  ❌  3 rules FAILED  ← "Address doesn't match order form"
  ⚠️  3 rules NEED HUMAN REVIEW

Operator clicks on each FAILED rule:
  → Sees exactly what the PDF said
  → Sees exactly what the order form said
  → Sees the difference highlighted
  → Can mark: "I agree this is wrong" or "System is wrong, here's the real answer"

System learns from that correction.
Next time it sees the same pattern: it gets it right.
```

### What Makes This Different From a Simple PDF Checker

A simple checker just runs rules. Your system will:

1. **Know the visual layout of appraisal forms** — not just search for words
2. **Understand appraisal language** — "C3 condition" means something specific
3. **Compare across 3 documents simultaneously** — catches errors that live in the gap between documents
4. **Learn from reviewer corrections** — every correction trains the ML layer
5. **Show confidence scores** — operator knows when to trust results vs when to double-check
6. **Explain every decision** — "I flagged this because the zip code in the report (31788) doesn't match the order form (31789)"

---

## 2. The Core Intelligence Strategy — OCR vs LLM vs ML

This is the most important design decision in the whole system. Read this carefully.

### The Three Tools and Their Jobs

Think of it like a team of three specialists:

```
┌─────────────────────────────────────────────────────────────┐
│  TOOL 1: OCR (Tesseract / Vision)                           │
│  Job: Eyes. Converts PDF images into text.                  │
│  Good at: Reading printed text from images                  │
│  Bad at: Understanding what the text means                  │
│  Speed: Slow (1–2 seconds per page)                         │
│  Cost: Free (local)                                         │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  TOOL 2: LLM (Claude / GPT / Local Llama)                   │
│  Job: English professor. Reads text and judges quality.     │
│  Good at: "Is this commentary generic or specific?"         │
│           "Does this description make real-world sense?"    │
│  Bad at: Structured field extraction (inconsistent)         │
│  Speed: Medium (1–5 seconds per call)                       │
│  Cost: API cost or local GPU                                │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  TOOL 3: ML Model (Your Trained Classifier)                 │
│  Job: Pattern memorizer. Remembers what worked.             │
│  Good at: "I've seen this OCR error before, the real        │
│           value was X"                                      │
│           "This field pattern usually means PASS"           │
│  Bad at: Things it has never seen before                    │
│  Speed: Very fast (milliseconds)                            │
│  Cost: Training time (weekly)                               │
└─────────────────────────────────────────────────────────────┘
```

### The Decision Rule — Which Tool for Which Job

| Task | Tool | Why |
|------|------|-----|
| Convert scanned/image PDF pages to text | OCR | Only option |
| Extract embedded text from digital PDFs | PyMuPDF (no OCR needed) | Faster, more accurate |
| Find "Property Address" field value | Regex + Pattern matching | Fast, auditable, deterministic |
| Judge commentary quality ("Is this canned?") | LLM | Only LLM understands language quality |
| Check if address in report matches order form | Rule Engine (string compare) | Simple comparison, no AI needed |
| Correct OCR errors ("aP Code" → "Zip Code") | ML model trained on past corrections | Learns your specific document patterns |
| Detect checkbox state (☑ or ☐) | OCR + Image analysis | Text + pixel both needed |
| Classify document section (subject/comps/addenda) | ML classifier | Pattern recognition |

### The Golden Rule

> **Only use AI (LLM or ML) when a simpler tool cannot do the job.**
> Rules before regex. Regex before ML. ML before LLM. LLM last resort.

This keeps the system fast, cheap, and explainable.

---

## 3. Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                         FRONTEND (React/Next.js)                     │
│  Upload UI  |  Results Dashboard  |  Rule Detail View  |  Feedback   │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │ HTTP / WebSocket
┌────────────────────────────────▼─────────────────────────────────────┐
│                      API GATEWAY (FastAPI)                            │
│  /qc/process  |  /qc/feedback  |  /admin/rules  |  /health           │
└──────┬──────────────────┬──────────────────┬────────────────┬────────┘
       │                  │                  │                │
┌──────▼──────┐  ┌────────▼──────┐  ┌───────▼──────┐  ┌─────▼──────┐
│   DOCUMENT  │  │  EXTRACTION   │  │    RULE      │  │  FEEDBACK  │
│  INGESTION  │  │   ENGINE      │  │   ENGINE     │  │   STORE    │
│             │  │               │  │              │  │            │
│ - PDF valid │  │ - OCR layer   │  │ - S-1..S-12  │  │ - Postgres │
│ - File type │  │ - Field parse │  │ - C-1..C-5   │  │ - Training │
│ - Temp store│  │ - ML correct  │  │ - N-1..N-7   │  │   queue    │
└─────────────┘  └───────────────┘  └──────────────┘  └────────────┘
                          │                  │
                 ┌────────▼──────┐  ┌────────▼──────┐
                 │  OCR SERVICE  │  │  LLM SERVICE  │
                 │  (Tesseract)  │  │  (Local/API)  │
                 └───────────────┘  └───────────────┘
                          │
                 ┌────────▼──────┐
                 │   ML MODEL    │
                 │  (Correction  │
                 │   Classifier) │
                 └───────────────┘
                          │
                 ┌────────▼──────┐
                 │   DATABASE    │
                 │  (PostgreSQL) │
                 │               │
                 │ - Documents   │
                 │ - Results     │
                 │ - Feedback    │
                 │ - ML training │
                 └───────────────┘
```

### Tech Stack Choices (Simple and Proven)

| Layer | Technology | Why This Choice |
|-------|-----------|----------------|
| Backend API | FastAPI (Python) | You already know it, async, fast |
| Frontend | Next.js + TailwindCSS | Fast to build, looks professional |
| Database | PostgreSQL | Reliable, good for training data |
| OCR | Tesseract (local) + Hybrid mode | Free, good enough, add cloud later |
| PDF reading | PyMuPDF | Best embedded text extraction |
| LLM | Claude API (or local Ollama) | Best quality, good API |
| ML training | scikit-learn → then PyTorch | Start simple, grow complex |
| Deployment | Docker + single VPS | Simple, cheap |
| Background jobs | Celery + Redis | For async OCR processing |

---

## 4. Phase 0 — Foundation (Days 1–3)

**Goal:** Get a clean project structure running. Zero features. Just scaffolding.

### What You Build

This is not glamorous. You are setting up the foundation so that in Phase 1, you never have to stop to set up tools. Think of it as building the road before the race.

**Project Folder Structure:**

```
appraisal-qc/
├── backend/
│   ├── app/
│   │   ├── api/            ← API routes live here
│   │   ├── services/       ← Business logic lives here
│   │   │   ├── ocr/
│   │   │   ├── extraction/
│   │   │   ├── rules/
│   │   │   ├── llm/
│   │   │   └── ml/
│   │   ├── models/         ← Database models live here
│   │   ├── schemas/        ← Pydantic response shapes
│   │   └── core/           ← Config, logging, error handling
│   ├── tests/
│   ├── alembic/            ← Database migrations
│   └── requirements.txt
├── frontend/
│   ├── app/
│   ├── components/
│   └── package.json
├── ml/
│   ├── data/               ← Training data lives here
│   ├── models/             ← Saved ML model files
│   └── notebooks/          ← Jupyter notebooks for experiments
├── docker/
│   ├── docker-compose.yml
│   └── Dockerfile.*
└── docs/
```

**What Gets Set Up:**

1. Python virtual environment with all packages installed
2. PostgreSQL database running in Docker
3. Redis running in Docker (for job queue)
4. FastAPI server starts without errors
5. Next.js frontend starts without errors
6. One working health check endpoint that returns `{"status": "ok"}`
7. Logging system — every request gets a UUID and is logged
8. Environment variable system — no secrets hardcoded anywhere
9. Database migration tool (Alembic) set up

**Database Tables to Create Now (You Will Add Columns Later):**

```
documents          — stores every uploaded PDF (metadata only, not the file itself)
processing_jobs    — tracks where each document is in the pipeline
rule_results       — stores every rule outcome for every document
feedback_events    — stores every correction an operator makes
extracted_fields   — stores every field extracted from every document
training_examples  — stores labeled data for ML training
```

### Achievement Gate to Move to Phase 1

You are ready for Phase 1 when:
- [ ] `docker-compose up` starts everything without errors
- [ ] `GET /health` returns 200 OK
- [ ] A test PDF upload stores metadata in the database
- [ ] Logs show request UUID on every request
- [ ] A new developer can clone the repo and run it in under 10 minutes

---

## 5. Phase 1 — Document Ingestion & Smart OCR (Days 4–8)

**Goal:** Accept any appraisal PDF and produce high-quality extracted text. Faster than your current system (under 15 seconds for a 27-page document).

### The Problem With Your Current System

Your current `force_image_ocr=True` runs Tesseract on all 27 pages. 23 of those pages already had readable text. You are paying 45 seconds when you should pay 9 seconds.

### The Smart OCR Decision (Improved Version)

Here is the exact logic you will implement, improved from what you have now:

```
For each page:
    Step 1: Try PyMuPDF embedded text
        → If word count ≥ 100 AND no OCR noise detected:
            → Use embedded text  (takes 0.01 seconds)
            → Mark confidence = HIGH
            
        → If word count between 30 and 99:
            → Run OCR in parallel
            → Pick whichever gives more clean words
            → Mark confidence = MEDIUM
            
        → If word count < 30:
            → Must OCR (image-heavy page: photos, maps, signatures)
            → Mark confidence = DEPENDS ON OCR QUALITY
            
    Step 2: For pages going to OCR:
        → First: run full preprocessing (not just grayscale!)
            - Grayscale conversion
            - Denoising
            - Otsu thresholding (black/white)
            - Table grid removal
            - Deskew if angle > 0.5°
        → Then: Tesseract with PSM 6
        
    Step 3: Confidence scoring (improved)
        → Count appraisal vocabulary words found
        → Check for OCR garbage patterns
        → Check for number fusion errors
        → Record per-page confidence score
        → Record which method was used
        → Record which page number
```

### The Key Improvement — Parallel Page Processing

Your current system processes pages one by one. Your new system will process them 4 at a time:

```
Current:   Page1 → Page2 → Page3 → ... Page27  =  45 seconds
New:       [Page1, Page2, Page3, Page4] simultaneously
            → [Page5, Page6, Page7, Page8] simultaneously
            → ...
            =  ~12 seconds
```

This is the `ThreadPoolExecutor` change that is already in your config but not wired in. Wire it in.

### Document Ingestion Security (Improved From Current)

Your current system checks extension and magic bytes. Add:

1. **File size limit:** Max 50MB per file
2. **Page count limit:** Max 100 pages (reject construction plans that get uploaded by mistake)
3. **Virus scan hook:** Even if you don't run antivirus now, add the hook so you can add it later
4. **Rate limiting:** Max 10 documents per hour per user
5. **Temp file encryption:** Encrypt temp files at rest using OS temp folder with restricted permissions

### What to Store in Database After OCR

For each document processed, store:

```
documents table:
  - document_id (UUID)
  - original_filename
  - file_hash (SHA-256 of file bytes)   ← enables deduplication
  - page_count
  - upload_timestamp
  - uploaded_by_user_id

per_page_ocr_results table:
  - document_id
  - page_number
  - extraction_method  (EMBEDDED / TESSERACT / HYBRID)
  - word_count
  - confidence_score
  - raw_text          ← SAVE THIS (you currently discard it)
  - processing_ms
```

**Why save raw text?** Because when the ML model makes a correction, you need to go back and look at what OCR originally produced to train from it. Right now you discard it and lose this training signal.

### OCR Result Caching (Fixes Your Biggest Gap)

Hash the PDF file (SHA-256). Before OCR, check the database:
- If hash found → return cached OCR result instantly
- If hash not found → run OCR, then save result to database

This means: if the Java backend retries a request, you do NOT pay 45 seconds again. You pay 0 seconds.

### Achievement Gate to Move to Phase 2

You are ready for Phase 2 when:
- [ ] A 27-page appraisal PDF processes in under 15 seconds
- [ ] Per-page confidence scores are stored in database
- [ ] Raw OCR text is stored per page in database
- [ ] Duplicate PDF (same hash) returns cached result in under 1 second
- [ ] A photo page (low text) correctly triggers full preprocessing
- [ ] A digital PDF page (high text) correctly uses embedded text
- [ ] Extraction method (EMBEDDED/TESSERACT) is stored per page

---

## 6. Phase 2 — Field Extraction Engine (Days 9–13)

**Goal:** Take the raw OCR text and reliably extract every field the rules need. Fix the zip code bug and all similar problems.

### The Current Weakness

Your current extraction is fragile because:
1. It relies on text patterns that OCR mangles ("aP Code" instead of "Zip Code")
2. It has no confidence score per field
3. It doesn't know which page a field came from
4. It only does first-match, not best-match

### The Improved Extraction Architecture

**Three-layer extraction system:**

**Layer 1 — Spatial Anchoring (New)**

Instead of just searching raw text, you understand the form layout:
- The UAD 1004 form always has the address block in the same position on page 1
- The borrower name is always in the same row
- The contract price is always in section 2

So you look for anchor words (section headers) first, then extract fields relative to those anchors. This is much more reliable than searching the full text.

```
Example:
Raw approach: search all 27 pages for "Property Address"
Spatial approach: 
  → Find "Uniform Residential Appraisal Report" header (always page 1)
  → Look at the first 20 lines below it
  → Extract address from that zone
  → Much less chance of hitting the wrong "Property Address" on page 7
```

**Layer 2 — OCR Error Correction (New — Your ML Model's First Job)**

OCR makes the same mistakes repeatedly on the same form types. Instead of trying to fix them in regex, you train a small ML model to correct them.

Common OCR errors in appraisal forms:
- "aP Code" → should be "Zip Code"
- "Borrovver" → should be "Borrower"
- "0 wner" → should be "Owner"
- "l.ender" → should be "Lender"
- Checkbox "X]" → should be "[X]"
- Dollar amount "$1O0,000" → should be "$100,000"

You collect these corrections from operator feedback (Phase 6) and train a correction model.

For now (Phase 2), hardcode the most common ones as a correction dictionary. Later (Phase 6), the ML model replaces the dictionary.

**Layer 3 — Cross-Field Validation (New)**

After extracting individual fields, run sanity checks:
- If state is "GA", the zip code should start with 3
- If contract date is after inspection date, flag it
- If property value is $0, that's an extraction error, not a real value
- If borrower name is more than 60 characters, probably OCR merged two lines

These are not rules (rules run later). These are extraction quality checks. If a sanity check fails, set field confidence to LOW and mark it for human review.

### The Field Extraction Data Model (Improved)

Every field you extract must store:

```
extracted_field:
  - document_id
  - field_name            (e.g. "property_address_street")
  - field_value           (e.g. "96 Baell Trace Ct SE")
  - confidence_score      (0.0 to 1.0)   ← FILL THIS IN (you have it but don't use it)
  - source_page           (e.g. 1)       ← FILL THIS IN (you have it but don't use it)
  - extraction_method     (REGEX / SPATIAL / ML_CORRECTED)
  - raw_ocr_text          (what OCR actually produced before correction)
  - correction_applied    (True/False — did ML change something?)
  - extraction_timestamp
```

This is critical for the learning loop. You need to know:
- What did OCR produce?
- What did extraction produce?
- What did the operator say the right answer was?
- Now train the model on that.

### Fields to Extract (Minimum Viable Set)

**From the appraisal report:**
- Property address (street, city, state, zip — split into 4 separate fields)
- Borrower name
- Lender name
- Property rights appraised (fee simple / leasehold)
- Date of appraisal
- Effective date
- Contract price (if a sale)
- Contract date
- Market value opinion
- Neighborhood description (text block)
- Market conditions commentary (text block)
- Comparable sale 1, 2, 3 addresses
- Comparable sale 1, 2, 3 prices
- Condition rating (C1–C6)
- Quality rating (Q1–Q6)

**From the engagement letter:**
- Ordered property address
- Ordered borrower name
- Ordered lender name
- Fee amount
- Due date

**From the purchase contract:**
- Contract price
- Contract date
- Seller concessions (amount and type)
- Property address

### The Address Splitting Fix (Fixing Your Current Bug)

Your current code fails on: `"96 Baell Trace Ct SE City Moultrie State GA aP Code 31788"`

The fix: do not try to split on the word "Code". Instead:

1. Find the 5-digit number at the end — that is the zip code
2. Find the 2-letter uppercase abbreviation before it — that is the state
3. Find the text between "City" and the state abbreviation — that is the city
4. Find the text before "City" — that is the street address

This approach works even when OCR mangles the label words. You are anchoring on the data pattern (5 digits = zip, 2 uppercase = state) not the label words.

### Achievement Gate to Move to Phase 3

You are ready for Phase 3 when:
- [ ] All 15+ fields extract correctly from your 3 test documents
- [ ] Address correctly splits into street, city, state, zip on all 3 documents
- [ ] Every extracted field has a confidence score stored in database
- [ ] Every extracted field has a source page number stored in database
- [ ] A field with confidence below 0.5 is automatically flagged as VERIFY
- [ ] Cross-field sanity checks catch at least 3 types of obviously wrong data

---

## 7. Phase 3 — Rule Engine (Days 14–18)

**Goal:** Run all 17+ validation rules, produce clear PASS/FAIL/VERIFY/WARNING results, with a human-readable explanation for every result.

### What the Rule Engine Needs to Be

Think of the rule engine like a checklist. An appraisal reviewer has 17 things they must check. The rule engine checks all 17 and reports back.

The key improvements over your current system:

1. **Rules run in the right order** — structure rules first, then content rules, then commentary rules
2. **Rules explain themselves** — not just FAIL but "Contract price in report ($285,000) does not match contract ($295,000)"
3. **Rules can be configured** without code changes — stored in database
4. **Rules have severity** — some failures block delivery, some are just warnings
5. **Rules can be turned off** for specific loan types

### Rule Categories

**Category S — Subject Property Rules (12 rules)**

| Rule ID | Rule Name | What It Checks | Failure Means |
|---------|-----------|----------------|---------------|
| S-1 | Address Match | Report address vs engagement letter | Appraiser appraised wrong property |
| S-2 | Borrower Match | Borrower name in report vs order | Wrong file mixed in |
| S-3 | Lender Match | Lender name in report vs order | Compliance issue |
| S-4 | Property Rights | Fee simple or leasehold checked | Required field missing |
| S-5 | Effective Date | Date of value is provided and logical | Required field missing |
| S-6 | Site Size | Site size provided | Required field missing |
| S-7 | Neighborhood Boundaries | Neighborhood section has actual boundaries | Canned language |
| S-8 | Market Conditions | 1004MC form referenced or actual analysis | Required analysis missing |
| S-9 | Condition Rating | C1-C6 checked and consistent with description | Internal inconsistency |
| S-10 | Inspection Date | Date of inspection provided and before effective date | Logic error |
| S-11 | Comparable Count | At least 3 sales comps provided | Required minimum not met |
| S-12 | Value Reconciliation | Final value within range of comp-indicated values | Outlier value |

**Category C — Contract Rules (5 rules)**

| Rule ID | Rule Name | What It Checks | Failure Means |
|---------|-----------|----------------|---------------|
| C-1 | Contract Existence | Is there a contract? Is it acknowledged? | Required acknowledgment missing |
| C-2 | Contract Price Match | Report price vs purchase contract price | Appraiser used wrong price |
| C-3 | Contract Date | Contract date is provided and logical | Required field missing |
| C-4 | Seller Concessions | If concessions present, analyzed in report | FNMA requirement not met |
| C-5 | Listing History | Property listing history acknowledged | Required disclosure missing |

**Category N — Narrative/Commentary Rules (7 rules)**

| Rule ID | Rule Name | What It Checks | Failure Means |
|---------|-----------|----------------|---------------|
| N-1 | Neighborhood Description | Is it specific to this area? | Copy-paste boilerplate |
| N-2 | Market Conditions Commentary | Does it reference actual market data? | Canned / insufficient |
| N-3 | Comparable Selection Rationale | Why were these comps chosen? | Required explanation missing |
| N-4 | Adjustments Explanation | Are adjustments explained? | FNMA requirement |
| N-5 | Reconciliation Commentary | Does reconciliation explain value? | Insufficient analysis |
| N-6 | Addenda Consistency | Addenda don't contradict main form | Internal conflict |
| N-7 | Prior Sales | Prior sales of subject addressed | Required disclosure |

### Rule Result Structure (Improved)

Every rule produces this output:

```
rule_result:
  - rule_id              (e.g. "S-1")
  - rule_name            (e.g. "Address Match")  
  - status               (PASS / FAIL / VERIFY / WARNING / SKIPPED)
  - severity             (BLOCKING / STANDARD / ADVISORY)
  - message              (human readable: "Address in report does not match order form")
  - detail               (full explanation with actual values)
  - appraisal_value      (what the report says)
  - reference_value      (what the engagement letter or contract says)
  - source_page          (which page of the report was used)
  - confidence           (how confident are we in our extracted values?)
  - action_required      (what the operator or appraiser must do)
  - auto_correctable     (can the system correct this without human help?)
  - rule_version         (so you know which version of the rule ran)
```

### Rule Configuration in Database (New — Big Improvement)

Instead of rules being hardcoded forever, store them in a database:

```
rules table:
  - rule_id
  - rule_category
  - rule_name
  - is_active           ← can turn off without code change
  - severity_level      ← can change without code change
  - applicable_loan_types  ← not all rules apply to refinances
  - created_at
  - last_modified_at
  - modified_by
```

This means:
- A compliance officer can turn off a rule that is not applicable this month
- You can add a new rule by inserting a row (if the logic is in a plugin system)
- You can see the history of rule changes

### Rule Execution Order

Rules must run in this order:

```
Step 1: Data availability check
  → If key fields are NULL, mark dependent rules as VERIFY
  → Don't waste time running address match if address extraction failed

Step 2: Structural rules (S-1 through S-6, C-1 through C-3)
  → Simple field comparisons
  → Fastest to run, foundational

Step 3: Logic rules (S-7 through S-12, C-4, C-5)
  → Require multiple fields
  → Medium complexity

Step 4: Commentary/narrative rules (N-1 through N-7)
  → Require LLM analysis (Phase 4)
  → Slowest — run last
  → If LLM is down, degrade gracefully to rule-based fallback
```

### Achievement Gate to Move to Phase 4

You are ready for Phase 4 when:
- [ ] All 17 rules run on your 3 test documents
- [ ] Every FAIL result shows the actual values from both documents
- [ ] VERIFY status correctly appears when a field was not extracted
- [ ] Rules are stored in the database and can be toggled without code restart
- [ ] A single rule crashing does not stop the other 16 rules from running
- [ ] Processing time for all 17 rules is under 200 milliseconds
- [ ] Rule results match what a human reviewer would say on your 3 test documents

---

## 8. Phase 4 — LLM Commentary Analysis (Days 19–21)

**Goal:** Use an LLM to evaluate commentary quality. Three days only — keep this narrow.

### What LLM Is Used For (Narrow and Specific)

The LLM does exactly three jobs. No more, no less.

**Job 1: Canned Language Detection (Rules N-1, N-2)**

You send it a commentary snippet (max 800 characters). It answers one question: "Is this commentary generic boilerplate OR is it specific to this property?"

Example input: "The subject neighborhood is in good condition with stable property values and typical market exposure times."

Expected output: CANNED

Example input: "The subject is located in the Moultrie, GA market, Colquitt County. The neighborhood shows 8% annual price appreciation over the last 12 months per MLS data. Average DOM is 47 days with 3.2 months supply."

Expected output: SPECIFIC

**Job 2: Market Analysis Quality (Rule N-2)**

Has the appraiser actually analyzed the market or just referred to the 1004MC addendum?

Example output: `{"has_real_analysis": true, "references_data": true, "is_see_1004mc_only": false}`

**Job 3: Reconciliation Sufficiency (Rule N-5)**

Does the reconciliation explain why the final value was chosen, or just restate the comparable values?

### How to Call the LLM Correctly

**Always include a system prompt that explains context:**

```
System: You are an appraisal compliance analyst reviewing UAD 1004 appraisal 
report commentaries. The property is located in [state]. Answer with exactly 
one word: CANNED or SPECIFIC.

User: Evaluate this neighborhood description:
"[commentary text, max 800 characters]"
```

**Always use temperature = 0** — you want the same answer every time for the same text.

**Always have a fallback:**

```
Try LLM API call
  → If timeout (>30 seconds): use keyword matching fallback
  → If API error: use keyword matching fallback
  → If invalid response: use keyword matching fallback
  → Never fail the whole request because LLM is down
```

**Keyword matching fallback for canned detection:**

Build a list of 50 common canned phrases. If the commentary contains more than 2 of them: CANNED. Otherwise: SPECIFIC. This is 80% as accurate as the LLM and works 100% of the time.

### LLM Cost Control

If you use Claude API:
- Average LLM call: ~500 input tokens + ~20 output tokens = ~520 tokens
- At 3 calls per document: ~1,560 tokens per document
- At 1,000 documents per month: 1.56 million tokens
- Cost: roughly $2–5 per month at current rates

This is very cheap. Don't run LLM calls on preprocessing or field extraction — only on commentary evaluation where it actually adds value.

### LLM Response Caching

If you process the same commentary text again (same document reprocessed), return the cached LLM result. Store LLM responses in the database keyed by hash of input text. This saves time and cost.

### Achievement Gate to Move to Phase 5

You are ready for Phase 5 when:
- [ ] N-1 (neighborhood description) correctly classifies CANNED vs SPECIFIC on 10 test samples
- [ ] N-2 (market conditions) correctly classifies quality on 10 test samples
- [ ] LLM being down does not crash the pipeline — fallback activates automatically
- [ ] LLM responses are cached — same text returns same answer instantly on second call
- [ ] LLM adds less than 5 seconds to total processing time

---

## 9. Phase 5 — Operator UI (Days 22–25)

**Goal:** Build the screen where an operator sees results, understands them, and corrects them. This is what operators interact with every day.

### The Core Screens

**Screen 1 — Upload Screen**

Simple drag-and-drop area for three files. Shows progress as processing happens. Uses a WebSocket to push real-time updates:
- "Extracting text from 27 pages..." (with page counter)
- "Running 17 compliance rules..."
- "Complete! 11 PASS, 3 FAIL, 3 VERIFY"

**Screen 2 — Results Dashboard**

Shows results at a glance. The most important information first:

```
╔══════════════════════════════════════════════════════════════╗
║  96 Baell Trace Ct SE, Moultrie, GA 31788                   ║
║  Processed: 45.5 seconds  |  27 pages  |  Tesseract OCR     ║
╠══════════════════════════════════════════════════════════════╣
║  ✅ 11 PASSED    ❌ 3 FAILED    ⚠️ 3 VERIFY                 ║
╠══════════════════════════════════════════════════════════════╣
║  FAILED RULES (action required):                            ║
║  ❌ S-1 Address Match — Report vs Order form differ         ║
║  ❌ C-2 Contract Price — $285,000 vs $295,000               ║
║  ❌ N-2 Market Commentary — Appears to be canned language   ║
╠══════════════════════════════════════════════════════════════╣
║  NEEDS REVIEW:                                              ║
║  ⚠️ S-5 Effective Date — Could not extract from report      ║
║  ⚠️ N-7 Prior Sales — Section not found                     ║
║  ⚠️ C-4 Concessions — Contract not clear                    ║
╚══════════════════════════════════════════════════════════════╝
```

**Screen 3 — Rule Detail View (Most Important Screen)**

When operator clicks on any rule, they see:

```
S-1: Address Match — FAILED

What we found in the Report:          What the Order Form says:
  "96 Baell Trace Ct SE"                "96 Bell Trace Ct SE"
  Moultrie                               Moultrie
  GA                                     GA
  31788                                  31788

Difference: Street name "Baell" vs "Bell"

Source: Report page 1 (confidence: 0.82)
        Order form page 1 (confidence: 0.91)

Possible causes:
  → OCR misread "Bell" as "Baell" in the report
  → Appraiser typed the wrong street name
  → The order form has a typo

[PDF SNIPPET showing exact page 1 area where address was found]

What would you like to do?
  ○ This is a real error — send back to appraiser
  ○ This is an OCR error — the correct street is: [__________]
  ○ This is an order form typo — ignore this mismatch
  ○ I'm not sure — flag for senior review
```

**Why this screen is so important:** It is the feedback collection point. Every time an operator picks an option, you collect a training example for your ML model.

**Screen 4 — Export / Send to Java**

After operator reviews results:
- Export full QC report as PDF
- Send structured JSON to the Java backend
- Mark document as "reviewed" in database

### UI Design Principles (Operator Confidence)

1. **Show your work** — never just say FAIL. Show what you found and where.
2. **Show confidence** — a green confidence bar helps operators know when to trust vs verify
3. **Never hide uncertainty** — VERIFY means "we tried but couldn't find this, you must look"
4. **Make correction easy** — the feedback form must take under 30 seconds
5. **Show the PDF** — embed a PDF viewer so operator never has to leave the app to check
6. **Mobile works** — reviewer might be on a tablet at a workstation

### Achievement Gate to Move to Phase 6

You are ready for Phase 6 when:
- [ ] An operator can upload 3 files and see results without technical knowledge
- [ ] Every FAILED rule shows actual values from both documents
- [ ] PDF viewer shows the page where the field was found
- [ ] Operator can submit a correction in under 30 seconds
- [ ] Corrections are stored in the database with full context
- [ ] The app works on a 1280px wide laptop screen without horizontal scrolling

---

## 10. Phase 6 — Feedback & Self-Learning Loop (Days 26–28)

**Goal:** Build the system that makes the software get smarter every time an operator uses it.

### The Learning Loop Explained Simply

```
Day 1: System extracts "96 Baell Trace Ct SE"
        Operator corrects: "This should be 96 Bell Trace Ct SE"
        → Training example stored:
          OCR input: "96 Baell Trace Ct SE"
          Correct output: "96 Bell Trace Ct SE"
          Pattern: "Baell" → "Bell" (OCR misread double-l as ll→ll with gap)

Day 7: System runs weekly ML retraining
        → New correction model trained with all 7 days of feedback
        
Day 8: New document comes in with same property
        System now corrects "Baell" → "Bell" automatically
        Operator sees correct result without having to correct it
        
Day 30: System has seen 300 corrections
         → 95% of common OCR errors corrected automatically
         → Operator only sees genuine errors, not OCR noise
```

### Three Levels of Learning

**Level 1 — Correction Dictionary (Immediate, No Training)**

Every operator correction immediately updates a dictionary:
- "Baell" → "Bell"
- "aP Code" → "Zip Code"
- "Borrovver" → "Borrower"

This is applied to ALL future documents the same day. No retraining needed. Simple string substitution.

**Level 2 — Field Extraction ML Model (Weekly Retraining)**

A small ML classifier that learns patterns:
- "Which regex pattern gives the best result for property address on pages with this layout?"
- "When OCR produces a word with two lowercase l characters back-to-back, is it likely a misread?"
- "What confidence score should we assign to addresses that end in a 5-digit number?"

This model is a simple scikit-learn classifier. It trains in seconds on your feedback data. It is retrained every Sunday night with the past week's corrections.

**Level 3 — Commentary Quality Model (Monthly Retraining)**

For the LLM fallback (when LLM is unavailable), train a small text classifier:
- Is this neighborhood description canned or specific?
- Does this market commentary have real analysis?

This uses the operator's responses from Screen 3 as labeled data. Every time an operator agrees with the LLM result or corrects it, that is a labeled example.

After 100 labeled examples: the classifier often beats the LLM for your specific market.

### What Gets Stored per Correction

```
feedback_events table:
  - feedback_id
  - document_id
  - rule_id               (which rule was involved)
  - field_name            (which extracted field)
  - original_ocr_text     (what OCR produced)
  - system_extracted_value (what extraction produced)
  - operator_provided_value (what the operator said is correct)
  - feedback_type         (OCR_ERROR / EXTRACTION_ERROR / RULE_ERROR / CORRECT)
  - operator_id
  - feedback_timestamp
  - used_in_training      (has this been included in a retraining run?)
  - training_run_id       (which training run used it)
```

### The Model Retraining Job

Every Sunday night, a background job runs:

```
1. Pull all feedback_events from the past 7 days where used_in_training = False
2. Build training dataset:
   - X (features) = OCR character patterns, word lengths, surrounding context
   - Y (labels) = operator-provided correct values
3. Retrain correction classifier
4. Validate on holdout set (last 10% of data)
5. If new model accuracy > current model accuracy: deploy new model
6. If worse: keep current model (do not downgrade)
7. Mark all used feedback_events as used_in_training = True
8. Send summary email: "Model retrained. Accuracy improved from X% to Y%"
```

### The Confidence Loop

After enough feedback, you can start showing operators when the system is very confident vs less confident:

- **Green bar (80–100% confidence):** System is almost certainly right. Operator can approve quickly.
- **Yellow bar (50–80%):** System thinks it's right but please verify.
- **Red bar (0–50%):** System is guessing. Human must look at the actual PDF.

The confidence score improves over time as the ML model learns. In month 1, everything might be yellow. By month 6, most fields are green.

### Achievement Gate to Move to Phase 7

You are ready for Phase 7 when:
- [ ] Operator corrections are stored in database with full context
- [ ] A correction dictionary applies corrections to future documents on the same day
- [ ] A test ML model trains without errors on synthetic feedback data
- [ ] The weekly retraining job runs without errors (can be tested manually)
- [ ] Confidence scores are shown in the UI and update based on feedback history

---

## 11. Phase 7 — Polish, Test & Deploy (Days 29–30)

**Goal:** Make it production-ready. Not more features. Quality of existing features.

### What "Production Ready" Means

1. **It doesn't crash** — every error is caught and shown gracefully
2. **It doesn't slow down** — tested with 5 simultaneous uploads
3. **It is secure** — no public endpoints, API key required
4. **It can be restored** — database is backed up automatically
5. **You can monitor it** — you can see how many requests failed today

### The Deployment Checklist

**Security:**
- [ ] API key required for every endpoint (add `X-API-Key` header)
- [ ] CORS restricted to Java backend IP (not `allow_origins=["*"]`)
- [ ] Temp files deleted immediately after processing
- [ ] Database user has minimum required permissions
- [ ] Secrets in environment variables, not code

**Performance:**
- [ ] 5 simultaneous uploads tested — all complete under 20 seconds each
- [ ] Database has indices on document_id and feedback queries
- [ ] OCR cache working (duplicate file processes in under 1 second)

**Reliability:**
- [ ] Postgres automated daily backup configured
- [ ] Docker restarts services if they crash (`restart: always`)
- [ ] Health check endpoint monitored

**Observability:**
- [ ] Every request logs: request_id, duration, status, error (if any)
- [ ] Simple dashboard shows: requests today, failures today, average processing time
- [ ] Alert sent if error rate exceeds 5% in any hour

**Documentation:**
- [ ] README explains how to deploy from scratch
- [ ] Each rule is documented (what it checks, why it matters)

---

## 12. When to Use OCR vs LLM vs ML — Decision Guide

Keep this reference card and consult it whenever you add a new feature:

### Decision Tree

```
NEW TASK: What tool should I use?
    │
    ├── Is the input a PDF image or scanned document?
    │       YES → Must use OCR first to get text
    │       NO (digital PDF) → Use PyMuPDF embedded text, no OCR
    │
    ├── Am I comparing two text values for equality?
    │       YES → Use string comparison (no AI needed)
    │
    ├── Am I extracting a structured field (address, price, date)?
    │       YES → Use regex + pattern matching
    │              If pattern fails → ML correction model
    │              Never use LLM for field extraction
    │
    ├── Am I evaluating text quality? ("Is this canned?")
    │       YES → Use LLM (this is what LLM is good at)
    │              Always have keyword-based fallback
    │
    ├── Am I correcting a known OCR error pattern?
    │       YES → Use ML correction model (trained on past corrections)
    │
    └── Am I classifying document type or section?
            YES → Use ML classifier (train on labeled examples)
            NO data yet → Use keyword matching until you have enough data
```

### The Cost of Getting This Wrong

| Wrong Choice | Cost |
|---|---|
| Using LLM for field extraction | Inconsistent results, 10× slower, expensive |
| Using OCR on digital PDF pages | 45 seconds instead of 0.01 seconds |
| Using regex for commentary quality | Misses real quality issues, reviewers lose trust |
| Not using ML for OCR correction | Same errors forever, reviewer frustration |

---

## 13. How the ML Model Learns From Feedback

This section goes deeper on the self-learning system.

### The Three ML Models You Will Train

**Model 1: OCR Correction Model**

Type: Sequence correction (character-level)
Input: Raw OCR text with potential errors
Output: Corrected text
Training data: Operator corrections from feedback_events table
When trained: Weekly (Sunday night job)
Initial state: Rule-based dictionary until 50+ training examples collected

What it learns:
- This form always prints "Zip Code" in a specific font. OCR sometimes reads it as "aP Code", "Zip Gode", "Zip C0de"
- "1" and "l" are confused when next to specific letters
- Certain cell border patterns cause OCR to merge two adjacent words

**Model 2: Field Confidence Model**

Type: Regression classifier
Input: Features about the extraction (method used, surrounding text quality, field length, etc.)
Output: Confidence score 0.0–1.0
Training data: Historical extractions where operator either confirmed or corrected the value
When trained: Weekly
Initial state: Rule-based confidence scoring (already in your system)

What it learns:
- When OCR confidence for the page is above 0.75 AND the field is on page 1 AND it's an address field → confidence is usually high
- When there are many special characters near the field → confidence should be lower

**Model 3: Commentary Quality Classifier**

Type: Text binary classifier
Input: Commentary text snippet (neighborhood, market conditions, etc.)
Output: CANNED or SPECIFIC (with probability)
Training data: Operator agreements/disagreements with LLM classification
When trained: Monthly (needs more data than other models)
Initial state: LLM API call (Phase 4)

What it learns:
- Phrases that are always canned for Georgia appraisals specifically
- Phrases that look canned but are actually market-specific in your area

### How to Collect Good Training Data From Day 1

Do not wait until Phase 6 to start collecting training data. From Day 1 of Phase 5 (operator UI), store every operator interaction:

- Did the operator agree with the system's result? → Positive training example
- Did the operator correct something? → Negative training example + correction label
- Did the operator flag something the system missed? → Gap training example

Even before you train any model, this data is valuable. In month 2, you will have hundreds of labeled examples that make training very fast and accurate.

### Model Performance Tracking

Store in database:
- Model version (date + accuracy score)
- Accuracy on holdout set
- Number of training examples used
- Which field types improved vs degraded

Never deploy a new model version that performs worse than the current one. Always keep the previous version as a rollback option.

---

## 14. Phase Achievement Gates

### Summary of All Gates

Use this as your weekly checklist. Do not start the next phase until the current gate is fully passed.

| Phase | Gate | Day Target |
|-------|------|-----------|
| 0 — Foundation | Docker starts, health check passes, DB created | Day 3 |
| 1 — OCR | 27-page doc in <15s, caching works, all text stored | Day 8 |
| 2 — Extraction | All fields extract correctly, confidence scores stored | Day 13 |
| 3 — Rules | All 17 rules run, results match human reviewer | Day 18 |
| 4 — LLM | Commentary rules work, fallback activates when LLM down | Day 21 |
| 5 — UI | Operator can use without training, corrections stored | Day 25 |
| 6 — Learning | Corrections flow into retraining, confidence updates | Day 28 |
| 7 — Production | Secure, monitored, backed up, documented | Day 30 |

### What Counts as "Done" for Phase 1

Many developers rush through phases without really completing them. Here is the strict definition:

**Phase 1 is done when:**
- You process your 3 real test documents (96 Baell Trace, 2307 Merrily, 8234 E Pearson)
- All 3 complete in under 15 seconds
- The raw OCR text for every page is in the database
- The per-page confidence score is in the database
- The OCR method (EMBEDDED vs TESSERACT) is in the database
- Processing the same document twice uses the cache (second time: under 1 second)
- You can look in the database and see the exact text from page 7 of any document

If any of those are not true, Phase 1 is not done.

---

## 15. Daily Hours Plan

You have AI tools to accelerate development. Here is a realistic plan:

### Overall Time Budget

30 days × 4–6 hours = 120–180 hours total investment.

With AI pair programming (Claude, Cursor, etc.) you can move 2–3× faster on boilerplate and standard patterns. The hard parts where you will spend time regardless:
- Getting OCR quality right for your specific form type
- Debugging regex patterns on real documents
- UI/UX for operator workflow
- Testing and finding edge cases

### Day-by-Day Hour Estimate

| Days | Phase | Daily Hours | Why |
|------|-------|-------------|-----|
| 1–3 | Phase 0 Foundation | 4 hours/day | Mostly mechanical setup. AI can scaffold most of this. |
| 4–8 | Phase 1 OCR | 5 hours/day | OCR tuning requires iteration on real documents |
| 9–13 | Phase 2 Extraction | 5 hours/day | Regex tuning on real data, debugging address parser |
| 14–18 | Phase 3 Rules | 4 hours/day | Logic is clear; mostly writing and testing rule functions |
| 19–21 | Phase 4 LLM | 3 hours/day | Small scope. Prompt engineering + fallback logic |
| 22–25 | Phase 5 UI | 6 hours/day | UI takes time even with AI. Real-world usability testing. |
| 26–28 | Phase 6 Learning | 5 hours/day | ML setup, training pipeline, feedback loop testing |
| 29–30 | Phase 7 Deploy | 6 hours/day | Docker, security, backup, monitoring — all need attention |

### Total: ~132 hours over 30 days

This is 4.4 hours per day average. Achievable with AI assistance.

### Where AI Tools Save You the Most Time

| Task | Without AI | With AI |
|------|-----------|---------|
| Project scaffolding | 8 hours | 1 hour |
| Database model setup | 4 hours | 30 minutes |
| API endpoint boilerplate | 6 hours | 1 hour |
| Frontend component creation | 10 hours | 3 hours |
| Test case writing | 8 hours | 2 hours |
| Docker configuration | 3 hours | 30 minutes |
| **Total saved** | — | **~25 hours** |

### Where AI Cannot Replace Your Judgment

- Deciding which OCR approach works best for your specific form type
- Tuning regex patterns against real appraisal documents
- Designing the operator workflow (you understand appraisals, AI doesn't)
- Debugging why a rule fails on one document but passes on another
- Deciding when the ML model is accurate enough to trust

---

## 16. What Makes This Better Than HomeVision

HomeVision is good but you can beat it in specific ways:

| Feature | HomeVision | Your System |
|---------|-----------|-------------|
| Self-learning from corrections | Unknown | ✅ Built in from day 1 |
| Per-field confidence score | Unknown | ✅ Every field has a score |
| OCR result caching | Unknown | ✅ Hash-based cache |
| Real-time processing progress | Unknown | ✅ WebSocket progress |
| Rule explanation with source page | Basic | ✅ Shows exact page and text |
| Parallel page OCR | Unknown | ✅ 4 pages simultaneous |
| Feedback loop retraining | Unknown | ✅ Weekly retraining |
| PDF viewer in results screen | Unknown | ✅ Click to see source |
| Rule on/off without code change | No | ✅ Database-driven |
| Full raw OCR text stored | Unknown | ✅ Every page stored |

The biggest advantage you can build is the **self-learning loop**. HomeVision gives static results. Your system gets better every day. After 6 months of operation, your system will be trained on your specific clients, your specific markets, and your specific OCR patterns. That is something HomeVision cannot offer.

---

## 17. Risk Register

These are the things most likely to cause delays. Know them in advance.

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| OCR quality is poor on your specific form type | MEDIUM | HIGH | Test OCR on all 3 documents in Phase 1 before going further |
| LLM API has downtime | LOW | MEDIUM | Fallback to keyword detection (Phase 4 requirement) |
| Regex fails on edge case documents | HIGH | MEDIUM | Build from 3 test docs, add more tests before Phase 7 |
| UI takes longer than expected | MEDIUM | MEDIUM | Use a component library (shadcn/ui) to speed up |
| ML model does not improve accuracy | LOW | LOW | Start simple (dictionary), grow slowly |
| Phase 5 UI usability is poor | MEDIUM | HIGH | Test with an actual operator before Phase 7 |
| Docker networking issues in deployment | MEDIUM | MEDIUM | Test deploy in staging environment by Day 25 |

### The One Rule to Not Break

> **Never skip the achievement gate to move faster.**

The gates exist because each phase builds on the previous one. If your OCR text is poor quality (Phase 1), every phase after it will be affected. If you skip to Phase 3 and come back to fix Phase 1, you waste 3× the time.

The gates are not bureaucracy. They are the fastest path to a working system.

---

## Appendix A — Technology Decisions Summary

| Component | Choice | Reason |
|-----------|--------|--------|
| API framework | FastAPI | Already in use, async, fast |
| PDF text extraction | PyMuPDF | Best embedded text quality |
| OCR engine | Tesseract | Free, local, good quality |
| Image preprocessing | OpenCV | Industry standard, fast |
| LLM | Claude API (with local Llama fallback) | Best quality + local backup |
| ML framework | scikit-learn → PyTorch | Simple start, grow as needed |
| Database | PostgreSQL | Reliable, good JSON support |
| Job queue | Celery + Redis | Proven, handles async OCR |
| Frontend | Next.js + shadcn/ui | Fast to build, professional |
| Deployment | Docker + single VPS | Simple, cheap |
| Monitoring | Simple logging + dashboard | Start simple |

## Appendix B — Your 3 Most Important Fixes (Do First in Phase 1)

These fix the problems in your current report immediately:

1. **Fix the zip code parser** — anchor on 5-digit pattern, not on the word "Code"
2. **Save raw OCR text per page** — without this, you cannot train the ML model
3. **Wire in `ThreadPoolExecutor`** — this is already in your config, just not used — 4× speedup immediately

---

*Plan prepared 2026-04-25. Based on live system analysis of 96 Baell Trace Ct SE.pdf (27 pages, 45.5s, 17 rules).*  
*Target: Production-ready appraisal QC platform in 30 days with self-learning ML layer.*
