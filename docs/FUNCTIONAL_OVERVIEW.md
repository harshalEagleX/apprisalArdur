# SHAL Platform — Functional Overview

A complete walkthrough of how the system works: from a user uploading a batch, through Java orchestration, Python OCR/QC processing, reviewer verification, and audit recording. Written for engineers who want to understand the *why* and *how* of each layer.

---

## Table of Contents

1. [System Architecture at a Glance](#1-system-architecture-at-a-glance)
2. [What the User Sees — UI Screens & Flows](#2-what-the-user-sees--ui-screens--flows)
3. [Security Layer — Authentication & Authorisation](#3-security-layer--authentication--authorisation)
4. [Batch Lifecycle — End-to-End](#4-batch-lifecycle--end-to-end)
5. [ZIP Ingestion & Volume Handling](#5-zip-ingestion--volume-handling)
6. [Java → Python Bridge (QC Submission)](#6-java--python-bridge-qc-submission)
7. [Python OCR Extraction Pipeline](#7-python-ocr-extraction-pipeline)
8. [Python QC Rules Engine](#8-python-qc-rules-engine)
9. [XML Handling](#9-xml-handling)
10. [Result Persistence — Java Side](#10-result-persistence--java-side)
11. [Reviewer Verification Workflow](#11-reviewer-verification-workflow)
12. [Real-Time Notifications (WebSocket)](#12-real-time-notifications-websocket)
13. [Audit Trail](#13-audit-trail)
14. [Analytics & Doc Stats](#14-analytics--doc-stats)
15. [Client Management](#15-client-management)
16. [Stuck-Batch Recovery](#16-stuck-batch-recovery)
17. [Reviewer Field Corrections (Python)](#17-reviewer-field-corrections-python)
18. [AMC Profile & Self-Learning Confidence](#18-amc-profile--self-learning-confidence)
19. [Confidence Routing & Auto-Threshold Tuning](#19-confidence-routing--auto-threshold-tuning)
20. [Cross-Document Consistency Checker](#20-cross-document-consistency-checker)
21. [Semantic Validator](#21-semantic-validator)
22. [Layer-B Narrative LLM Assessment](#22-layer-b-narrative-llm-assessment)
23. [Photo Analysis (Gemini / Google Vision)](#23-photo-analysis-gemini--google-vision)
24. [Python QC Response Assembly](#24-python-qc-response-assembly)
25. [Operator Sessions](#25-operator-sessions)
26. [Admin Impersonation](#26-admin-impersonation)
27. [File Serving & Profile Management](#27-file-serving--profile-management)
28. [Dashboard Service — Role-Scoped Payloads](#28-dashboard-service--role-scoped-payloads)
29. [Appraisal Transaction Layer](#29-appraisal-transaction-layer)

---

## 1. System Architecture at a Glance

```
Browser (Next.js)
      │  REST / WebSocket
      ▼
Spring Boot Java App  (multi-module Maven)
      │
      ├── user module     — auth, JWT, user/client CRUD
      ├── batch module    — ZIP ingestion, BatchFile records
      ├── qc module       — QC orchestration, Python bridge
      ├── common module   — shared entities, repos, events
      └── app module      — Spring Security config, WebSocket, metrics
                │
                │  HTTP (REST + Celery polling)
                ▼
      FastAPI + Celery Python Service  (ocr-service)
                │
                ├── L0–L5 extraction pipeline (pdfplumber → PaddleOCR → UAD template …)
                ├── QC rules engine (200+ UAD rules)
                └── PostgreSQL (SQLAlchemy)

Shared storage: local filesystem /uploads  (PDFs)
Database:       PostgreSQL  (JPA/Hibernate + SQLAlchemy)
Cache:          Caffeine (Java, 30s TTL) + Redis (rate-limit, cluster coordination)
Async:          Spring @Async thread pool + Celery (Python tasks)
Realtime:       WebSocket /ws/qc  (per-batch progress)
```

---

## 2. What the User Sees — UI Screens & Flows

### Roles

Two roles exist in the `Role` enum — `ADMIN` and `REVIEWER`. There is no "super-admin" or "CLIENT" role in code:

| Role | What they can do |
|------|-----------------|
| **ADMIN** | Upload batches, assign reviewers, manage users/clients, view all analytics, approve overrides, see audit graphs, impersonate users |
| **REVIEWER** | See their review queue, verify QC results for assigned batches, save decisions, sign off |

`Client` is a **data entity** (AMC/lender that owns batches), not a role. A user may be scoped to a specific Client, which filters dashboard data — this scoping is enforced at the service layer, not by a third role.

### Admin Screens

| Screen | Path | Purpose |
|--------|------|---------|
| Dashboard | `/admin` | Live KPI stats (batch counts by status), system signals, workload overview |
| Batches list | `/admin/batches` | Filterable/sortable table of all batches; bulk QC submit, delete, assign reviewer |
| Batch detail | `/admin/batches/[id]` | Full drilldown: files, QC results, processing timeline, history drawer, recovery drawer |
| Clients | `/admin/clients` | Create/edit client accounts that own batches |
| Client detail | `/admin/clients/[id]` | Single client's metadata + associated batches |
| Users | `/admin/users` | Create/edit user accounts (role, email, client assignment) |
| Doc Stats | `/admin/doc-stats` | QC performance analytics per document; four panels (appraisals, timing, rules, ML) |
| Overrides | `/admin/overrides` | Toggle QC rule severity overrides at runtime |
| Analytics | `/analytics` | Batch processing metrics, reviewer performance, model performance charts |

### Reviewer Screens

| Screen | Path | Purpose |
|--------|------|---------|
| Queue | `/reviewer/queue` | Active assignments + submitted reviews |
| Verify | `/reviewer/verify/[id]` | Core review page: PDF viewer, QC rules grouped by section, evidence comparison |
| Submitted detail | `/reviewer/submitted/[id]` | Read-only view of a completed review |

### Shared UI Components

- **StatusBadge** — colour-coded badge mapping every batch/file status to a colour
- **StatCard** — dashboard KPI tile (label + value + icon + colour)
- **Skeleton / Spinner** — loading states
- **ConfirmDialog** — destructive-action confirmation with typed confirmation guard
- **NotificationBell** — live WebSocket-driven toast notifications
- **useBatchPolling** — adaptive polling hook that checks QC processing status; backs off when not needed
- **useWebSocket** — maintains the WebSocket connection and emits events to subscribers
- **useReviewSession** — keeps the review session lock alive via heartbeat calls

---

## 3. Security Layer — Authentication & Authorisation

### Login Flow

```
POST /api/auth/login
  └─ AuthController
       └─ AuthenticationService.authenticate()
            ├─ Spring AuthenticationManager validates username/password
            ├─ JwtUtils.generateToken()  — 24-hour JWT
            └─ Sets shal_jwt cookie (HttpOnly) + returns token in body
```

The JWT is stored in an **HttpOnly cookie** (`shal_jwt`). The frontend also reads it from the response body for the `Authorization: Bearer` header on API calls.

### Per-Request JWT Validation

Every API request passes through `JwtAuthenticationFilter` (a `OncePerRequestFilter`):

1. Looks for JWT in `shal_jwt` cookie **or** `Authorization: Bearer` header.
2. Calls `JwtUtils.validateToken()` — checks signature + expiry.
3. Calls `CustomUserDetailsService.loadUserByUsername()` — loads the `User` entity from DB.
4. Wraps it in `UserPrincipal` (Spring `UserDetails`) and sets it in `SecurityContextHolder`.

### Security Configuration (`SecurityConfig`)

Two filter chains are defined:

| Chain | Matches | Rules |
|-------|---------|-------|
| API chain | `/api/**` | Stateless JWT, CORS enabled, specific roles per endpoint |
| Web chain | Everything else | Session-based Thymeleaf views for profile pages |

Role-based rules:

- `/api/admin/**` → `ADMIN` only
- `/api/reviewer/**` → `REVIEWER` only
- `/api/auth/**` → public (login, register)
- `/ws/qc` → authenticated (validated via `WebSocketAuthHandshakeInterceptor`)

### Rate Limiting

`AuthRateLimitFilter` enforces a **sliding-window in-memory rate limit** on `/api/auth/login` to prevent brute-force attacks.

### Security Events

`SecurityEventListener` listens to Spring Security login-success, login-failure, and logout events and writes them to the `AuditLog` table. It also calls `OperatorSessionService` on login to start a new operator session record.

### Admin Seeder

On startup, `AdminSeeder` checks if any ADMIN user exists and creates a default one if not — it logs a warning if the default password is still in use.

---

## 4. Batch Lifecycle — End-to-End

A batch moves through **eight forward-only states** (see `BatchStatus.java`):

```
UPLOADED ──► VALIDATING ──► VALIDATION_FAILED   (dead end)
                       │
                       └──► QC_PROCESSING ──► COMPLETED        (all rules auto-pass)
                                          ├──► REVIEW_PENDING  (FAIL/VERIFY items exist)
                                          │       └──► IN_REVIEW ──► COMPLETED
                                          │                     └──► ERROR
                                          └──► ERROR            (system failure)
```

Note: there is no `SUBMITTED`, `FAILED`, `PENDING`, or `CANCELLED` state in code.
`ERROR` is the only terminal failure state and can be entered from two paths:
(a) a system error during QC processing, or (b) a reviewer submitting a final rejection.
The batch must be re-submitted (re-run QC) to escape ERROR — it is not permanent.

### Step-by-Step Flow

```
1. ADMIN uploads ZIP  →  BatchApiController.uploadBatch()
2. BatchService.uploadBatch()
     ├─ Computes ZIP hash (SHA-256) — duplicate detection
     ├─ Creates Batch entity (status = VALIDATING)
     ├─ extractAndValidateZip() — classifies files into APPRAISAL/ENGAGEMENT/CONTRACT/APPRAISAL_XML
     ├─ Reads manifest.json from ZIP if present → links batch to AppraisalTransaction
     └─ Saves Batch + BatchFile entities (status = UPLOADED on success)

3. ADMIN clicks "Run QC"  →  QCApiController.submitBatch()
4. QCProcessingService.processBatchAsync()  [runs on @Async thread pool]
     ├─ claimBatchForProcessing()  — atomically sets status = QC_PROCESSING (prevents race)
     ├─ FileMatchingService.getMatchedPairs()  — pairs appraisal PDFs with engagement/contract PDFs
     ├─ For each file pair → processFilePair()
     │     ├─ PythonClientService.submitQCJob() or processQC()  — calls Python with client_id
     │     ├─ persistPythonResult()  — writes QCResult + QCRuleResult rows
     │     └─ saveMetrics()  — writes ProcessingMetrics row
     ├─ determineBatchStatus()  — aggregates file results → COMPLETED | REVIEW_PENDING | ERROR
     └─ Publishes WebSocket event → browser updates live

5. ADMIN assigns reviewer  →  BatchService.assignReviewer()
     └─ Batch status unchanged (reviewer assignment is a field, not a state transition)

6. REVIEWER opens review  →  VerificationService.beginReviewSession()
     └─ Batch status → IN_REVIEW

7. REVIEWER signs off  →  VerificationService (see §11)
     └─ Batch status → COMPLETED (all accepted) or ERROR (reviewer rejection)
```

---

## 5. ZIP Ingestion & Volume Handling

**Entry point:** `BatchApiController.uploadBatch()` — accepts a `MultipartFile` (ZIP).

**`BatchService.createFromZip()`** does the heavy lifting:

1. **`extractAndValidateZip()`**
   - Reads every ZIP entry without extracting to disk first.
   - Validates file types — only PDFs are accepted.
   - Reads folder hierarchy to infer **property-set names**: e.g., a ZIP with folders `PropA/`, `PropB/` creates two `PropertySet` groups.
   - Rejects malformed or empty ZIPs immediately.

2. **Property-set grouping**
   - Files are grouped by their top-level folder name inside the ZIP.
   - Each group becomes a logical property set attached to the `Batch`.
   - Within each group, files are classified as `APPRAISAL` or `SUPPORTING` (`FileType` enum).

3. **Persistence**
   - One `Batch` entity is created with status `PENDING`.
   - One `BatchFile` entity per PDF, pointing to its storage path on disk.
   - Files are written to the local `/uploads` directory (served via `WebConfig` at `/uploads/**`).

**Volume limits:**
- The `RestTemplateConfig` defines separate `RestTemplate` beans — one with a standard timeout for general API calls, one with an extended timeout specifically for calls to the Python OCR service (PDF processing can take seconds per page).
- The `@Async` thread pool (`AsyncConfig`) is bounded — it won't spawn unbounded threads for large batches; jobs queue internally.

---

## 6. Java → Python Bridge (QC Submission)

**Service:** `PythonClientService`

This service is the only point of contact between Java and Python.

### Sync vs Async Submission

```
PythonClientService.processQC(batchFile, modelConfig)
   │
   ├─ if Python service supports async (Celery):
   │     submitQCJob()  →  POST /qc/process-async
   │     waitForJobResult()  →  polls GET /qc/status/{jobId}
   │          ├─ exponential backoff polling
   │          └─ timeout → throws exception
   │
   └─ else (sync fallback):
         POST /qc/process  →  waits for full response
```

**What's sent (request body):**
- Absolute file paths for the appraisal PDF and supporting PDFs
- Model name + version (from `QCModelConfig` configuration properties)
- Transaction folder path

**What's returned (`PythonQCResponse`):**
- Per-document extraction results
- Per-rule results (`PythonRuleResult`) with: rule ID, status, severity, message, evidence list, timing
- Overall confidence scores
- Timing breakdown (`PythonTimings`)

**Health check:** `PythonClientService.isHealthy()` pings `GET /health` — used by the admin dashboard signal indicator.

**OCR service config** (`OcrServiceConfig`): holds the Python service base URL, timeout, and retry settings — all configurable via properties/env vars.

---

## 7. Python OCR Extraction Pipeline

The Python side processes a single PDF through multiple layers, each adding confidence to the extracted field values.

### Entry Points

| Entry Point | When used |
|-------------|-----------|
| `POST /qc/process` | Sync call — runs pipeline, returns response directly |
| `POST /qc/process-async` | Async — enqueues Celery task, returns job ID |
| `tasks.py: qc_process_task` | Celery worker picks up job, calls `pipeline_runner.py` |

### Pipeline Stages (`pipeline_runner.py`)

```
PDF input
   │
   ├─ 1. Document classification  (document_classifier.py)
   │       → keyword-based: is this an APPRAISAL / ENGAGEMENT / CONTRACT?
   │
   ├─ 2. Adaptive OCR  (adaptive_ocr.py)
   │       → detects digital vs scanned pages
   │       → scanned pages → PaddleOCR deep-learning OCR
   │       → digital pages → pdfplumber text extraction
   │
   ├─ 3. Table detection  (table_detector.py)
   │       → three strategies: line-based, drawing-based, heuristic
   │
   ├─ 4. Full field extraction  (orchestrator.py → L0–L5 layers)
   │
   ├─ 5. QC validation  (transaction.py → engine.py)
   │
   └─ 6. Persist to DB  (classification, page-OCR, extraction, validation rows)
```

### Extraction Layers (L0–L5) — run in parallel via thread pool

| Layer | File | What it does |
|-------|------|-------------|
| L0 | `l0_pdfplumber.py` | Opens PDF with pdfplumber; extracts structured word positions and text. Foundation for all other layers. |
| L1 | `l1_checkbox_visual.py` | Renders pages to images (PyMuPDF); detects checked checkboxes visually (diagonal line crossing detection). |
| L2 | `l2_grid_resolver.py` | Extracts UAD grid fields (price/age ranges, land-use percentages) from table structures. |
| L3 | `l3_paddle_ocr.py` | Applies PaddleOCR on scanned pages to recover text that pdfplumber cannot read. |
| L4 | `l4_camelot.py` | Uses Camelot PDF table parser to extract comparable-sales grid data. |
| L5 | `l5_uad_template.py` | The most comprehensive layer (1 231 lines). Template-based UAD form field extraction covering every standard appraisal field. |

### Post-Extraction Merging

After all layers run:

1. **`extraction_merger.py`** — merges L0–L5 results per field using agreement patterns; higher-confidence layers win.
2. **`document_reconciler.py`** — deduplicates results across pages for the same field.
3. **`field_locator.py`** — finds bounding-box coordinates for located fields (used in the reviewer PDF viewer).

### Specialist Overlays (run after base extraction)

These run on top of the base extraction to fill gaps or improve accuracy:

| Overlay | Purpose |
|---------|---------|
| `embedding_extractor.py` | Semantic embedding-based extraction using SentenceTransformer — finds fields by semantic similarity |
| `form_llm_extractor.py` | LLM gap-fill: groups missing fields by form section, sends page text to Groq LLM |
| `spatial_extractor.py` | High-precision spatial extraction using word-position maps and anchoring |
| `sca_llm_extractor.py` | Groq LLM specifically for the Sales Comparison Approach grid |
| `sketch_extractor.py` | Extracts Gross Living Area from sketch pages (three strategies: template match, OCR, LLM) |
| `narrative_extractor.py` | Extracts sales-comparison narrative text |
| `comp_photo_extractor.py` | Detects comparable-sale photo pages |
| `checkbox_extractor.py` | Focused checkbox detection using PyMuPDF drawing analysis |
| `contract_extractor.py` | Extracts structured fields from purchase contract PDFs |
| `engagement_extractor.py` | Extracts engagement-letter fields (borrower, address, loan type) |
| `comp_grid_extractor.py` | Extracts the comparable sales grid using spatial word analysis |

### LLM Calls (Groq)

`llm_groq.py` wraps the Groq API with:
- **Redis-backed caching** (plus local in-memory fallback) — same prompt = cached response
- **Token-per-minute rate throttling** — prevents hitting Groq's rate limits
- **LLM telemetry** (`llm_telemetry.py`) — thread-local span tracking for timing and token counts

---

## 8. Python QC Rules Engine

After extraction, `transaction.py` builds a `QCContext` and runs the rule engine.

### QCContext

`context.py` defines two objects:

- **`DocView`** — field-level accessor for a single document's extraction results; provides `.get(field_name)` with confidence scores
- **`QCContext`** — holds all `DocView` instances for a transaction (appraisal + engagement + contract)

### Rule Registration

`registry.py` provides a `@rule` decorator. Every rule module imports it and decorates its rule function:

```python
@rule(id="S1", section="Subject", severity="error", phase="extraction")
def s1_address(ctx: QCContext) -> RuleResult:
    ...
```

`__init__.py` in `rules/` side-effect-imports all rule modules, registering ~200+ rules.

### Engine Execution (`engine.py: run_qc`)

```
For each registered rule:
   ├─ Phase filter  — skip rules for a different phase
   ├─ Section gate  — skip rules whose section already failed completely
   ├─ call rule_function(ctx)
   ├─ catch any exception → mark rule as ERROR (never crash the whole run)
   └─ collect RuleResult

After all rules:
   ├─ _escalate_sections()  — if a section has enough failures, add a synthetic section-FAIL result
   └─ persist_report()  — writes all results to the DB via SQLAlchemy
```

### Rule Modules (domain breakdown)

| Module | Rules | What they check |
|--------|-------|----------------|
| `global_rules.py` | g0 | Engagement document present |
| `subject.py` | S1–S12 | Property address, borrower identity, intended use, assignment type, effective date |
| `site.py` | ST1–ST10, ST1B | Site dimensions, area, shape, UAD codes |
| `neighborhood.py` | N1–N5 | Neighborhood characteristics, trend direction, boundaries |
| `improvements.py` | i1–i34 | Foundation, materials, general fields |
| `sales_comparison.py` | (largest — 1 336 lines) | All UAD SCA checks: comparable addresses, dates, prices, adjustments, grid consistency |
| `reconciliation.py` | R1, R2, CA1–CA3, IA1 | Reconciliation, cost approach, income approach |
| `commentary.py` | n6, n7, add1 | Narrative text quality, market conditions |
| `contract.py` | c_exec, c1–c4 | Contract analysis, price/date, data source |
| `addendum.py` | add2, add5 | Addendum SCA selection, MCA required fields |
| `signature.py` | SIG1–SIG4, DOC1 | Appraiser credentials, signature blocks |
| `photos.py` | PH1, PH2, FHA9 | Required photo presence |
| `fha_usda.py` | FHA-specific | Case number format, intended use, economics |

### Rule Results

Each rule produces a `RuleResult`:

```python
@dataclass
class RuleResult:
    rule_id: str
    status: RuleStatus     # PASS / FAIL / WARNING / ERROR / SKIP
    severity: str          # error / warning / info
    message: str           # human-readable explanation
    evidence: list[Evidence]  # extracted values shown as evidence
    timing: RuleTiming     # how long the rule took
```

`Evidence` captures the actual extracted field value vs expected, with a source label so the reviewer can see exactly what the OCR read.

---

## 9. XML Handling

XML appears in two places in this system:

### 1. Spring Boot Maven Multi-Module Build (`pom.xml`)

The Java project is structured as a Maven multi-module project. Each module (`common`, `user`, `batch`, `qc`, `app`) has its own `pom.xml`. The `app` module's POM is the assembly point that brings all modules together.

Hibernate/JPA mapping annotations drive the schema — there are no Flyway or Liquibase XML migration files. Schema changes use `spring.jpa.hibernate.ddl-auto=update` for auto-managed tables.

### 2. UAD Form Template Matching (Python Layer 5)

`l5_uad_template.py` (1 231 lines) contains the most comprehensive extraction layer. UAD (Uniform Appraisal Dataset) forms have a known field layout. The template extractor:

- Uses spatial word-position maps to locate fields by their expected position on the form
- Handles both digital PDFs (exact coordinates) and scanned PDFs (approximate positions after OCR alignment)
- Reads field definitions from `schema.py` — a YAML-backed schema loader that defines every extractable field, its synonyms, and acceptable value patterns

The schema YAML acts as the single source of truth for what fields exist, where they should appear, and what valid values look like. Rule helpers in `helpers.py` (`format_regex`, `boolean_is_yes`, etc.) compile these patterns for use inside QC rules.

---

## 10. Result Persistence — Java Side

When `PythonClientService` returns a `PythonQCResponse`, `QCProcessingService.persistPythonResult()` translates it into the Java domain model:

### Entities Created

| Entity | What it holds |
|--------|--------------|
| `QCResult` | One record per processed file. Holds overall status, confidence, Python response JSON, model version, timing. |
| `QCRuleResult` | One record per rule per file. Holds rule ID, status, severity, message, evidence JSON. Hibernate Envers tracks its revision history. |
| `ProcessingMetrics` | OCR latency, total duration, retry count for this file. |
| `DocumentMatch` | Links an appraisal `BatchFile` to its matching engagement and contract `BatchFile`. |

### Envers Audit on QCRuleResult

`QCRuleResult` is annotated with `@Audited` (Hibernate Envers). Every update to a rule result — including reviewer decisions — creates a new revision row. `AppRevisionEntity` extends the default revision to capture: username, IP address, and correlation ID.

`EnversAuditService` queries these revision rows to compute a "diff" of changes over time, used by the audit graph and batch history drawer.

---

## 11. Reviewer Verification Workflow

### How a Reviewer Gets Work

1. Admin assigns a reviewer to a batch (`BatchService.assignReviewer()`).
2. Batch status moves to `IN_REVIEW`.
3. Batch appears in the reviewer's queue page (`/reviewer/queue`).

### Review Session Lock

Before a reviewer can save decisions, they must claim the QC result exclusively:

```
POST /api/reviewer/session/start/{qcResultId}
  └─ VerificationService.beginReviewSession()
       ├─ Checks no other reviewer currently holds the lock
       ├─ Issues a session token (UUID) with a TTL
       └─ Saves token + expiry on the QCResult
```

The frontend's `useReviewSession` hook sends heartbeat calls (`PUT /api/reviewer/session/heartbeat/{token}`) every N seconds to keep the lock alive. If the reviewer closes their browser without finishing, the lock expires and another reviewer can claim it.

### Saving Decisions

```
POST /api/reviewer/decision/{qcRuleResultId}
  └─ ReviewerApiController.saveDecision()
       └─ VerificationService.saveDecision()
            ├─ Validates session token ownership
            ├─ Records PASS / FAIL decision on QCRuleResult
            └─ Writes BusinessEvent (reviewer_decision)
```

The `RuleCard` component shows each rule with: the QC engine's verdict, the extracted evidence, a diff comparison (EvidenceCompare), and the reviewer's pass/fail button.

### Sign-Off

```
POST /api/reviewer/submit/{qcResultId}
  └─ ReviewerApiController.submitSavedReview()
       └─ VerificationService.submitVerification()
            ├─ Validates all rules have been decided
            ├─ Releases session lock
            ├─ Sets FinalDecision (PASS / FAIL) on QCResult
            ├─ Records BusinessEvent (verification_complete)
            └─ Triggers batch status recomputation
```

The `SignOffDialog` component forces the reviewer to confirm the overall outcome before submitting.

### Override Workflow

If a reviewer disagrees with the engine, they can request an override. An admin uses the Overrides page (`/admin/overrides`) to approve or reject it:

```
POST /api/reviewer/override/{qcRuleResultId}
  └─ ReviewerApiController.decideOverride()
       └─ VerificationService  — marks override approved/rejected
```

---

## 12. Real-Time Notifications (WebSocket)

### Connection Setup

The frontend's `useWebSocket` hook connects to `ws://.../ws/qc?token=<JWT>`.

`WebSocketAuthHandshakeInterceptor` validates the JWT from the query parameter during the WebSocket upgrade request. Only authenticated users get a connection.

`WebSocketConfig` registers `QcWebSocketHandler` at `/ws/qc`.

### Topic Subscription

After connecting, the client subscribes to specific batch IDs it cares about:

```
SUBSCRIBE batch:<batchId>
```

`QcWebSocketHandler` maintains a map of `batchId → Set<session>`. When a session subscribes to a batch, it's added to that batch's listener set.

### Publishing Events

`WebSocketRealtimeEventPublisher` implements `RealtimeEventPublisher`. When `QCProcessingService` completes processing a file or changes a batch status, it calls:

```java
realtimeEventPublisher.publish(batchId, eventType, payload)
```

This pushes a JSON message to every WebSocket session subscribed to that batch.

### Frontend Reaction

`useBatchPolling` hook reacts to WebSocket events: on a status-change event, it triggers an immediate re-fetch of batch data. The batch detail page and status badges update in real time without the user refreshing.

---

## 13. Audit Trail

The system has three separate audit mechanisms:

### 1. AuditLog — Administrative Actions

`AuditLog` entity records: who did what, to which entity, from which IP, at what time.

`AuditLogService` is called from:
- `SecurityConfig` on login/logout
- Admin controllers when creating/editing users, clients, batches

The admin batch detail page shows a paginated audit log (`getBatchAuditLog()`).

### 2. BusinessEvent — Domain Events

`BusinessEvent` is a **write-once** entity (throws on `@PreUpdate` to prevent modification). It records:
- QC decisions made by the engine
- Batch state transitions (submitted, processing, completed)
- Reviewer decisions
- Override approvals/rejections

`BusinessEventService` creates these; `BusinessEventRepository` queries them by batch, file, and type.

### 3. Hibernate Envers — Field-Level Change History

`QCRuleResult` is `@Audited`. Every change creates a revision row in the Envers `_AUD` table. `AppRevisionEntity` attaches username, IP, and correlation ID to each revision.

`EnversAuditService.getQCResultHistory()` queries these revisions and computes diffs — showing exactly what changed between reviewer decisions and engine results.

### Audit Graph API (`AuditGraphController`)

Three graph-structure endpoints power the force-directed graph visualisations:

| Endpoint | What it returns |
|----------|----------------|
| `GET /api/audit/overview` | All QC results grouped by batch as a graph — nodes are batches/files/decisions |
| `GET /api/audit/batch/{id}` | Focused graph for one batch: files, QC runs, and decision nodes |
| `GET /api/audit/reviewer/{id}` | Graph centred on a reviewer — all their batches and decisions |

### Correlation IDs

`CorrelationIdFilter` injects a correlation ID into every request (from an incoming header or freshly generated). It is stored on the Envers revision entity, logged in all request-scoped log lines, and included in `AuditLog` entries, making it possible to trace a single user action across all three audit systems.

---

## 14. Analytics & Doc Stats

### AnalyticsService

Aggregates data for eight analytics dimensions:
- Batch processing metrics (throughput, failure rate)
- Reviewer performance (decisions/hour, accuracy)
- ML model performance (confidence distributions)
- Operator productivity metrics

All eight are exposed via `AnalyticsApiController` under `/api/analytics/*`.

### DocStats

`DocStat` entity captures per-document QC telemetry: total time, rule execution time, OCR time, LLM time. Three sub-entities hold per-rule, per-section, and per-stage breakdowns:

- `DocStatRule` — time and pass/fail per rule
- `DocStatSection` — aggregated time per section
- `DocStatStage` — time per pipeline stage (L0 extraction, L3 OCR, LLM overlay, etc.)

`DocStatsThresholds` defines configurable warning thresholds (e.g., "if total QC time > X ms, flag as slow").

`DocStatsApiController` provides:
- Paginated document search with filters
- Batch-level aggregations
- Per-document detail (the `/admin/doc-stats/[id]` page)

### Micrometer Metrics (`QcMetrics`)

Exposes Gauge metrics to Prometheus/Micrometer for:
- Batch counts broken down by status (PENDING, PROCESSING, COMPLETED, etc.)

---

## 15. Client Management

`Client` entity represents an appraisal company. Every `Batch` belongs to a `Client`.

`ClientService` handles:
- Create/edit with duplicate-code prevention
- Listing all clients with their batch counts

`ClientRepository` supports lookup by `clientCode`.

ADMIN users are optionally associated with a client (for multi-tenancy filtering). `BatchApiController` asserts client ownership before allowing batch operations — a reviewer/admin can only touch batches belonging to their client unless they are a super-admin.

---

## 16. Stuck-Batch Recovery

`StuckBatchReconciler` is a scheduled Spring service that runs periodically. It:

1. Queries for batches stuck in `PROCESSING` status beyond a configurable timeout threshold.
2. For each stuck batch, checks `RedisClusterCoordinator` to see if any node is still actively working on it.
3. If no active worker is found, transitions the batch to `FAILED` with an error message.
4. Logs the recovery as an `AuditLog` entry.

`RedisClusterCoordinator` (and its in-memory fallback `InMemoryClusterCoordinator`) tracks which batches are actively being processed by which cluster node — used both for cancellation signalling and stuck-batch detection.

### Cancellation Flow

```
POST /api/qc/cancel/{batchId}
  └─ QCProcessingService.cancelBatch()
       ├─ Sets all non-terminal file statuses → CANCELLED
       ├─ Publishes cancel signal via ClusterCoordinator
       └─ processBatchAsync() checks the cancel signal between files and aborts
```

The admin can also trigger recovery manually via the `BatchRecoveryDrawer` component on the batch detail page.

---

---

## 17. Reviewer Field Corrections (Python)

When a reviewer spots a wrong OCR value, they can submit a **field-level correction** — not just a pass/fail on a rule, but an explicit "the correct value for this field is X".

**Entry point:** `POST /corrections` in `main.py` → `correction_service.save_correction()`

### What gets saved

Each correction row records:
- The document ID and field name
- The original extracted value and the reviewer-supplied correct value
- A reason category (e.g., `wrong_value`, `missing_value`, `format_error`)
- A link back to the `ExtractionResult` row that was wrong

### How corrections feed back

`get_correction_stats()` aggregates all correction rows into two frequency maps:
- **By reason** — which categories of errors occur most often
- **By field name** — which fields are most frequently wrong

These stats are surfaced in the admin Doc Stats pages and feed into the **auto-threshold tuning** system (see §19).

---

## 18. AMC Profile & Self-Learning Confidence

Different AMC (Appraisal Management Company) clients produce PDFs with slightly different layouts — field positions shift, fonts differ, forms may be from different software vendors. The AMC profile system learns from every processed document to improve accuracy over time.

**Service:** `amc_profile_service.py`

### Profile Learning

After each document is successfully processed, `update_profile_from_document()`:

1. Computes a **document fingerprint** — page count, average word density, form layout signals.
2. Calls `_fingerprint_similarity()` to find an existing AMC profile that matches (composite similarity score based on page count, layout, and word density).
3. If a match is found above a confidence threshold, it updates that AMC's profile with the new field location priors (which page a field typically appears on, where on the page).
4. If no match, it seeds a new profile row.

### Confidence Adjustment

`apply_amc_confidence_adjustment()` is called during extraction merging. It takes the raw confidence score for a field and adjusts it upward if:
- This AMC's profile shows the field is reliably at this page+position
- The AMC has a strong track record on this field

This means the system extracts fields with higher confidence on repeat clients without re-running LLM extractors unnecessarily.

---

## 19. Confidence Routing & Auto-Threshold Tuning

**Service:** `routing_config.py`

Every extracted field goes through a routing decision after extraction:

```
raw confidence score
       │
       ▼
get_thresholds(field_name, amc_id)
       │
       ├─ score ≥ auto_accept threshold  →  accepted automatically, no review needed
       ├─ score ≥ review threshold       →  flagged for reviewer attention
       └─ score < reject threshold       →  marked as extraction failure
```

### Threshold Hierarchy

AMC-level thresholds override global thresholds. This means a field that is easy to extract for AMC-A (high auto-accept threshold) can still be routed to review for AMC-B (lower threshold) without changing global defaults.

### Seeding Defaults

On startup, `seed_routing_config()` inserts default threshold rows for every field defined in the YAML schema, skipping any that already exist. This ensures new fields added to the schema get sensible defaults automatically.

### Auto-Tuning from Corrections

`auto_adjust_from_corrections()` runs periodically (or after a batch of corrections). For any field where the correction rate exceeds a configured ceiling, it **tightens the review threshold** — meaning more extractions for that field get routed to human review until accuracy improves. This is a feedback loop: high error rate → lower threshold → more review → corrections → AMC profile improves → error rate drops → threshold relaxes.

---

## 20. Cross-Document Consistency Checker

**Service:** `cross_document_checker.py`

After all documents in a transaction have been extracted, a cross-document consistency pass compares shared fields between them:

- **Address match** — property address in the appraisal report must match the address in the engagement letter and the purchase contract
- **Borrower name match** — borrower in the appraisal must match the engagement letter
- **Value consistency** — appraised value in the appraisal report must be consistent with the value referenced in the engagement letter

The checker uses the text normalisation library in `matching.py` for fuzzy comparisons — addresses are normalised (street abbreviations expanded, punctuation stripped) before comparing, so `"123 Main St."` matches `"123 Main Street"`.

Inconsistencies become `Evidence` entries attached to cross-document QC rules, surfaced in the reviewer's `EvidenceCompare` view.

---

## 21. Semantic Validator

**Service:** `semantic_validator.py`

Runs after field extraction and before the main QC rule engine. It applies cross-field semantic rules that the rule engine cannot easily express:

| Rule | What it checks |
|------|---------------|
| `rule_sem01_value_price_ratio` | Appraised value is within a configurable ratio tolerance of the contract price (e.g., must be within ±20%) |
| `rule_sem03_contract_before_effective` | Contract date must precede the appraisal effective date — catches impossible timeline errors |

`validate()` orchestrates all semantic rules against the full `ExtractionResultSet` and aggregates pass/fail/warning results. These flow into the `QCContext` alongside the standard per-field extractions.

---

## 22. Layer-B Narrative LLM Assessment

**Service:** `layer_b.py`

Some QC rules check not just whether a field is present, but whether the **narrative text** adequately explains a concern. Layer-B handles this:

```
QC concern (e.g., "unusual market condition flagged")
       │
       ▼
layer_b.assess(concern, narrative_text)
       │
       ├─ _llm_reasoning()
       │     ├─ SHA-1 hash of (concern + narrative) → Redis/in-memory cache lookup
       │     └─ if miss → Groq LLM call → cache result
       │
       └─ Returns: EXPLAINED / NOT_EXPLAINED / INCONCLUSIVE
```

This is used by commentary rules (N6, N7, ADD1) where a flag is acceptable only if the appraiser explicitly addresses it in the narrative. The LLM reads both the concern and the narrative and reasons about whether the concern is covered.

Caching is critical here — the same concern+narrative combination is common across a corpus of similar properties, so cache hit rates are high and LLM costs stay low.

---

## 23. Photo Analysis (Gemini / Google Vision)

**Service:** `analyzer.py` + `vision_client.py`

Photo QC rules (PH1, PH2, FHA9) check that required property photos are present. Beyond detection, the platform can also analyse photo *content* for quality signals.

### Multi-Backend Chain

`get_photo_analyzer()` builds an analyser chain based on the `VISION_BACKEND` config setting. The chain tries backends in order:

| Backend | When used |
|---------|-----------|
| **Gemini** (via REST) | Primary; uses Google Gemini Vision API for high-accuracy image understanding |
| **Google Cloud Vision** | Fallback if Gemini unavailable; uses `ImageAnnotatorClient` |

`vision_client.py` wraps the Google Cloud Vision client with:
- Lazy initialisation (no credentials error on startup if Vision isn't configured)
- Credential detection (checks for Application Default Credentials or a service account key file)

Photo detection results (is the front of the subject property shown? rear? street? interior?) are used as `Evidence` items in photo QC rule results.

---

## 24. Python QC Response Assembly

**Service:** `python_response.py`

After all rules run and the report is persisted, `report_to_python_qc_response()` converts the in-memory `QCReport + QCContext` into the JSON dict that gets returned to the Java `PythonClientService`.

### Structure of the response

```
{
  "documents": [
    {
      "doc_id": "...",
      "doc_type": "appraisal | engagement | contract",
      "extraction_confidence": 0.87,
      "rule_results": [
        {
          "rule_id": "S1",
          "status": "FAIL",
          "severity": "error",
          "message": "Street address missing",
          "evidence": [...],
          ...
        }
      ]
    }
  ],
  "timings": {
    "total_ms": 4200,
    "per_rule": { "S1": 12, "N1": 8, ... },
    "per_section": { "Subject": 180, ... },
    "per_stage": { "l0_pdfplumber": 310, "llm_sca": 1200, ... }
  }
}
```

`_build_timings()` assembles the timing breakdown from per-rule `RuleTiming` records and per-stage telemetry from `llm_telemetry.py`. This is what becomes the `PythonTimings` DTO on the Java side and ultimately populates the `DocStat` / `DocStatRule` / `DocStatStage` telemetry tables.

---

## 25. Operator Sessions

**Service:** `OperatorSessionService.java` + `OperatorSession` entity

Every time a user logs in, `startSession()` is called (triggered by `SecurityEventListener`):

1. Finds any currently `ACTIVE` or `IDLE` sessions for that user and closes them (marks end timestamp, computes active minutes).
2. Creates a new `OperatorSession` record with start timestamp and links it to the user.

This gives the analytics layer a factual record of when each operator was working, how long they spent per session, and how many batches they processed in a session.

`OperatorSessionRepository` exposes queries for:
- Sessions by user in a date range
- Sessions with their batch-interaction counts
- Aggregate active-minute totals per operator (used in the OperatorBar analytics chart)

---

## 26. Admin Impersonation

**Service:** `ImpersonationService.java`

Allows an ADMIN to temporarily act as another user — useful for debugging reviewer-specific issues or testing role-restricted views.

```
startImpersonation(targetUsername)
   ├─ Validates caller is ADMIN (throws AccessDeniedException if not)
   ├─ Loads the target user from UserRepository
   ├─ Pushes the current authentication onto a thread-local stack
   └─ Replaces SecurityContextHolder with a new Authentication for the target user

stopImpersonation()
   └─ Pops the stack and restores the original authentication
```

The thread-local stack means impersonation is:
- **Scoped to the current request thread** — other concurrent requests are not affected
- **Nestable** — an admin impersonating user A can impersonate user B, and unwinding goes back through A before returning to the admin

All actions taken while impersonating are still attributed in `AuditLog` to the target user's identity (since `SecurityContextHolder` holds the target). The admin's original identity is preserved only in the thread-local stack, not in any audit record.

---

## 27. File Serving & Profile Management

### File Serving (`FileController`)

`FileController` streams stored PDFs from the local filesystem to the browser. It:
- Accepts a `batchFileId` parameter
- Resolves the file's storage path from the `BatchFile` entity
- Streams the bytes with `Content-Type: application/pdf`

This is how the reviewer PDF viewer (`PdfDocumentViewer`) displays the appraisal and supporting documents. The frontend loads the PDF as a blob URL from this endpoint, then renders it page-by-page with the zoom/navigation controls.

`WebConfig` maps the `/uploads/**` URL prefix to the local upload directory for direct static serving (used for thumbnails and non-PDF assets). PDFs go through `FileController` so access can be controlled by the security filter chain.

### Profile Management (`ProfileController`)

`ProfileController` renders the user profile page (Thymeleaf MVC, not a REST endpoint) and handles:
- Viewing account info (username, email, role, client)
- Changing password (with current-password verification)
- Updating display name and contact info

Both admin (`/admin/profile`) and reviewer (`/reviewer/profile`) screens hit the same controller. The frontend pages are thin wrappers around this Thymeleaf form.

---

## 28. Dashboard Service — Role-Scoped Payloads

**Service:** `DashboardService.java`

The admin dashboard overview page (`/admin`) gets its data from `DashboardService`, which assembles different payloads depending on the calling user's role:

| Role | What's included |
|------|----------------|
| **ADMIN** | Total batches by status, all-reviewer workload summary, recent batch activity, system health signals |
| **CLIENT** | Only batches belonging to their client, no cross-client data |
| **REVIEWER** | Their assigned batches only, their personal queue stats |

The service aggregates from `BatchRepository`, `QCResultRepository`, and `OperatorSessionRepository` in a single pass — results are cached for 30 seconds in the Caffeine cache (`CacheConfig`) to avoid repeated DB hits when multiple admin users have the dashboard open simultaneously.

The **system signals** shown on the admin dashboard (Python service healthy / unhealthy, stuck batches present, Redis available) come from:
- `PythonClientService.isHealthy()` — pings the OCR service
- `StuckBatchReconciler` — its last-run result is stored in memory
- `RedisClusterCoordinator` — connectivity check

---

## 29. Appraisal Transaction Layer

An **AppraisalTransaction** sits one level above `Batch` and represents one AMC order from first email receipt through final closure. A single transaction may span multiple SHAL batches (original submission + one or more revision rounds).

### Entity: `AppraisalTransaction`

| Field | Purpose |
|-------|---------|
| `transactionRef` | Stable human-readable ID (e.g. `FIRSTAM-LN20240601-20240601`), shared in rejection emails so the AMC can reference it on revision |
| `amcCode` | AMC identifier (from manifest or explicit API call) — the authoritative link for confidence routing (`amc_id`) |
| `orderNumber` | AMC order/loan number |
| `propertyAddress` | Pre-OCR property address from the intake manifest |
| `client` | FK to the Java `Client` entity owning this order |
| `status` | `TransactionStatus` enum — see lifecycle below |
| `revisedFrom` | Self-referential FK: when this is a revision, points to the preceding transaction |
| `revisionNumber` | 0 = original, 1 = first revision, etc. |
| `receivedAt` | When intake team created the transaction |
| `submittedAt` | When the first batch was uploaded under this transaction |
| `revisionSentAt` | When the last rejection letter was sent to the AMC |
| `closedAt` | When the transaction reached RESOLVED or ABANDONED |
| `slaDueAt` | SLA deadline from the manifest |

### `TransactionStatus` Lifecycle

```
RECEIVED ──► SUBMITTED ──► AWAITING_REVISION ──► SUBMITTED  (revision comes back)
                      │                       └──► ABANDONED
                      └──► RESOLVED
```

### Manifest-Driven Intake

When the ZIP uploaded to SHAL contains a `manifest.json` at its root, `BatchService.linkBatchToTransactionFromManifest()` parses it and auto-links the batch:

```json
{
  "transaction_ref": "FIRSTAM-LN20240601-20240601",
  "amc_code": "FIRSTAM",
  "order_number": "LN20240601",
  "property_address": "123 Main St, Phoenix, AZ 85001",
  "is_revision_of": null,
  "sla_due_at": "2026-07-05T17:00:00"
}
```

If `is_revision_of` names a prior `transactionRef`, the new transaction's `revisedFrom` is set and `revisionNumber` is incremented automatically. If no matching transaction exists for the given `transactionRef`, a new one is created.

### REST Endpoints (`/api/admin/transactions`)

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/admin/transactions` | List all transactions, paginated |
| `GET` | `/api/admin/transactions/{id}` | Get single transaction |
| `GET` | `/api/admin/transactions/stats` | Status counts for dashboard |
| `POST` | `/api/admin/transactions` | Create transaction (explicit, pre-ZIP intake) |
| `POST` | `/api/admin/transactions/{id}/link-batch/{batchId}` | Link an existing batch to a transaction |
| `POST` | `/api/admin/transactions/{id}/rejection-sent` | Record that a rejection was sent → AWAITING_REVISION |
| `POST` | `/api/admin/transactions/{id}/abandon` | Mark transaction abandoned |

### Turnaround Metrics

Three timestamps produce the key AMC scorecard metrics without any external integration:

- **Intake-to-submission**: `submittedAt − receivedAt`
- **First-touch turnaround**: `revisionSentAt − submittedAt`
- **Total lifecycle**: `closedAt − receivedAt`

These are the same metrics MIRA uses to defend AMC volume allocation against client scorecards.

---

*Generated from the project knowledge graph at `.understand-anything/intermediate/assembled-graph.json`. Reflects the codebase as of the last `/understand` analysis run.*
