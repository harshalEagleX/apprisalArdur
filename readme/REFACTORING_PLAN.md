# Appraisal QC Platform — Full Architecture Analysis & Refactoring Plan

> **Prepared:** 2026-04-29  
> **Scope:** Java multi-module backend · Python OCR service · Next.js frontend · ML/LLM layer  
> **Analyst role:** Senior system architect — full codebase read, code-review-graph verified  
> **Non-negotiable constraint:** Only two roles — `ADMIN` and `REVIEWER`. No CLIENT role. No other roles.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current State Analysis](#2-current-state-analysis)
   - 2a. Module & Folder Map
   - 2b. Database Entity Map
   - 2c. Role & Permission Audit
   - 2d. Problem Catalogue
3. [Target Architecture](#3-target-architecture)
   - 3a. Ideal Folder Structure
   - 3b. Corrected Database Schema
   - 3c. Role Permission Matrix
   - 3d. Frontend Page & Component Tree
   - 3e. Order State Machine
4. [Migration & Execution Plan](#4-migration--execution-plan)
5. [Risk Register](#5-risk-register)
6. [Before vs After](#6-before-vs-after)

---

## 1. Executive Summary

The Appraisal QC Platform is a functioning, multi-service system. The Java backend is well-structured
(5 Maven modules, clean service boundaries, proper audit logging). The Python OCR service has 136
compliance rules across 16 files and is architecturally sound. The reviewer verification UI is the
strongest part of the frontend.

**However, six problems undermine the system:**

1. **A third role (CLIENT) exists everywhere** — in Java entities, security config, API routes, and
   the frontend. The business requirement is strictly two roles: ADMIN and REVIEWER. CLIENT is an
   organisation (tenant), not a user type. This confusion is the root cause of most structural
   problems.

2. **The admin frontend uses `window.prompt()`** for creating users and clients. This is not
   acceptable for a production tool used by operators.

3. **No Next.js route protection middleware** — any authenticated user can navigate to any page
   directly. A reviewer can type `/admin` in the browser and reach the admin screen.

4. **The Python OCR service models are correctly placed** — but they are completely undocumented,
   causing the perception that they are wrong. They need documentation, not relocation.

5. **BatchApiController is mounted at `/api/client/batches`** — because uploads were originally a
   client action. In the two-role model, only ADMIN uploads. The route must move to
   `/api/admin/batches/upload`.

6. **ImpersonationService adds significant complexity** for a feature that is not needed in v1.

Everything else — the OCR pipeline, rule engine, reviewer verification flow, audit logging,
analytics service, JWT + session dual auth, and PostgreSQL schema — is solid and should be kept.

**The refactoring is safe and incremental. Nothing breaks if the plan is followed in order.**

---

## 2. Current State Analysis

### 2a. Module & Folder Map (Actual, As-Found)

```
apprisalArdur/                             ← Git root, Maven parent POM
├── pom.xml                                ← parent: 5 modules, Spring Boot 4.0.1, Java 21
├── common/                                ← Shared library (no Spring Boot main)
│   └── src/main/java/com/apprisal/common/
│       ├── audit/         AppRevisionEntity, AppRevisionListener (Hibernate Envers)
│       ├── dto/           AuthenticationRequest/Response, DecisionSaveRequest,
│       │                  RegisterRequest, python/PythonQCResponse, PythonRuleResult
│       ├── entity/        User, Role(ADMIN|REVIEWER|CLIENT), Client, Batch, BatchFile,
│       │                  BatchStatus(14 states), FileType, FileStatus, QCResult,
│       │                  QCRuleResult, QCDecision, FinalDecision, AuditLog,
│       │                  OperatorSession, ProcessingMetrics
│       ├── exception/     AccessDeniedException, BatchProcessingException,
│       │                  ResourceNotFoundException, ValidationException
│       ├── repository/    All JPA repositories (11 total)
│       └── service/       AuditLogService, FileMatchingService
│
├── batch/                                 ← ZIP upload & file management
│   └── src/main/java/com/apprisal/batch/
│       ├── controller/
│       │   ├── FileController.java        ← GET /files/{id} (serves PDFs to iframe)
│       │   └── api/BatchApiController.java← GET|POST /api/client/batches  ← WRONG MOUNT
│       └── service/
│           ├── BatchService.java          ← createFromZip, assign, delete, stats
│           └── OperatorSessionService.java← session tracking (analytics)
│
├── qc/                                    ← QC processing & reviewer verification
│   └── src/main/java/com/apprisal/qc/
│       ├── config/OcrServiceConfig.java   ← Python endpoint, timeouts
│       └── service/
│       │   ├── QCProcessingService.java   ← orchestrates Python calls, stores results
│       │   ├── PythonClientService.java   ← HTTP client to Python :5001
│       │   └── VerificationService.java   ← reviewer accept/reject logic
│       └── controller/api/
│           ├── QCApiController.java       ← POST /api/qc/process/{batchId}
│           └── ReviewerApiController.java ← /api/reviewer/** (queue, decisions, progress)
│
├── user/                                  ← Auth & user management
│   └── src/main/java/com/apprisal/user/
│       ├── controller/
│       │   ├── AuthController.java        ← /api/auth/login (JWT), /api/auth/register
│       │   ├── ProfileController.java     ← /api/me
│       │   └── api/DashboardApiController.java ← /api/*/dashboard
│       ├── security/
│       │   ├── CustomUserDetailsService.java
│       │   └── JwtAuthenticationFilter.java
│       ├── service/
│       │   ├── UserService.java           ← CRUD
│       │   ├── ClientService.java         ← tenant organisation management
│       │   ├── AuthenticationService.java ← login, JWT issuance
│       │   ├── DashboardService.java      ← per-role dashboard metrics
│       │   └── ImpersonationService.java  ← UNNECESSARY in v1
│       └── util/JwtUtils.java
│
├── app/                                   ← Spring Boot main, security, analytics
│   └── src/main/java/com/apprisal/
│       ├── ApprisalApplication.java
│       ├── config/
│       │   ├── SecurityConfig.java        ← references CLIENT role in 6 places
│       │   ├── AdminSeeder.java           ← seeds default admin on startup
│       │   ├── RestTemplateConfig.java
│       │   └── WebConfig.java
│       ├── controller/
│       │   ├── AdminController.java       ← Thymeleaf /admin/** (legacy, can be removed)
│       │   ├── ClientController.java      ← Thymeleaf /client/** (CLIENT role, remove)
│       │   ├── PageController.java        ← Thymeleaf /dashboard, /login
│       │   └── ReviewerController.java    ← Thymeleaf /reviewer/** (legacy)
│       │   └── api/
│       │       ├── AdminApiController.java← /api/admin/** (users, clients, batches, impersonation)
│       │       └── AnalyticsApiController.java ← /api/analytics/**
│       ├── exception/                     ← Global exception handlers (REST + Web)
│       ├── filter/CorrelationIdFilter.java← Request ID MDC injection
│       └── service/AnalyticsService.java  ← aggregated metrics (5 query methods)
│
├── frontend/                              ← Next.js 16, React 19, Tailwind 4, Radix/shadcn
│   ├── app/
│   │   ├── layout.tsx                     ← root layout (bare, no auth shell)
│   │   ├── page.tsx                       ← role-based redirect only
│   │   ├── login/page.tsx                 ← ✅ clean, keep
│   │   ├── admin/page.tsx                 ← ⚠️ uses window.prompt(), no middleware guard
│   │   ├── reviewer/queue/page.tsx        ← ✅ good, keep
│   │   ├── reviewer/verify/[id]/page.tsx  ← ✅ best screen, keep
│   │   ├── client/page.tsx                ← ❌ CLIENT role, delete
│   │   ├── analytics/page.tsx             ← ⚠️ exists but wiring incomplete
│   │   ├── help/page.tsx                  ← ⚠️ stub
│   │   └── error.tsx, not-found.tsx       ← ✅ keep
│   ├── components/
│   │   ├── UploadScreen.tsx               ← ⚠️ legacy OCR-service direct upload
│   │   ├── ResultsDashboard.tsx           ← ⚠️ legacy OCR-service direct results
│   │   ├── RuleDetailView.tsx             ← ⚠️ legacy OCR-service direct rules
│   │   └── ui/                            ← shadcn primitives (button, card, badge…)
│   └── lib/
│       ├── api.ts                         ← ✅ clean Java-only client, keep and extend
│       └── legacy-types.ts                ← ❌ orphan, delete
│
└── ocr-service/                           ← Python FastAPI, port 5001
    ├── main.py                            ← FastAPI app entry, all routes
    ├── app/
    │   ├── config.py                      ← env vars
    │   ├── database.py                    ← SQLAlchemy engine (own PostgreSQL schema)
    │   ├── models/
    │   │   ├── db_models.py               ← ✅ CORRECT PLACEMENT (Python-own DB tables)
    │   │   ├── appraisal.py               ← ✅ Pydantic domain models
    │   │   ├── difference_report.py       ← ✅ Pydantic extraction result models
    │   │   └── field_meta.py              ← ✅ FieldMetaResult
    │   ├── ocr/
    │   │   ├── ocr_pipeline.py            ← parallel OCR (ThreadPoolExecutor, 4 workers)
    │   │   └── image_preprocessor.py     ← 5-step OpenCV pipeline
    │   ├── services/
    │   │   ├── phase2_extraction.py       ← spatial anchor + regex field extraction
    │   │   ├── extraction_service.py      ← engagement + contract parsing
    │   │   ├── ocr_correction.py          ← 51-pattern correction dictionary
    │   │   ├── cache_service.py           ← SHA-256 OCR cache
    │   │   ├── ollama_service.py          ← LLM: classify_commentary, analyze_market
    │   │   └── llm_cache.py              ← LLM response cache
    │   ├── rule_engine/
    │   │   ├── engine.py                  ← DB-ordered rule runner
    │   │   ├── rules_db.py               ← rule config loader
    │   │   └── smart_identifier.py       ← RuleResult, RuleStatus, RuleSeverity
    │   ├── rules/                         ← 136 rules, 16 files, 7 tiers
    │   │   ├── subject_rules.py           ← S-1..S-12
    │   │   ├── contract_rules.py          ← C-1..C-5
    │   │   ├── neighborhood_rules.py      ← N-1..N-7
    │   │   ├── site_rules.py              ← ST-1..ST-10
    │   │   ├── improvement_rules.py       ← I-1..I-13
    │   │   ├── sales_comparison_rules.py  ← SCA-1..SCA-27
    │   │   ├── additional_approach_rules.py← R-1..R-2, CA-1..CA-2, IA-1..IA-2
    │   │   ├── addendum_rules.py          ← ADD-1..ADD-9
    │   │   ├── doc_rules.py              ← DOC-1..DOC-4
    │   │   ├── signature_rules.py         ← SIG-1..SIG-4
    │   │   ├── photo_rules.py             ← PH-1..PH-6
    │   │   ├── maps_rules.py             ← M-1..M-4
    │   │   ├── sketch_rules.py           ← SK-1..SK-5
    │   │   ├── fha_rules.py              ← FHA-1..FHA-14
    │   │   ├── usda_mf_rules.py          ← USDA-1, MF-1..MF-2
    │   │   └── narrative_rules.py         ← COM-1..COM-7 (LLM, runs last)
    │   ├── nlp/nlp_checks.py             ← tiered commentary analysis
    │   └── qc_processor.py              ← top-level QC orchestrator
    └── alembic/                           ← Python DB migrations
```

---

### 2b. Database Entity Map

**Java database schema (PostgreSQL, managed by Hibernate DDL / manual migrations):**

| Table | Entity | Module | Status |
|-------|--------|--------|--------|
| `_user` | `User` | common | ✅ Keep, remove CLIENT references |
| `client` | `Client` | common | ✅ Keep — this is a tenant organisation |
| `batch` | `Batch` | common | ✅ Keep |
| `batch_file` | `BatchFile` | common | ✅ Keep |
| `qc_result` | `QCResult` | common | ✅ Keep |
| `qc_rule_result` | `QCRuleResult` | common | ✅ Keep |
| `audit_log` | `AuditLog` | common | ✅ Keep |
| `operator_session` | `OperatorSession` | common | ⚠️ Keep but simplify |
| `processing_metrics` | `ProcessingMetrics` | common | ✅ Keep |
| Envers revision tables | `AppRevisionEntity` | common | ✅ Keep |

**Python database schema (separate PostgreSQL schema, managed by Alembic):**

| Table | Model | Status | Notes |
|-------|-------|--------|-------|
| `documents` | `Document` | ✅ Correct placement | OCR-service own cache |
| `page_ocr_results` | `PageOCRResult` | ✅ Correct placement | OCR cache per page |
| `extracted_fields` | `ExtractedFieldRecord` | ✅ Correct placement | Training signal |
| `rule_results` | `RuleResultRecord` | ✅ Correct placement | Python-side audit |
| `feedback_events` | `FeedbackEvent` | ✅ Correct placement | ML training source |
| `training_examples` | `TrainingExample` | ✅ Correct placement | ML labels |
| `rules_config` | `RuleConfig` | ✅ Correct placement | Toggle rules live |
| `llm_response_cache` | `LLMResponseCache` | ✅ Correct placement | Ollama cache |

> **Clarification on model placement:** The Python models in `ocr-service/app/models/` are
> **correctly placed**. They represent tables in the Python service's own PostgreSQL database.
> Java has no knowledge of these tables — it receives QC results via REST API only.
> These models do NOT need to move. They need a `README.md` explaining the two-database design.

**Key relationship (Java side):**
```
Client (tenant org)
  └─ Batch (uploaded ZIP)
       └─ BatchFile (individual PDF)
            └─ QCResult (Python QC output, stored by Java)
                 └─ QCRuleResult[] (one per rule)
                      └─ reviewer decision (accept/reject/comment)
```

---

### 2c. Role & Permission Audit (Current State)

**Current roles in `Role.java`:** `ADMIN`, `REVIEWER`, `CLIENT`

| Endpoint | Current Guard | Current Role(s) | Problem |
|----------|--------------|-----------------|---------|
| `POST /login` | permitAll | — | ✅ Correct |
| `GET /api/me` | authenticated | any | ✅ Correct |
| `GET /api/admin/**` | `hasRole("ADMIN")` | ADMIN | ✅ Correct |
| `GET /api/client/**` | `hasAnyRole("ADMIN","CLIENT")` | ADMIN + CLIENT | ❌ CLIENT role should not exist |
| `GET /api/reviewer/**` | `hasAnyRole("ADMIN","REVIEWER")` | ADMIN + REVIEWER | ✅ Correct logic |
| `POST /api/qc/process/**` | authenticated | any | ❌ Should be ADMIN only |
| `GET /api/qc/results/**` | authenticated | any | ❌ Reviewer should only see assigned |
| `GET /files/{id}` | authenticated | any | ⚠️ No ownership check in SecurityConfig (done in controller) |
| `GET /admin/**` (Thymeleaf) | `hasRole("ADMIN")` | ADMIN | ⚠️ Thymeleaf routes unused with Next.js frontend |
| `GET /client/**` (Thymeleaf) | `hasAnyRole("ADMIN","CLIENT")` | ADMIN + CLIENT | ❌ Remove |
| `GET /reviewer/**` (Thymeleaf) | `hasAnyRole("ADMIN","REVIEWER")` | ADMIN + REVIEWER | ⚠️ Thymeleaf unused |
| `POST /api/admin/batches/{id}/assign` | `hasRole("ADMIN")` | ADMIN | ✅ Correct |
| `DELETE /api/admin/batches/{id}` | `hasRole("ADMIN")` | ADMIN | ✅ Correct |
| `POST /api/admin/impersonate/**` | `hasRole("ADMIN")` | ADMIN | ❌ Remove feature |
| `POST /api/reviewer/decision/save` | `hasAnyRole("ADMIN","REVIEWER")` | ADMIN + REVIEWER | ⚠️ No assignment ownership check |
| `GET /api/reviewer/qc/{id}/rules` | `hasAnyRole("ADMIN","REVIEWER")` | ADMIN + REVIEWER | ⚠️ No assignment ownership check |
| `GET /api/analytics/**` | authenticated | any | ❌ Should be ADMIN only |

**Frontend route protection (current):**
| Route | Protection | Problem |
|-------|-----------|---------|
| `/login` | none | ✅ Correct |
| `/admin` | ❌ None (middleware missing) | Any user can navigate here |
| `/reviewer/queue` | ❌ None | Any user can navigate here |
| `/reviewer/verify/[id]` | ❌ None | Any user can access any result |
| `/client` | ❌ CLIENT role, delete | — |
| `/analytics` | ❌ None | Any user can access |

---

### 2d. Problem Catalogue

Numbered by severity. Fix in this order.

#### 🔴 CRITICAL — Fix Before Any Feature Work

**P-01: CLIENT role must be fully removed**
- `Role.java`: Remove `CLIENT` from enum
- `SecurityConfig.java`: Remove all `hasRole("CLIENT")` / `hasAnyRole("ADMIN","CLIENT")` references
- `BatchApiController.java`: Move from `/api/client/batches` to `/api/admin/batches/upload`
- `ClientController.java`: Delete entire file (Thymeleaf, unused)
- `frontend/app/client/page.tsx`: Delete
- `frontend/lib/api.ts`: Remove `getClientBatches`, `getBatchById`, `getBatchStatus`, `uploadBatch` (client versions)
- `User.java`: The `client` FK field stays — a user (ADMIN) can belong to a client organisation
- `DashboardService.java`: Remove `getClientDashboard()` method
- `DashboardApiController.java`: Remove `/api/client/dashboard` endpoint

**P-02: Frontend has no route protection middleware**
- Create `frontend/middleware.ts` that checks the session cookie on every request
- ADMIN routes (`/admin/**`, `/analytics/**`) → redirect non-ADMIN to `/reviewer/queue`
- REVIEWER routes (`/reviewer/**`) → redirect unauthenticated to `/login`
- Any unauthenticated request → redirect to `/login`

**P-03: Admin UI uses `window.prompt()` for CRUD**
- `admin/page.tsx`: Replace all `prompt()` calls with proper modal dialog components
- Need: `UserModal.tsx`, `ClientModal.tsx` with proper form validation
- Need: Confirmation dialog for delete operations (`ConfirmDialog.tsx`)

**P-04: QC process endpoint is not ADMIN-guarded**
- `QCApiController`: `POST /api/qc/process/{batchId}` must add `@PreAuthorize("hasRole('ADMIN')")`
- Analytics endpoints must be ADMIN-only

**P-05: Reviewer sees ALL pending results, not just assigned ones**
- `ReviewerApiController.getPendingQueue()` calls `findPendingVerification()` — returns ALL
- Must filter by `batch.assignedReviewer.id == currentUser.id` for REVIEWER role
- ADMIN can see all (for override)

#### 🟡 HIGH — Fix in Phase 2

**P-06: ImpersonationService adds complexity with no v1 value**
- `ImpersonationService.java`: Move to `legacy/` package and annotate `@Deprecated`
- Remove from `AdminApiController` (3 endpoints)
- Remove from `lib/api.ts`

**P-07: BatchApiController mounted at wrong path**
- Currently: `POST /api/client/batches/upload`
- Should be: `POST /api/admin/batches/upload`
- Also add: proper file size guard (currently only in Python, must be enforced in Java too)
- Add: idempotency check — hash ZIP file before saving, reject duplicate upload

**P-08: BatchStatus has 14 states — several are redundant and never set**
- `OCR_PENDING` / `OCR_PROCESSING` / `OCR_COMPLETED` — OCR happens inside Python, Java never sets these
- Java goes directly from `VALIDATION_FAILED` → `OCR_PENDING` → `QC_PROCESSING` → `REVIEW_PENDING`/`COMPLETED`
- Simplify to 8 states (see Section 3e)

**P-09: No ownership check on file serving**
- `FileController GET /files/{id}`: Checks `batchFile` exists but should also verify the requesting
  user owns or is assigned to the batch that contains the file
- A reviewer could guess any `batchFileId` and download unassigned documents

**P-10: No pagination UI controls in frontend**
- Admin batch list uses `getAdminBatches(page=0)` but never passes a `page` variable
- Add pagination controls to all list views

**P-11: Thymeleaf controllers are dead code with Next.js frontend**
- `AdminController.java`, `ClientController.java`, `PageController.java`, `ReviewerController.java`
- These serve Thymeleaf templates that no longer exist
- Delete all four files; the Spring Boot app serves no HTML pages

**P-12: Missing search and filter on admin batch list**
- Admin has no way to filter batches by status, date, or client
- Add `BatchRepository` query methods and API parameter support

#### 🟢 STANDARD — Phase 3+

**P-13: No Next.js layouts for role isolation**
- Currently: every page inlines its own `<nav>` and `<aside>` (copy-paste)
- Create: `AdminLayout.tsx` and `ReviewerLayout.tsx` as shared shell components

**P-14: Analytics page exists but uses no data**
- `/analytics/page.tsx` is a stub
- Wire to existing `AnalyticsApiController` endpoints (already built in Java)

**P-15: No error boundary per page**
- Global `error.tsx` exists but no per-route error handling
- Reviewer verify page should show a friendly error if QC result not found

**P-16: Python models need documentation, not relocation**
- Add `ocr-service/app/models/README.md` explaining the two-database design
- This eliminates the confusion about whether models are "in the wrong place"

**P-17: OCR service communicates synchronously**
- `QCProcessingService.processBatch()` calls Python inline on the HTTP thread
- Large batches block the Spring thread pool
- Add `@Async` annotation + `CompletableFuture` return to move to task executor

**P-18: No database migration system for Java side**
- Java uses `spring.jpa.hibernate.ddl-auto=update` (inferred from working state)
- Should use Flyway or Liquibase for schema version control
- Python already has Alembic — establish the same discipline for Java

**P-19: Reviewer's `saveDecision` has no authorization on rule ownership**
- `POST /api/reviewer/decision/save` with any `ruleResultId` — no check that the reviewer
  is assigned to the batch containing this rule result
- Classic IDOR vulnerability

---

## 3. Target Architecture

### 3a. Ideal Folder Structure (After Refactor)

**Java backend — changes only (unchanged modules omitted):**

```
common/
  └── entity/
      └── Role.java                      ← REMOVE CLIENT; keep ADMIN, REVIEWER only
      └── BatchStatus.java               ← Simplify to 8 states

batch/
  └── controller/
      └── FileController.java            ← Add ownership check
      └── api/BatchApiController.java    ← Move to /api/admin/batches/**
                                           Remove CLIENT-scoped methods

app/
  └── controller/
      ├── AdminController.java           ← DELETE (Thymeleaf, dead)
      ├── ClientController.java          ← DELETE (CLIENT role)
      ├── PageController.java            ← DELETE (Thymeleaf, dead)
      └── ReviewerController.java        ← DELETE (Thymeleaf, dead)
  └── config/
      └── SecurityConfig.java            ← Remove CLIENT references (6 places)
                                           Add ADMIN guard to /api/qc/process/**
                                           Add ADMIN guard to /api/analytics/**

user/
  └── service/
      └── ImpersonationService.java      ← MOVE to legacy/, annotate @Deprecated
```

**Frontend — new structure:**

```
frontend/
├── middleware.ts                         ← NEW: route protection for all pages
├── app/
│   ├── layout.tsx                        ← Keep (root layout, no auth shell)
│   ├── page.tsx                          ← Keep (role-based redirect)
│   ├── login/page.tsx                    ← Keep as-is
│   │
│   ├── admin/                            ← ADMIN-only zone (middleware enforced)
│   │   ├── layout.tsx                    ← NEW: AdminLayout (sidebar + header)
│   │   ├── page.tsx                      ← Overview dashboard (rewrite properly)
│   │   ├── batches/page.tsx              ← NEW: dedicated batch list page
│   │   ├── users/page.tsx                ← NEW: dedicated user management page
│   │   └── clients/page.tsx              ← NEW: dedicated client management page
│   │
│   ├── reviewer/                         ← REVIEWER + ADMIN zone (middleware enforced)
│   │   ├── layout.tsx                    ← NEW: ReviewerLayout (minimal nav)
│   │   ├── queue/page.tsx                ← Keep, minor improvements
│   │   └── verify/[id]/page.tsx          ← Keep as-is (best screen in the system)
│   │
│   ├── analytics/page.tsx                ← Wire to /api/analytics/** (ADMIN only)
│   ├── error.tsx                         ← Keep
│   └── not-found.tsx                     ← Keep
│
├── components/
│   ├── admin/
│   │   ├── BatchTable.tsx                ← NEW: table with search, filter, pagination
│   │   ├── UserTable.tsx                 ← NEW: user list with proper actions
│   │   ├── ClientGrid.tsx                ← NEW: client organisation cards
│   │   ├── BatchActions.tsx              ← NEW: QC trigger + assign dropdown
│   │   ├── UserModal.tsx                 ← NEW: create/edit user form in dialog
│   │   ├── ClientModal.tsx               ← NEW: create client form in dialog
│   │   └── ConfirmDialog.tsx             ← NEW: delete confirmation
│   │
│   ├── reviewer/
│   │   ├── QueueItem.tsx                 ← EXTRACT from queue/page.tsx
│   │   └── RuleCard.tsx                  ← EXTRACT from verify/[id]/page.tsx
│   │
│   ├── shared/
│   │   ├── AdminLayout.tsx               ← NEW: sidebar + header shell
│   │   ├── ReviewerLayout.tsx            ← NEW: top nav shell
│   │   ├── StatCard.tsx                  ← NEW: metric card with icon + color
│   │   ├── StatusBadge.tsx               ← NEW: unified badge for BatchStatus
│   │   ├── Pagination.tsx                ← NEW: prev/next page controls
│   │   ├── SearchFilter.tsx              ← NEW: search input + status dropdown
│   │   └── EmptyState.tsx                ← NEW: no-data placeholder
│   │
│   ├── UploadScreen.tsx                  ← DELETE (OCR-direct legacy)
│   ├── ResultsDashboard.tsx              ← DELETE (OCR-direct legacy)
│   └── RuleDetailView.tsx                ← DELETE (OCR-direct legacy)
│
└── lib/
    ├── api.ts                            ← Keep, remove CLIENT methods, add admin upload
    ├── auth.ts                           ← NEW: role checking helpers for middleware
    └── legacy-types.ts                   ← DELETE
```

**Python OCR service — no structural changes needed:**

```
ocr-service/
  └── app/
      └── models/
          └── README.md                   ← NEW: document two-database design
```

---

### 3b. Corrected Database Schema

**Java schema — changes:**

```sql
-- Role enum: remove CLIENT
-- Before: ADMIN | REVIEWER | CLIENT
-- After:  ADMIN | REVIEWER

-- BatchStatus: simplify from 14 → 8 states
-- Remove: OCR_PENDING, OCR_PROCESSING, OCR_COMPLETED, QC_PENDING, QC_COMPLETED
-- (Java never sets these — Python handles OCR internally)
-- Keep: UPLOADED, VALIDATING, VALIDATION_FAILED, QC_PROCESSING,
--       REVIEW_PENDING, IN_REVIEW, COMPLETED, ERROR

-- Add missing index: batch.assigned_reviewer_id
CREATE INDEX idx_batch_assigned ON batch(assigned_reviewer_id);

-- Add missing index: qc_rule_result.qc_result_id (verify it exists)
CREATE INDEX idx_qc_rule_qc_result ON qc_rule_result(qc_result_id);

-- Add: batch.file_hash for deduplication (align with Python)
ALTER TABLE batch ADD COLUMN file_hash VARCHAR(64);
CREATE UNIQUE INDEX idx_batch_file_hash ON batch(file_hash);

-- Add: soft delete on _user
ALTER TABLE _user ADD COLUMN deleted_at TIMESTAMP;
ALTER TABLE _user ADD COLUMN is_active BOOLEAN DEFAULT TRUE;
```

**Entity Relationship (target):**

```
Client (id, name, code, status)
  └──< Batch (id, parent_batch_id, client_id, status[8], assigned_reviewer_id,
              created_by, file_hash, created_at)
         └──< BatchFile (id, batch_id, file_type[APPRAISAL|ENGAGEMENT|CONTRACT],
                         filename, storage_path, file_size, status, order_id)
                └── QCResult (id, batch_file_id, qc_decision, final_decision,
                              total_rules, passed_count, failed_count, verify_count,
                              reviewed_by, reviewed_at, reviewer_notes, processing_time_ms)
                      └──< QCRuleResult (id, qc_result_id, rule_id, rule_name, status,
                                         message, action_item, appraisal_value,
                                         engagement_value, review_required,
                                         reviewer_verified, reviewer_comment, verified_at)

_user (id, username, password[bcrypt], role[ADMIN|REVIEWER], email, full_name,
       client_id[FK→client, nullable], is_active, created_at)

AuditLog (id, user_id, action, entity_type, entity_id, details, ip_address, created_at)
ProcessingMetrics (id, qc_result_id, total_processing_ms, ocr_confidence_avg,
                   fields_extracted, rule_pass_rate, cache_hit, file_size_bytes)
```

---

### 3c. Role Permission Matrix (Target)

| Endpoint | Method | ADMIN | REVIEWER | Unauthenticated | Notes |
|----------|--------|-------|----------|-----------------|-------|
| `/api/auth/login` | POST | ✅ | ✅ | ✅ | Form login |
| `/api/me` | GET | ✅ | ✅ | ❌→/login | Returns role |
| `/api/admin/users` | GET | ✅ | ❌ | ❌ | Paginated |
| `/api/admin/users` | POST | ✅ | ❌ | ❌ | Create ADMIN or REVIEWER only |
| `/api/admin/users/{id}` | PUT | ✅ | ❌ | ❌ | |
| `/api/admin/users/{id}` | DELETE | ✅ | ❌ | ❌ | Soft delete |
| `/api/admin/clients` | GET | ✅ | ❌ | ❌ | |
| `/api/admin/clients` | POST | ✅ | ❌ | ❌ | |
| `/api/admin/batches` | GET | ✅ | ❌ | ❌ | All batches, paginated, filterable |
| `/api/admin/batches/upload` | POST | ✅ | ❌ | ❌ | ZIP upload (moved from /client/) |
| `/api/admin/batches/{id}/assign` | POST | ✅ | ❌ | ❌ | Assign reviewer |
| `/api/admin/batches/{id}` | DELETE | ✅ | ❌ | ❌ | |
| `/api/admin/dashboard` | GET | ✅ | ❌ | ❌ | |
| `/api/qc/process/{batchId}` | POST | ✅ | ❌ | ❌ | Trigger QC — ADMIN only |
| `/api/qc/results/{batchId}` | GET | ✅ | ✅ (assigned) | ❌ | Reviewer: own assignments only |
| `/api/qc/file/{qcResultId}` | GET | ✅ | ✅ (assigned) | ❌ | |
| `/api/reviewer/qc/results/pending` | GET | ✅ (all) | ✅ (own) | ❌ | Scoped by assignment |
| `/api/reviewer/qc/{id}/rules` | GET | ✅ | ✅ (own) | ❌ | IDOR check on reviewer |
| `/api/reviewer/qc/{id}/progress` | GET | ✅ | ✅ (own) | ❌ | |
| `/api/reviewer/decision/save` | POST | ✅ | ✅ (own) | ❌ | IDOR check on rule result |
| `/api/reviewer/dashboard` | GET | ✅ | ✅ | ❌ | |
| `/api/analytics/**` | GET | ✅ | ❌ | ❌ | |
| `/files/{id}` | GET | ✅ | ✅ (assigned) | ❌ | Ownership check in controller |
| `/actuator/health` | GET | ✅ | ✅ | ✅ | |

**Frontend route protection (middleware.ts):**

| Route Pattern | ADMIN | REVIEWER | Unauthenticated |
|---------------|-------|----------|-----------------|
| `/login` | redirect `/admin` | redirect `/reviewer/queue` | ✅ allow |
| `/admin/**` | ✅ allow | redirect `/reviewer/queue` | redirect `/login` |
| `/analytics/**` | ✅ allow | redirect `/reviewer/queue` | redirect `/login` |
| `/reviewer/**` | ✅ allow | ✅ allow | redirect `/login` |
| `/` | redirect `/admin` | redirect `/reviewer/queue` | redirect `/login` |

---

### 3d. Frontend Page & Component Tree (Target)

```
Login (/login)
│  clean form, no changes needed

Root (/) — redirect only, no UI

Admin Zone (/admin/**)
├── AdminLayout (shared shell)
│   ├── Sidebar: logo, nav links, user avatar, sign out
│   └── Header: page title, breadcrumb
│
├── /admin (Dashboard Overview)
│   ├── StatCard × 6 (total batches, pending QC, in review, completed, reviewers, errors)
│   ├── RecentBatchList (last 5 batches, quick actions)
│   └── ReviewerWorkloadTable (per-reviewer: assigned, completed today, avg time)
│
├── /admin/batches (Batch Management)
│   ├── Header: "Upload Batch" button → triggers ZIP upload modal
│   ├── SearchFilter (search by batch ID, filter by status, date range)
│   ├── BatchTable
│   │   ├── Columns: Batch ID | Client | Status | Files | Reviewer | Date | Actions
│   │   ├── StatusBadge (colour-coded per state)
│   │   └── BatchActions per row:
│   │       ├── [Run QC] button (only when status = UPLOADED / VALIDATING)
│   │       ├── [Assign] dropdown (only when status = QC_PROCESSING / REVIEW_PENDING)
│   │       └── [Delete] → ConfirmDialog
│   └── Pagination
│
├── /admin/users (User Management)
│   ├── Header: "Add User" button → UserModal
│   ├── UserTable
│   │   ├── Columns: Name | Username | Role | Client Org | Created | Actions
│   │   └── Actions: [Edit] → UserModal | [Delete] → ConfirmDialog
│   └── Pagination
│
└── /admin/clients (Client Organisations)
    ├── Header: "Add Client" button → ClientModal
    └── ClientGrid (card per org: name, code, status, batch count)

Reviewer Zone (/reviewer/**)
├── ReviewerLayout (shared shell)
│   └── TopNav: logo, "Queue" link, user name, sign out
│
├── /reviewer/queue (Verification Queue)
│   ├── Header: "N pending" badge
│   ├── EmptyState (when queue is empty: ✅ All caught up)
│   └── QueueItemList
│       └── QueueItem per file:
│           ├── filename, processed time, cache indicator
│           ├── Pass/Fail/Review/Total counts
│           └── [Verify →] link to /reviewer/verify/[id]
│
└── /reviewer/verify/[id] (Verification Detail — keep as-is, it's good)
    ├── TopBar: ← Queue | file name | status counts | Submit button
    ├── Left panel (55%): PDF iframe
    └── Right panel (45%):
        ├── FilterBar: All | Fail | Review | Pass
        └── RuleCard list (expandable)
            ├── Rule ID badge | Rule name | Severity badge | Status badge
            ├── Found in Report vs Expected (Order Form) comparison
            ├── Action item hint
            └── Accept / Reject buttons + comment (review-required only)

Analytics (/analytics) — ADMIN only
├── Period selector (7d / 30d / 90d)
├── StatCard × 4 (files processed, avg OCR accuracy, avg pass rate, cache hit rate)
├── TrendChart (rule pass rate over time)
├── ReviewerWorkloadTable (assignments, completions, avg time)
└── FlagFrequencyTable (which rules fail most often)
```

---

### 3e. Order State Machine (Target — 8 States)

```
                 ┌─────────────────────────────────────────────┐
                 │              ADMIN UPLOADS ZIP               │
                 └──────────────────┬──────────────────────────┘
                                    │
                                    ▼
                              UPLOADED (initial)
                                    │
                                    │ (Java validates ZIP structure)
                                    ▼
                              VALIDATING
                               /        \
              (invalid ZIP)  /            \ (valid: has appraisal + engagement)
                            ▼              ▼
                   VALIDATION_FAILED    QC_PROCESSING
                        (terminal)          │
                                            │ (Python OCR + 136 rules run)
                                            │
                          ┌─────────────────┴──────────────────┐
                          │                                      │
                   (all rules PASS)                    (any FAIL/VERIFY/WARNING)
                          │                                      │
                          ▼                                      ▼
                       COMPLETED ◄───── (reviewer accepts) ── REVIEW_PENDING
                        (terminal)                               │
                                                                 │ (admin assigns reviewer)
                                                                 ▼
                                                             IN_REVIEW
                                                                 │
                                        ┌────────────────────────┤
                                        │                         │
                               (all accepted)              (any rejected)
                                        │                         │
                                        ▼                         ▼
                                    COMPLETED                  ERROR
                                    (terminal)              (manual review needed)

Legend:
  UPLOADED         — ZIP received, awaiting validation
  VALIDATING       — folder/file structure check running
  VALIDATION_FAILED — bad structure, no PDFs found, path traversal detected
  QC_PROCESSING    — Python OCR + 136 rules running
  REVIEW_PENDING   — has FAIL/VERIFY items, waiting for reviewer assignment
  IN_REVIEW        — reviewer actively working on it
  COMPLETED        — all rules pass or reviewer accepted all items
  ERROR            — system error, needs manual investigation

Allowed transitions (enforced in BatchService):
  UPLOADED        → VALIDATING
  VALIDATING      → VALIDATION_FAILED | QC_PROCESSING
  QC_PROCESSING   → REVIEW_PENDING | COMPLETED | ERROR
  REVIEW_PENDING  → IN_REVIEW (when reviewer assigned)
  IN_REVIEW       → COMPLETED | ERROR
```

**Transition rules:**
- Only ADMIN can trigger QC (`UPLOADED → QC_PROCESSING`)
- Only ADMIN can assign reviewer (`REVIEW_PENDING → IN_REVIEW`)
- Only REVIEWER (or ADMIN) can complete review (`IN_REVIEW → COMPLETED | ERROR`)
- No backward transitions allowed (cannot go from COMPLETED back to REVIEW_PENDING)
- Any transition logs to `AuditLog` with actor, from-state, to-state, timestamp

---

## 4. Migration & Execution Plan

### Phase 1 — Safe Cleanup (No Logic Changes, Just Removal)
**Estimated: 1 day. Risk: LOW. Nothing functional changes.**

| Step | Action | Files |
|------|--------|-------|
| 1.1 | Delete dead Thymeleaf controllers | `AdminController.java`, `ClientController.java`, `PageController.java`, `ReviewerController.java` |
| 1.2 | Delete legacy frontend components | `UploadScreen.tsx`, `ResultsDashboard.tsx`, `RuleDetailView.tsx`, `legacy-types.ts` |
| 1.3 | Delete client page | `frontend/app/client/page.tsx` |
| 1.4 | Remove impersonation endpoints | `AdminApiController.java` (3 methods), `lib/api.ts` (3 functions) |
| 1.5 | Move `ImpersonationService.java` to `user/service/legacy/` | Add `@Deprecated` annotation |
| 1.6 | Add `README.md` to `ocr-service/app/models/` | Explains two-database design |

### Phase 2 — Role Correction (Core Breaking Change)
**Estimated: 1 day. Risk: MEDIUM. Test after each sub-step.**

| Step | Action | Files |
|------|--------|-------|
| 2.1 | Remove `CLIENT` from `Role.java` enum | `common/.../entity/Role.java` |
| 2.2 | Update `SecurityConfig.java` — remove all CLIENT references | `app/.../config/SecurityConfig.java` |
| 2.3 | Add `@PreAuthorize("hasRole('ADMIN')")` to QC process + analytics endpoints | `QCApiController.java`, `AnalyticsApiController.java` |
| 2.4 | Move `BatchApiController` mount to `/api/admin/batches/upload` | `batch/.../api/BatchApiController.java` |
| 2.5 | Remove CLIENT methods from `DashboardApiController` and `DashboardService` | `user/...` |
| 2.6 | Update `lib/api.ts` — remove client-scoped functions, add `uploadBatch` under admin | `frontend/lib/api.ts` |
| 2.7 | Database: add `is_active` and `deleted_at` to `_user` table | SQL migration |
| 2.8 | Verify admin seeder still works with 2-role enum | `AdminSeeder.java` |

### Phase 3 — Security Hardening (IDOR + Ownership)
**Estimated: 1 day. Risk: LOW (additive checks only).**

| Step | Action | Files |
|------|--------|-------|
| 3.1 | `FileController`: verify requester owns or is assigned to file's batch | `batch/.../FileController.java` |
| 3.2 | `ReviewerApiController.getPendingQueue()`: filter by `assigned_reviewer_id` for REVIEWER role | `qc/.../ReviewerApiController.java` |
| 3.3 | `ReviewerApiController.saveDecision()`: verify rule result belongs to assigned batch | `qc/.../ReviewerApiController.java` |
| 3.4 | `ReviewerApiController.getAllRules()`: same ownership check | `qc/.../ReviewerApiController.java` |
| 3.5 | Create `frontend/middleware.ts` | Route protection for all pages |
| 3.6 | Simplify `BatchStatus` to 8 states | `common/.../entity/BatchStatus.java`, check all setters |

### Phase 4 — Frontend Rebuild (New Components)
**Estimated: 2-3 days. Risk: LOW (UI only, no backend changes).**

| Step | Action | Files |
|------|--------|-------|
| 4.1 | Create `middleware.ts` | `frontend/middleware.ts` |
| 4.2 | Create `AdminLayout.tsx` (sidebar + header shell) | `components/shared/AdminLayout.tsx` |
| 4.3 | Create `ReviewerLayout.tsx` (top nav) | `components/shared/ReviewerLayout.tsx` |
| 4.4 | Create shared primitives: `StatCard`, `StatusBadge`, `Pagination`, `SearchFilter`, `EmptyState`, `ConfirmDialog` | `components/shared/` |
| 4.5 | Create admin modals: `UserModal.tsx`, `ClientModal.tsx` | `components/admin/` |
| 4.6 | Create `BatchTable.tsx` with search + filter + pagination | `components/admin/BatchTable.tsx` |
| 4.7 | Rewrite `admin/page.tsx` → route to `/admin` (overview only) | |
| 4.8 | Create `admin/batches/page.tsx` | dedicated batch management |
| 4.9 | Create `admin/users/page.tsx` | dedicated user management |
| 4.10 | Create `admin/clients/page.tsx` | dedicated client management |
| 4.11 | Create `admin/layout.tsx` | uses `AdminLayout` |
| 4.12 | Create `reviewer/layout.tsx` | uses `ReviewerLayout` |
| 4.13 | Wire `analytics/page.tsx` to `AnalyticsApiController` | |
| 4.14 | Add pagination to all list pages | |

### Phase 5 — Quality & Async (Performance)
**Estimated: 1 day. Risk: LOW.**

| Step | Action | Files |
|------|--------|-------|
| 5.1 | Add `@Async` + `CompletableFuture` to `QCProcessingService.processBatch()` | `qc/.../QCProcessingService.java` |
| 5.2 | Add `BatchRepository` search/filter query methods | `common/.../repository/BatchRepository.java` |
| 5.3 | Add `GET /api/admin/batches?status=&search=&page=` query params | `BatchApiController.java` |
| 5.4 | Add ZIP deduplication: hash ZIP before save, reject duplicate | `BatchService.java` |
| 5.5 | Add Java-side file size enforcement (50MB limit) | `BatchApiController.java` |
| 5.6 | Add Flyway dependency and migrate existing schema | `pom.xml`, `resources/db/migration/` |

---

## 5. Risk Register

| ID | Risk | Likelihood | Impact | Mitigation |
|----|------|-----------|--------|-----------|
| R-01 | Removing CLIENT role breaks an active user's login | LOW (if no CLIENT users exist) | HIGH | Query `_user` table before migration: `SELECT * FROM _user WHERE role = 'CLIENT'`; update to REVIEWER if any found |
| R-02 | Moving BatchApiController path breaks admin UI upload | MEDIUM | MEDIUM | Update `lib/api.ts` upload URL at the same time; test upload before merging |
| R-03 | BatchStatus simplification leaves orphaned records | LOW | MEDIUM | Query current states before removing: `SELECT status, COUNT(*) FROM batch GROUP BY status`; migrate remaining `OCR_PENDING` → `QC_PROCESSING` |
| R-04 | Middleware.ts blocks a valid route | LOW | MEDIUM | Test all routes with both roles after creating middleware; add `/actuator/**` to allowlist |
| R-05 | IDOR check on `saveDecision` rejects admin override | LOW | LOW | Check role first: if ADMIN, skip ownership check; if REVIEWER, enforce it |
| R-06 | Python OCR service continues to function after no changes | NONE | N/A | No Python changes planned; verify health endpoint after Java restart |
| R-07 | Async QC processing changes response shape | MEDIUM | LOW | Return `202 Accepted` with `{ batchId, status: "QC_PROCESSING" }` instead of blocking; frontend polls `/api/admin/batches/{id}/status` |
| R-08 | `ImpersonationService` is depended on by running admin sessions | LOW | LOW | Deprecate it, keep the beans but remove HTTP endpoints |

---

## 6. Before vs After

### Role System

| Aspect | Before | After |
|--------|--------|-------|
| Roles | ADMIN, REVIEWER, CLIENT | ADMIN, REVIEWER only |
| Upload who | CLIENT users (via `/api/client/batches/upload`) | ADMIN only (via `/api/admin/batches/upload`) |
| Client entity | Linked to CLIENT users | Still exists as tenant organisation (admin creates them, users may belong to one) |
| Role enum | 3 values | 2 values |
| Security config | 6 CLIENT references | 0 CLIENT references |

### API Routes

| Before | After | Change |
|--------|-------|--------|
| `POST /api/client/batches/upload` | `POST /api/admin/batches/upload` | Mount point moved |
| `GET /api/client/batches` | `GET /api/admin/batches` | Absorbed into admin |
| `GET /api/client/batches/{id}` | `GET /api/admin/batches/{id}` | Absorbed into admin |
| `POST /api/admin/impersonate/{id}` | removed | Feature removed |
| `POST /api/admin/impersonate/stop` | removed | Feature removed |
| `GET /api/admin/impersonate/status` | removed | Feature removed |
| `GET /api/qc/process/{id}` | `POST /api/qc/process/{id}` + ADMIN-only guard | Properly secured |
| `GET /api/analytics/**` | `GET /api/analytics/**` + ADMIN-only guard | Properly secured |

### Frontend Structure

| Before | After |
|--------|-------|
| Single `admin/page.tsx` with 4 tabs | 4 separate pages: `/admin`, `/admin/batches`, `/admin/users`, `/admin/clients` |
| `window.prompt()` for create actions | Proper modal dialogs with form validation |
| No middleware — any user hits any route | `middleware.ts` enforces role-based access |
| No shared layout | `AdminLayout.tsx` + `ReviewerLayout.tsx` |
| No pagination UI | Pagination controls on all list views |
| No search/filter | Search + status filter on batch list |
| `client/page.tsx` exists | Deleted |
| `UploadScreen.tsx` (OCR-direct) | Deleted (upload is in admin panel) |
| `legacy-types.ts` | Deleted |

### State Machine

| Before (14 states) | After (8 states) |
|-------------------|-----------------|
| UPLOADED | UPLOADED |
| VALIDATING | VALIDATING |
| VALIDATION_FAILED | VALIDATION_FAILED |
| OCR_PENDING | → merged into QC_PROCESSING |
| OCR_PROCESSING | → merged into QC_PROCESSING |
| OCR_COMPLETED | → merged into QC_PROCESSING |
| QC_PENDING | → merged into QC_PROCESSING |
| **QC_PROCESSING** | QC_PROCESSING |
| QC_COMPLETED | → merged into REVIEW_PENDING |
| REVIEW_PENDING | REVIEW_PENDING |
| IN_REVIEW | IN_REVIEW |
| COMPLETED | COMPLETED |
| REJECTED | → ERROR (reviewer rejection → human review) |
| ERROR | ERROR |

### Python Model Placement

| Before (perceived) | After (documented) |
|-------------------|-------------------|
| `ocr-service/app/models/db_models.py` seen as misplaced | Same file, same location — now documented |
| No README explaining design | `ocr-service/app/models/README.md` explains two-database design |
| Confusion: "Java entities vs Python models" | Clear: Python owns its own PostgreSQL schema; Java owns its own. They share no tables. |

---

## Appendix A — Reviewer Data Access Model

After the refactor, a REVIEWER accessing `/api/reviewer/qc/results/pending` will only see:

```sql
SELECT qr.* FROM qc_result qr
  JOIN batch_file bf ON bf.id = qr.batch_file_id
  JOIN batch b ON b.id = bf.batch_id
WHERE b.assigned_reviewer_id = :currentUserId
  AND qr.qc_decision = 'TO_VERIFY'
  AND qr.final_decision IS NULL
```

An ADMIN accessing the same endpoint sees all records (no `WHERE` clause on reviewer).

This is enforced in `ReviewerApiController` via `SecurityContextHolder` — check role, build query accordingly.

---

## Appendix B — Frontend Middleware Implementation

```typescript
// middleware.ts
import { NextRequest, NextResponse } from "next/server";

const PUBLIC_ROUTES = ["/login"];
const ADMIN_ROUTES  = ["/admin", "/analytics"];

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (PUBLIC_ROUTES.some(r => pathname.startsWith(r))) {
    return NextResponse.next();
  }

  // Validate session with Java backend
  const sessionRes = await fetch(
    `${process.env.NEXT_PUBLIC_JAVA_URL}/api/me`,
    { headers: { cookie: request.headers.get("cookie") ?? "" } }
  );

  if (!sessionRes.ok) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  const { role } = await sessionRes.json() as { role: string };

  const isAdminRoute = ADMIN_ROUTES.some(r => pathname.startsWith(r));
  if (isAdminRoute && role !== "ADMIN") {
    return NextResponse.redirect(new URL("/reviewer/queue", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|api).*)"],
};
```

> **Note:** This makes a server-side fetch on every page load. Cache the session result in
> an edge-compatible store (or use a signed cookie) if latency becomes a concern.

---

## Appendix C — AI / LLM Integration Status

**Current (keep as-is):**
- Ollama running locally on port 11434
- Model: `llama3:8b-instruct-q4_0` for commentary analysis (COM-1..COM-7)
- Model: `moondream` for checkbox detection (future)
- Temperature: 0.0 (deterministic)
- All calls cached in `llm_response_cache` table (SHA-256 of input)
- Fallback: keyword-based when Ollama unavailable

**No Claude API or OpenAI integration is needed** unless the commentary quality detection
proves insufficient with llama3:8b. The current tiered approach (keyword → embeddings → LLM)
is already well-designed. Add Claude/OpenAI only if Ollama quality is demonstrably below
business requirements — which requires measurement first.

---

---

## Appendix D — Database & Migration Strategy (Point 2)

### Current State (Found in Code)

`application.yml` has `spring.jpa.hibernate.ddl-auto: none` and `spring.flyway.enabled: true`
with `locations: classpath:db/migration`. **Flyway is already wired but has zero migration files.**
This means the schema currently exists only because someone ran `ddl-auto: create` once and then
switched to `none`. If you deploy to a fresh database, nothing works.

### Migration File Sequence (Safe, Ordered)

All files go in `app/src/main/resources/db/migration/`.

```
V1__initial_schema.sql       ← captures current full schema as baseline
V2__remove_client_role.sql   ← migrates Role enum: CLIENT → REVIEWER for existing records
V3__simplify_batch_status.sql← migrates old status values to 8-state model
V4__add_severity_to_qc_rule.sql ← adds severity column to qc_rule_result
V5__add_batch_indexes.sql    ← missing performance indexes
```

**V1 must be created by dumping the current schema:**
```bash
pg_dump --schema-only --no-owner -d ardurApprisal > V1__initial_schema.sql
```
Then set `spring.flyway.baseline-on-migrate: true` on first deploy against an existing database.

**V2 — safe CLIENT role removal (run this BEFORE removing CLIENT from enum):**
```sql
-- First: verify no CLIENT users exist
SELECT id, username, role FROM _user WHERE role = 'CLIENT';
-- If any found: decide whether to make them REVIEWER or ADMIN
-- Then migrate:
UPDATE _user SET role = 'REVIEWER' WHERE role = 'CLIENT';
-- Remove CLIENT from the PostgreSQL enum is not needed: Java enums
-- are stored as VARCHAR(255) with EnumType.STRING, so no ALTER TYPE needed.
-- Just removing from the Java enum is sufficient after the UPDATE above.
```

**V3 — safe BatchStatus migration:**
```sql
-- Check what states exist before simplifying
SELECT status, COUNT(*) FROM batch GROUP BY status;

-- Migrate redundant states to closest equivalent
UPDATE batch SET status = 'QC_PROCESSING'
  WHERE status IN ('OCR_PENDING', 'OCR_PROCESSING', 'OCR_COMPLETED', 'QC_PENDING');
UPDATE batch SET status = 'REVIEW_PENDING'
  WHERE status = 'QC_COMPLETED';
UPDATE batch SET status = 'ERROR'
  WHERE status = 'REJECTED';
```

**V4 — add severity column:**
```sql
ALTER TABLE qc_rule_result
  ADD COLUMN IF NOT EXISTS severity VARCHAR(20) DEFAULT 'STANDARD';
```

**V5 — performance indexes:**
```sql
CREATE INDEX IF NOT EXISTS idx_batch_assigned ON batch(assigned_reviewer_id);
CREATE INDEX IF NOT EXISTS idx_batch_status   ON batch(status);
CREATE INDEX IF NOT EXISTS idx_batch_client   ON batch(client_id);
CREATE INDEX IF NOT EXISTS idx_qc_result_file ON qc_result(batch_file_id);
CREATE INDEX IF NOT EXISTS idx_qc_rule_result ON qc_rule_result(qc_result_id);
CREATE INDEX IF NOT EXISTS idx_qc_rule_review ON qc_rule_result(review_required) WHERE review_required = TRUE;
CREATE INDEX IF NOT EXISTS idx_audit_user     ON audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_entity   ON audit_log(entity_type, entity_id);
```

### Migration Safety Rules

1. **Always run V2 before removing CLIENT from `Role.java`** — removing the enum value before
   migrating the data will cause a `DataIntegrityViolationException` on next startup.
2. **Always test migrations against a copy of production data** before applying.
3. **Never drop columns** — only make them nullable first, drop in a later migration.
4. **Flyway checksums are sacrosanct** — never edit a migration file after it has been applied.
   Create a new `Vx__fix.sql` instead.

---

## Appendix E — Testing Strategy (Point 3)

### Current Test Coverage: CRITICAL GAP

**Existing tests found:** 1 file, 1 test.
```
app/src/test/java/com/apprisal/ApprisalApplicationTests.java
  └── contextLoads()  ← Spring context startup test only
```

**Coverage:** ~0% of business logic. No tests for any service, controller, rule, or repository.

### Risk Assessment

| Module | Risk to Refactor | Why |
|--------|-----------------|-----|
| `VerificationService` | HIGH | Complex state transitions, IDOR logic newly added |
| `QCProcessingService` | HIGH | Multi-step pipeline, async behaviour being added |
| `BatchService.createFromZip()` | HIGH | ZIP parsing, path traversal guard, file matching |
| `SecurityConfig` | MEDIUM | Role guard changes affect all endpoints |
| `ReviewerApiController` | MEDIUM | New ownership checks, new query methods |
| `BatchApiController` | LOW | Thin controller, delegates to BatchService |

### Minimum Tests to Write Before Shipping Phase 5

These are the tests that must exist before any Phase 5 code touches production:

**1. Role guard integration tests** (verify the two-role enforcement)
```java
// File: qc/src/test/java/com/apprisal/qc/controller/ReviewerApiControllerTest.java
@Test void reviewer_cannotSeeOtherReviewersBatches() { ... }
@Test void reviewer_cannotSaveDecisionForUnassignedBatch() { ... }
@Test void admin_canSeeAllPendingResults() { ... }
@Test void unauthenticated_cannotAccessReviewerEndpoints_returns401() { ... }
```

**2. BatchService unit tests** (the most complex service)
```java
// File: batch/src/test/java/com/apprisal/batch/service/BatchServiceTest.java
@Test void createFromZip_withValidStructure_createsFilesCorrectly() { ... }
@Test void createFromZip_withPathTraversal_throwsValidationException() { ... }
@Test void createFromZip_withDuplicateHash_throwsDuplicateException() { ... }
@Test void assignReviewer_withNonReviewer_throwsIllegalArgument() { ... }
```

**3. VerificationService unit tests**
```java
// File: qc/src/test/java/com/apprisal/qc/service/VerificationServiceTest.java
@Test void assertReviewerOwnsQcResult_whenNotAssigned_throwsSecurityException() { ... }
@Test void saveDecision_accept_setsStatusManualPass() { ... }
@Test void saveDecision_reject_setsStatusFail() { ... }
```

**4. Python OCR service tests** (already in `ocr-service/` — check if they run)
```bash
cd ocr-service && pytest tests/ -v
```

### Test Environment Setup Required

```yaml
# app/src/test/resources/application-test.yml
spring:
  datasource:
    url: jdbc:h2:mem:testdb;MODE=PostgreSQL
  flyway:
    enabled: false        # Use @Sql annotations instead in tests
  jpa:
    hibernate:
      ddl-auto: create-drop
```

---

## Appendix F — Inter-Service Communication Contract (Point 4)

### Current Architecture

```
Java (port 8080)                    Python (port 5001)
  QCProcessingService
    └─ PythonClientService
         └─ RestTemplate.exchange()
              POST /qc/process       multipart/form-data
              ─────────────────────────────────────────→
              X-API-Key: {PYTHON_API_KEY}
              file: <appraisal.pdf>
              engagement_letter: <engagement.pdf>  (optional)
              contract_file: <contract.pdf>         (optional)
              ←─────────────────────────────────────────
              PythonQCResponse (JSON)
```

**Timeout config:** `ocr.service.timeout-seconds: 180` (3 minutes). `retry-attempts: 2`.

### Formally Defined DTO Contract

**Request — multipart fields:**

| Field | Required | Type | Notes |
|-------|----------|------|-------|
| `file` | YES | PDF binary | Appraisal PDF — the document being reviewed |
| `engagement_letter` | NO | PDF binary | Expected values — used for S-1, S-2, S-10 etc. |
| `contract_file` | NO | PDF binary | Purchase agreement — used for C-1 through C-5 |

**Response — `PythonQCResponse` JSON:**

| Field | Type | Notes |
|-------|------|-------|
| `document_id` | string (UUID) | Python's internal ID for OCR caching |
| `total_rules` | int | Rules executed |
| `passed` | int | Rules with status=pass |
| `failed` | int | Rules with status=fail |
| `verify` | int | Rules with status=verify |
| `warnings` | int | Rules with status=warning |
| `system_errors` | int | Rules that threw exceptions |
| `skipped` | int | Inactive or inapplicable rules |
| `rule_results` | array | One per rule (see below) |
| `processing_time_ms` | int | Total wall time including OCR |
| `extraction_method` | string | EMBEDDED / TESSERACT / HYBRID |
| `cache_hit` | boolean | True if OCR was served from cache |
| `total_pages` | int | Pages processed |
| `field_confidence` | map | field_name → confidence 0-100 |

**Rule result item — `PythonRuleResult`:**

| Field | Type | Notes |
|-------|------|-------|
| `rule_id` | string | e.g. "S-1", "C-3" |
| `rule_name` | string | Human-readable |
| `status` | string | pass / fail / verify / warning / skipped / system_error |
| `message` | string | Summary for operator display |
| `detail` | object | Raw comparison data |
| `action_item` | string | What the reviewer should do |
| `appraisal_value` | string | What OCR found in the report |
| `engagement_value` | string | What the engagement letter says |
| `review_required` | boolean | True if reviewer must act |
| `needs_verification` | boolean | True if OCR confidence was low |

### Failure Modes & Handling

| Failure | Current Handling | Required Fix |
|---------|-----------------|--------------|
| Python service down | `RestClientException` → batch status `ERROR` | ✅ Already handled — `isHealthy()` check before loop |
| Timeout (>180s) | `ResourceAccessException` → not caught → 500 | ⚠️ Wrap in try/catch, set `ERROR` status |
| Invalid JSON response | Jackson parse error → not caught → 500 | ⚠️ Wrap, set `ERROR` status |
| Python returns HTTP 4xx | `HttpClientErrorException` → propagates | ⚠️ Catch specifically — 422 means invalid PDF |
| Python returns empty body | `NullPointerException` on `result.passed()` | ⚠️ Null-check response before using |
| File not found on disk | `FileNotFoundException` in multipart | ⚠️ Check file exists before sending |

**Retry logic:** `retry-attempts: 2` is configured but `PythonClientService` does not implement
retries. The config exists but is unused. For Phase 5: wrap in Spring Retry `@Retryable`.

---

## Appendix G — Error Handling & Observability (Point 8)

### Current State

**Global exception handlers:** ✅ Both exist:
- `GlobalApiExceptionHandler.java` — handles REST exceptions
- `GlobalWebExceptionHandler.java` — handles web/template exceptions

**Correlation ID:** ✅ `CorrelationIdFilter.java` injects `X-Correlation-ID` into MDC.

**Health endpoint:** ✅ `/actuator/health` — configured to show no details (correct for production).

**Structured logging:** ⚠️ SLF4J + Logback. Currently plain-text format. No JSON logging configured.
For production: add logback JSON encoder so logs are parseable by CloudWatch / ELK.

### Gaps Found

**1. Errors silently swallowed in QCProcessingService (single file pair):**
```java
// Current: logs error but keeps going — correct
} catch (Exception e) {
    log.error("Error processing file pair...", e.getMessage(), e);
    errorCount++;
}
```
This is correct for per-file isolation. No change needed.

**2. `PythonClientService.processQC()` propagates `RuntimeException`** — not caught at the
   processing level for timeout / JSON parse errors. Fix: add specific catch blocks in
   `processFilePair()`.

**3. No admin-visible diagnostics for failed batches** — `batch.status = ERROR` with no detail
   about WHY it failed. Fix: add `error_message` column to `Batch` entity (see V4 migration).

**4. `AnalyticsService` catches nothing** — if a metrics query fails, the whole analytics
   endpoint returns 500. Fix: wrap in try/catch, return partial results.

### What to Add for Production Observability

```yaml
# Add to application.yml for production profile
logging:
  pattern:
    console: >-
      {"ts":"%d{ISO8601}","level":"%p","logger":"%c{1}",
       "correlation":"%X{correlationId}","msg":"%m"}%n
```

Or better: add `logstash-logback-encoder` dependency and configure JSON appender.

**Missing health checks to add:**
- Python service reachability (check `/health` on Python service)
- Database connection pool saturation
- Storage disk space available

---

## Appendix H — Deployment & Environment Config (Point 9)

### Current State

**Docker:** `ocr-service/docker-compose.yml` exists for the Python service only. No Docker setup
for the Java backend. No unified `docker-compose.yml` at the repository root.

**Environment validation:** None. If `DB_PASSWORD` is missing, the app starts and crashes on first
DB operation. Spring Boot 4 supports `@ConfigurationPropertiesScan` with `@Validated` — use it.

### Environment Variables (Full Audit)

| Variable | Used by | Default | Required in Prod | Risk if Missing |
|----------|---------|---------|-----------------|-----------------|
| `DB_HOST` | Java | `localhost` | YES | Won't connect to DB |
| `DB_PORT` | Java | `5432` | NO | Uses default |
| `DB_NAME` | Java | `ardurApprisal` | YES | Wrong DB |
| `DB_USERNAME` | Java | `harshalsmac` | YES | Auth failure |
| `DB_PASSWORD` | Java | `12345678` | YES | Auth failure (dev default is insecure) |
| `ADMIN_EMAIL` | Java | `dhoteharshal16@gmail.com` | YES | Seeds wrong admin |
| `ADMIN_PASSWORD` | Java | `Admin123!` | YES | ⚠️ Default is in CLAUDE.md — CHANGE IN PROD |
| `JWT_SECRET` | Java | hardcoded Base64 string | YES | ⚠️ Default is in CLAUDE.md — CHANGE IN PROD |
| `STORAGE_PATH` | Java | `./uploads` | YES | Files stored in CWD (lost on container restart) |
| `PYTHON_API_KEY` | Java → Python | empty | RECOMMENDED | Python accepts any caller |
| `OCR_SERVICE_URL` | Java | `http://localhost:5001` | YES | Can't reach Python |
| `COOKIE_SECURE` | Java | `false` | YES (set true) | Cookies sent over HTTP |
| `DATABASE_URL` | Python | none | YES | Python won't start |
| `OLLAMA_BASE_URL` | Python | `http://localhost:11434` | RECOMMENDED | LLM falls back to keywords |

**Two secrets leaked in CLAUDE.md:** `ADMIN_PASSWORD=Admin123!` and the JWT secret. These must
be rotated before any production deployment. The CLAUDE.md should reference env vars, not values.

### Recommended: Add Startup Validation

```java
// app/src/main/java/com/apprisal/config/StartupValidator.java
@Component
public class StartupValidator implements ApplicationListener<ApplicationReadyEvent> {
    @Value("${app.admin.password}") private String adminPassword;
    @Value("${app.jwt.secret}")     private String jwtSecret;
    @Value("${app.storage.path}")   private String storagePath;

    @Override
    public void onApplicationEvent(ApplicationReadyEvent event) {
        if ("Admin123!".equals(adminPassword) || "Password".equals(adminPassword)) {
            log.warn("SECURITY: Default admin password detected — change ADMIN_PASSWORD before production");
        }
        if (jwtSecret.length() < 32) {
            throw new IllegalStateException("JWT_SECRET must be at least 32 characters");
        }
        Path path = Paths.get(storagePath);
        if (!Files.exists(path) || !Files.isWritable(path)) {
            throw new IllegalStateException("STORAGE_PATH does not exist or is not writable: " + storagePath);
        }
    }
}
```

### Docker — Recommended Root `docker-compose.yml`

```yaml
services:
  postgres:
    image: postgres:17
    environment:
      POSTGRES_DB: ardurApprisal
      POSTGRES_USER: ${DB_USERNAME}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  java-api:
    build: .
    depends_on: [postgres]
    environment:
      DB_HOST: postgres
      DB_PASSWORD: ${DB_PASSWORD}
      STORAGE_PATH: /data/uploads
      OCR_SERVICE_URL: http://ocr-service:5001
    volumes:
      - uploads:/data/uploads
    ports:
      - "8080:8080"

  ocr-service:
    build: ./ocr-service
    depends_on: [postgres]
    environment:
      DATABASE_URL: postgresql://${DB_USERNAME}:${DB_PASSWORD}@postgres:5432/ardurApprisal_ocr
    ports:
      - "5001:5001"

  frontend:
    build: ./frontend
    environment:
      NEXT_PUBLIC_JAVA_URL: http://java-api:8080
    ports:
      - "3000:3000"

volumes:
  pgdata:
  uploads:
```

---

## Appendix I — Idempotency & Duplicate Processing (Point 11)

### Problems Found

**1. Double-click upload creates duplicate batches.**
`POST /api/admin/batches/upload` with the same ZIP twice creates two `Batch` rows. The user
sees two identical batches with identical files but different IDs.

**Fix:** SHA-256 hash the ZIP bytes on receipt. Check `batch.file_hash` before saving.

```java
// In BatchService.createFromZip():
String hash = DigestUtils.sha256Hex(file.getBytes());
Optional<Batch> existing = batchRepository.findByFileHash(hash);
if (existing.isPresent()) {
    log.info("Duplicate ZIP upload detected, returning existing batch {}", existing.get().getId());
    return existing.get();  // idempotent — same ZIP = same batch
}
```

**2. QC processing is not idempotent.**
`QCProcessingService.processFilePair()` already checks `existsByBatchFileId` — ✅ handled.
But `processBatch()` could be triggered twice before the first finishes if admin double-clicks.
Fix: check batch status before starting, return early if already `QC_PROCESSING`.

**3. Reviewer decision save is idempotent** ✅ — `saveDecision()` updates in place, not inserts.

**4. Batch job restart safety.**
If the server crashes mid-batch (e.g., after processing 3 of 5 file pairs), on restart the
`processFilePair()` check for `existsByBatchFileId` will skip already-processed files and
continue with remaining ones. ✅ Already safe.

---

## Appendix J — File Storage Architecture (Point 12)

### Current State

Files are stored on **local disk** at `STORAGE_PATH` (default: `./uploads`).

**Directory structure:**
```
uploads/
  {client.code}/           ← e.g. EQSS/
    {parentBatchId}/       ← e.g. xBatch/
      appraisal/           ← APPRAISAL PDFs
      engagement/          ← ENGAGEMENT PDFs
      contract/            ← CONTRACT PDFs (if present)
```

**Access control:** `GET /files/{batchFileId}` — served by `FileController`. REVIEWER ownership
check now enforced (Phase 2 fix). ADMIN sees all files.

### Known Risks

| Risk | Severity | Mitigation |
|------|----------|-----------|
| Files lost on container restart if volume not mounted | HIGH | Mount `STORAGE_PATH` as a named Docker volume (see Appendix H) |
| Disk fills up — no cleanup job | MEDIUM | Add soft-delete + background purge job (Phase 6) |
| No max file size in Java | MEDIUM | Spring multipart config: `max-file-size: 100MB` ✅ already set — but Java-side guard should also be explicit in `BatchApiController` |
| Original filename not sanitized | LOW | `Paths.get(entryName).getFileName().toString()` already strips path — ✅ safe |
| Files not deleted when batch is deleted | ✅ Fixed | `BatchService.deleteBatch()` walks and deletes storage directory |

### Long-Term: Move to Object Storage

When running multiple API instances or in containerized production, local disk breaks.
Migration path:
1. Add S3/MinIO client dependency
2. Abstract file storage behind `StorageService` interface
3. Implement `LocalStorageService` (current) and `S3StorageService`
4. Switch via `@ConditionalOnProperty("app.storage.type=s3")`

---

## Appendix K — Performance & Scalability (Point 13)

### N+1 Query Audit

| Endpoint | Query Pattern | Problem | Fix |
|----------|-------------|---------|-----|
| `GET /api/admin/batches` | `findAll(Pageable)` | Loads batch list, then for each batch: `batch.getFiles()` accessed in view layer | Add `@EntityGraph` or `JOIN FETCH files` |
| `GET /api/admin/dashboard` | `findTop10ByOrderByCreatedAtDesc()` then iterates `b.getFiles().size()` | N+1 — one query per batch to count files | Use `@Query("SELECT b, SIZE(b.files) FROM Batch b ...")` |
| `GET /api/reviewer/qc/results/pending` | Loads QCResult list, then accesses `r.getBatchFile().getFilename()` | Lazy load per result | ✅ Fixed in new controller — manually maps to Map, no lazy access |

**Identified N+1:** `getAdminDashboard()` in `DashboardService` calls `batchRepository.findByAssignedReviewerId()`
then iterates `b.getFiles().size()` — this is N+1. Fix: use a `@Query COUNT` instead.

### Missing Indexes (Beyond Phase 5 V5 Migration)

```sql
-- Processing metrics lookups (used by AnalyticsService heavily)
CREATE INDEX IF NOT EXISTS idx_metrics_created ON processing_metrics(qc_result_id);
CREATE INDEX IF NOT EXISTS idx_metrics_cache   ON processing_metrics(cache_hit);
```

### Memory Issues

**Large file loading:** `BatchService.createFromZip()` uses `ZipInputStream` streaming — ✅ safe,
never loads full ZIP into memory.

**PDF serving:** `FileController` uses `FileSystemResource` which streams — ✅ safe.

**`pythonResponse` stored as full JSON text** in `qc_result.python_response` column. For a batch
with 100 rules × 100 files this could be 50MB+ in the DB. Consider removing this column after
rule_results are parsed and stored individually.

### Pagination

All list endpoints use `Pageable` — ✅ already correct. Frontend now has pagination UI (Phase 4).

---

## Appendix L — Concurrency & Race Conditions (Point 14)

### Race Conditions Found

**1. Two admins assign the same batch simultaneously.**

```
Admin A: assignReviewer(batchId=42, reviewer=Alice)  → saves
Admin B: assignReviewer(batchId=42, reviewer=Bob)    → saves (overwrites A's assignment)
Alice now has an empty queue, Bob has the batch.
```

**Fix:** Add optimistic locking to `Batch` entity:
```java
@Version
private Long version;  // Hibernate will check this before UPDATE
```
If two concurrent updates happen, the second throws `OptimisticLockingFailureException`.
The API returns `409 Conflict` — frontend retries or shows a message.

**2. Reviewer submits final decision while admin re-assigns.**

Low risk — the reviewer's submission sets `final_decision`, the re-assignment changes
`assigned_reviewer_id`. These are different columns and don't conflict.

**3. QC triggered twice on same batch before first completes.**

Fix: in `QCProcessingService.processBatch()`, check status before starting:
```java
if (batch.getStatus() == BatchStatus.QC_PROCESSING) {
    log.warn("Batch {} is already being processed, ignoring duplicate trigger", batchId);
    return new QCProcessingSummary(0,0,0,0,0, BatchStatus.QC_PROCESSING);
}
```

**4. Two rule results saved concurrently for same QC result.**

`recalculateCounters()` reads all rules then updates QCResult — not atomic. Two concurrent
saves could calculate stale counts. Fix: use `@Lock(LockModeType.PESSIMISTIC_WRITE)` on the
`findById` inside `recalculateCounters`, or use `@Query` aggregate SQL instead of Java loop.

### Transaction Audit

- `BatchService.createFromZip()` — `@Transactional` ✅ — entire ZIP extraction is one transaction.
  If anything fails, no files are created in DB (disk files may be orphaned — acceptable risk).
- `VerificationService.saveDecision()` — `@Transactional` ✅
- `QCProcessingService.processFilePair()` — `@Transactional` ✅

---

## Appendix M — Async Job & Queue Reliability (Point 15)

### Current State

`processBatch()` runs **synchronously on the HTTP thread**. For a 20-file batch at 15 seconds
per file (OCR), the admin's browser waits 5 minutes for a response. This will timeout.

### Phase 5 Implementation Plan

**Step 1:** Add `@Async` to the processing call site (not the service itself):

```java
// In QCApiController:
@PostMapping("/process/{batchId}")
@PreAuthorize("hasRole('ADMIN')")
public ResponseEntity<?> processBatch(@PathVariable Long batchId) {
    // Validate batch exists and is in correct state
    Batch batch = batchService.findById(batchId)
        .orElseThrow(() -> new ResourceNotFoundException("Batch", "id", batchId));

    if (batch.getStatus() == BatchStatus.QC_PROCESSING) {
        return ResponseEntity.ok(Map.of("message", "Already processing", "batchId", batchId));
    }

    // Fire async — returns immediately to admin
    qcProcessingService.processBatchAsync(batchId);

    return ResponseEntity.accepted().body(Map.of(
        "message", "QC processing started",
        "batchId", batchId,
        "pollUrl", "/api/admin/batches/" + batchId + "/status"
    ));
}
```

**Step 2:** Add `@Async` method to QCProcessingService:
```java
@Async("qcTaskExecutor")
public CompletableFuture<QCProcessingSummary> processBatchAsync(Long batchId) {
    try {
        QCProcessingSummary result = processBatch(batchId);
        return CompletableFuture.completedFuture(result);
    } catch (Exception e) {
        log.error("Async QC processing failed for batch {}: {}", batchId, e.getMessage(), e);
        batchService.updateStatus(batchId, BatchStatus.ERROR);
        return CompletableFuture.failedFuture(e);
    }
}
```

**Step 3:** Configure thread pool:
```java
// AppConfiguration.java
@Bean("qcTaskExecutor")
public Executor qcTaskExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);      // 2 batches processed simultaneously
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(20);    // queue up to 20 pending batches
    executor.setThreadNamePrefix("qc-");
    executor.setRejectedExecutionHandler(new ThreadPoolExecutor.CallerRunsPolicy());
    executor.initialize();
    return executor;
}
```

### What Happens if Async Task Crashes

With `@Async` + `CompletableFuture`:
- Exception is caught in `processBatchAsync()`
- Batch status set to `ERROR` with a message
- Error logged with correlation ID
- Admin can see the ERROR status via polling

**Visibility for admin:** The `GET /api/admin/batches/{id}/status` endpoint returns current status.
Frontend polls this after triggering QC (every 5 seconds for up to 10 minutes).

**No dead-letter queue needed** at this scale — failed jobs are visible as `ERROR` batches.
Admin can re-trigger QC manually after fixing the underlying issue.

---

## Appendix N — Audit Trail & Compliance (Point 17)

### What Is Currently Logged

`AuditLogService.logEntity()` and `logAction()` are called for:

| Action | Logged? | Actor | Entity |
|--------|---------|-------|--------|
| User login | ✅ | User | — |
| User logout | ✅ | User | — |
| Batch uploaded | ✅ | ADMIN | Batch |
| User created | ✅ | ADMIN | User |
| User updated | ✅ | ADMIN | User |
| User deleted | ✅ | ADMIN | User |
| Client created | ✅ | ADMIN | Client |
| Batch assigned | ✅ | ADMIN | Batch |
| Batch deleted | ✅ | ADMIN | Batch |
| QC triggered | ✅ | ADMIN | Batch |

### What Is NOT Logged (Gap)

| Action | Currently Logged | Risk |
|--------|-----------------|------|
| Reviewer saves a decision (ACCEPT/REJECT) | ❌ No | Cannot audit who accepted a fail |
| Reviewer submits final review | ❌ No | No record of completion event |
| Batch status transitions | ❌ No | Cannot see when batch moved between states |
| File served (PDF downloaded) | ❌ No | No access log for sensitive documents |
| Admin views a batch | ❌ No | Low priority |

**Fix for reviewer decisions (add to `VerificationService.saveDecision()`):**
```java
auditLogService.log(reviewer, "DECISION_SAVED",
    "QCRuleResult", ruleResultId,
    "ruleId=" + ruleResult.getRuleId() + " decision=" + decision,
    null, null);
```

**Fix for batch status transitions (add to `BatchService.updateStatus()`):**
```java
String detail = "status: " + batch.getStatus() + " → " + status;
auditLogService.logEntity(currentUser, "BATCH_STATUS_CHANGED", "Batch", id, detail);
```

### Envers (Hibernate Audit Tables)

`@Audited` is already on `User`, `Batch`, `BatchFile`, `QCResult`, `QCRuleResult`. This captures
every field change with before/after values in Hibernate's `_aud` tables. This is the primary
compliance audit trail. The `AuditLog` table is the human-readable action log.

---

## Appendix O — Dependency & Version Audit (Point 20)

### Java Dependencies

| Dependency | Version | Status |
|-----------|---------|--------|
| Spring Boot | 4.0.1 | ✅ Current |
| Java | 21 (LTS) | ✅ Current LTS |
| jjwt-api | 0.12.6 | ✅ Current |
| PostgreSQL JDBC | (Boot-managed) | ✅ |
| Lombok | 1.18.34 | ✅ Current |

**Run to check for vulnerabilities:**
```bash
./mvnw dependency:check -DfailBuildOnCVSS=7
```

**Missing:** Spring Security `@PreAuthorize` annotation already on class level in `BatchApiController`
but not consistently applied to individual methods in other controllers. Use `@EnableMethodSecurity`
(already enabled in `SecurityConfig`) + `@PreAuthorize` on all sensitive methods as a second
defence layer beyond URL-level guards.

### Python Dependencies

Run to audit:
```bash
cd ocr-service && pip audit
# or
pip install pip-audit && pip-audit
```

Key packages to verify:
- `fastapi` — check for known CVEs
- `python-multipart` — file upload parsing, historically had vulnerabilities
- `pillow` — image processing, frequent CVE target
- `sqlalchemy` — check version for injection risks

### Frontend Dependencies

```bash
cd frontend && npm audit
```

Current packages of note:
- `react-pdf@10.4.1` + `react-pdf-viewer@3.12` — two PDF libraries, possibly redundant
- `axios@1.15.2` — not actually used (all fetch calls use native `fetch`)

---

## Appendix P — Document Versioning (Point 22)

### What Happens When a Corrected ZIP Is Re-Uploaded?

**Current behaviour:** A new `Batch` is created with the same `parentBatchId` string.
The previous batch and all its files remain in the database untouched. Admin sees two batches.

**Problem:** No concept of "this batch supersedes that one". The reviewer could work on the old batch.

### Recommended Design

**Option A — Idempotent re-upload (replace):** Hash the ZIP. If a batch with the same hash exists, reject the upload and tell admin "this batch was already uploaded" with the batch ID. If content changes (different hash), create a new batch. Old batch must be manually deleted by admin.

**Option B — Version lineage:** Add `parent_batch_id` (FK to `batch.id`, not the string identifier)
and `version_number` to `Batch`. Each re-upload increments the version. Only the latest version is
active. The reviewer always sees the most recent version.

**Recommended for v1: Option A** — simpler, no new columns needed beyond `file_hash`. The admin
explicitly deletes the old batch before re-uploading if they need to replace it.

**Implementation:** Already planned in Phase 5 (ZIP deduplication via SHA-256 hash).

### ZIP Re-upload Behaviour After Phase 5

```
Admin uploads ZIP #1 → hash=abc123 → Batch ID 1 created → QC runs
Admin uploads same ZIP → hash=abc123 → returns existing Batch ID 1 (idempotent)
Admin uploads corrected ZIP → hash=def456 → Batch ID 2 created → new QC runs
Admin deletes Batch ID 1 (old version) via DELETE /api/admin/batches/1
```

This gives full control to ADMIN without automatic replacement that could surprise reviewers.

---

*Document version: 2.0*  
*Updated: 2026-04-29 — Added Appendices D–P covering all 20 audit points*  
*Based on full codebase read: 1417 graph nodes, 8518 edges, 175 files*
