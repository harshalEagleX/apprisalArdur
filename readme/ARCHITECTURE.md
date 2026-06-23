# SHAL Platform — System Architecture

> **Current State** — This document reflects the architecture as it exists today, derived from a deep
> code audit conducted May 2026. The previous version described a Phase-1 Thymeleaf MVP; the
> platform has evolved significantly beyond that. Read this before making any structural changes.

---

## Table of Contents

1. [Platform Overview](#platform-overview)
2. [Service Topology](#service-topology)
3. [Java Backend — Module Structure](#java-backend--module-structure)
4. [Python OCR Service](#python-ocr-service)
5. [Next.js Frontend](#nextjs-frontend)
6. [End-to-End Data Flow](#end-to-end-data-flow)
7. [Database Design](#database-design)
8. [Real-Time Architecture](#real-time-architecture)
9. [Security Architecture](#security-architecture)
10. [Processing Architecture — Celery](#processing-architecture--celery)
11. [Scalability & Performance](#scalability--performance)
12. [Known Architectural Risks](#known-architectural-risks)

---

## Platform Overview

SHAL is an enterprise appraisal quality-control platform. It ingests residential appraisal PDFs
alongside engagement letters and purchase contracts, runs an OCR + ML + rule-engine pipeline, and
presents a structured reviewer workflow for human quality decisions.

The platform is a **polyglot multi-service system**:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                APPRISAL PLATFORM                                        │
│                                                                                          │
│  ┌─────────────────────────────────────┐     ┌─────────────────────────────────────┐  │
│  │      Next.js 16 Frontend             │     │        Groq (Cloud LLM)            │  │
│  │      Port 3000 (dev)                 │     │        via HTTPS                     │  │
│  │      Role-gated: ADMIN / REVIEWER    │     │        gpt-oss-120b model              │  │
│  └──────────────┬──────────────────────┘     └─────────────────────────────────────┘  │
│                 │ HTTP + WebSocket                         ▲                             │
│                 ▼                                          │ HTTP                        │
│  ┌─────────────────────────────────────┐     ┌────────────┴────────────────────────┐  │
│  │    Java Spring Boot 3 Backend        │────►│   Python FastAPI OCR Service        │  │
│  │    Ports: 8080 (HTTP), /ws/qc (WS)  │◄────│   Port 5001                         │  │
│  │    5 modules: app, batch, common,    │     │   Celery workers + Redis broker      │  │
│  │               qc, user              │     │   Groq LLM integration             │  │
│  └──────────────┬──────────────────────┘     └─────────────────────────────────────┘  │
│                 │ JDBC (HikariCP)                                │                      │
│                 ▼                                                 │ SQLAlchemy           │
│  ┌──────────────────────────────────────────────────────────────▼──────────────────┐  │
│  │                   Neon PostgreSQL (Cloud)   — Shared Single Instance             │  │
│  │   Java schema:  batch, batch_file, qc_result, qc_rule_result, _user, client,    │  │
│  │                 audit_log, revision_info, processing_metrics, operator_session,  │  │
│  │                 business_events, document_match                                  │  │
│  │   Python schema: documents, page_ocr_results, extracted_fields, rule_results,   │  │
│  │                  processing_jobs, feedback_events, training_examples,            │  │
│  │                  llm_call_logs, rules_config                                     │  │
│  └──────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                          │
│  ┌──────────────────────────────────────────────────────────────────────────────────┐  │
│  │                   Redis 7   (Docker local / Celery broker + result backend)       │  │
│  │   Port 6379  — Celery job queue, job status polling, sub-progress events         │  │
│  └──────────────────────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

> **IMPORTANT:** Both Java and Python connect to the **same Neon PostgreSQL instance** with
> different schemas. There is no data replication or message bus between them — Java calls
> Python via REST; Python writes back to the shared DB.

---

## Service Topology

| Service | Language | Port | Auth | Entry Point |
|---------|----------|------|------|-------------|
| Java Backend | Spring Boot 3.4 | 8080 | JWT + Session | `ShalApplication.java` |
| Python OCR | FastAPI 0.115 | 5001 | `X-API-Key` header | `ocr-service/main.py` |
| Next.js Frontend | React 19 + Next.js 16 | 3000 | Bearer token (localStorage) | `frontend/app/` |
| Redis | Redis 7 | 6379 | None (dev) | Docker Compose |
| PostgreSQL | Neon Cloud | 5432 | SSL + user/password | `jdbc:postgresql://...neon.tech` |
| Groq | Cloud API | — | API key | api.groq.com (HTTPS) |

---

## Java Backend — Module Structure

The Java backend is a **modular Maven multi-project**. All modules share the `common` library.

```
app/          ← Main Spring Boot application, config, security, WebSocket, analytics
batch/        ← ZIP upload, file extraction, batch lifecycle, operator sessions
common/       ← Shared entities, repositories, DTOs, services, utilities
qc/           ← QC processing orchestration, Python client, reviewer workflow
user/         ← Authentication, JWT, user management, impersonation, dashboard
brain/        ← Playwright E2E test suite (not deployed)
```

### Module Responsibilities

#### `app` — Application Shell
- `SecurityConfig` — dual security chains (JWT API + form-login web)
- `WebSocketConfig` — STOMP over WebSocket for real-time progress
- `QcWebSocketHandler` — topic-based subscription (batches, reviewer sessions)
- `WebSocketAuthHandshakeInterceptor` — JWT auth on WS upgrade
- `AnalyticsService` — dashboard statistics, SLA metrics
- `AdminSeeder` — creates admin user on first start
- `AsyncConfig` — `qcTaskExecutor` thread pool (2 core, 4 max, queue=20)

#### `batch` — File Ingestion
- `BatchService` — ZIP upload, SHA-256 deduplication, file extraction, storage path management
- `BatchApiController` — admin batch CRUD, status, QC trigger, reviewer assignment
- `FileController` — authenticated PDF file serving (`/files/{batchFileId}`)
- `OperatorSessionService` — tracks reviewer session timing, files processed

#### `common` — Shared Foundation
- **Entities:** `Batch`, `BatchFile`, `Client`, `User`, `QCResult`, `QCRuleResult`,
  `AuditLog`, `DocumentMatch`, `ProcessingMetrics`, `BusinessEvent`, `OperatorSession`
- **Repositories:** JPA repositories with custom JPQL, `@EntityGraph`, and batch operations
- **Services:** `AuditLogService`, `BusinessEventService`, `FileMatchingService`
- **Audit:** Hibernate Envers on all core entities (`revision_info` + `*_AUD` tables)
- **Utilities:** `AppTime` (timezone-aware timestamps), `UserPrincipal`, `AppRevisionEntity`

#### `qc` — QC Processing Engine
- `QCProcessingService` — orchestrates the full batch→file→Python→persist pipeline
- `PythonClientService` — HTTP calls to Python via `RestTemplate` (sync + async Celery paths)
- `VerificationService` — reviewer session locking, decision saving, counter recalculation
- `StuckBatchReconciler` — scheduled task to recover batches stuck in QC_PROCESSING
- `ReviewerApiController` — reviewer queue, decisions, session management
- `QCApiController` — admin QC triggers, progress, job status, file info

#### `user` — Identity & Access
- `AuthController` — login/logout, JWT token issuance
- `AuthenticationService` — BCrypt validation, JWT generation
- `CustomUserDetailsService` — Spring Security user loading
- `DashboardService` — role-specific dashboard statistics
- `ImpersonationService` — admin can impersonate any user
- `ClientService` — organization management

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Self-injection via `@Lazy` in `QCProcessingService` | Break circular proxy dependency for `@Async` + `@Transactional` self-calls |
| `REQUIRES_NEW` transactions on error/save helpers | Isolate each file's save from the long Python processing; prevents idle Neon connections |
| `processBatch()` NOT `@Transactional` | Python OCR takes 5-15 min; holding a DB transaction that long kills Neon's idle timeout |
| In-memory progress maps (`ConcurrentHashMap`) | Low latency progress updates; acceptable because processing is single-server today |
| `@Formula` for `fileCount` on `Batch` | Avoids lazy-load N+1 when serializing batches in list API with `open-in-view=false` |
| Hibernate batch inserts (`batch_size=50`) | Saves ~136 `QCRuleResult` rows in bulk after Python returns; reduces 50s → ~1s |
| Dual auth chains (JWT + session) | REST API uses stateless JWT; Thymeleaf pages (if any) use form session |

---

## Python OCR Service

The Python service is a **FastAPI application** with a Celery background processing queue.

### Internal Structure

```
ocr-service/
├── main.py                   ← FastAPI app, all endpoints, rate limiting, CORS, API key auth
├── app/
│   ├── config.py             ← ENV var bindings, binary paths, file size limits
│   ├── database.py           ← SQLAlchemy engine + session factory
│   ├── qc_processor.py       ← Orchestrates full QC pipeline (OCR→extract→rules→persist)
│   ├── observability.py      ← OpenTelemetry (optional)
│   ├── models/
│   │   ├── appraisal.py      ← Pydantic domain models (ValidationContext, AppraisalReport…)
│   │   ├── db_models.py      ← SQLAlchemy ORM models for all Python-owned tables
│   │   ├── difference_report.py ← Field comparison structs
│   │   └── field_meta.py     ← FieldMetaResult (value + confidence + source_page)
│   ├── ocr/
│   │   ├── ocr_pipeline.py   ← Parallel page OCR (ThreadPoolExecutor, 4 workers)
│   │   └── image_preprocessor.py ← 5-step OpenCV (gray→denoise→Otsu→grid→deskew)
│   ├── services/
│   │   ├── phase2_extraction.py ← Field extraction via spatial anchors + regex
│   │   ├── extraction_service.py ← Engagement letter + contract field extraction
│   │   ├── cache_service.py   ← SHA-256 OCR cache (page_ocr_results table)
│   │   ├── llm_enrichment.py  ← Groq LLM calls for commentary analysis
│   │   ├── comparable_extraction.py ← Sales comparison grid extraction
│   │   ├── processing_lifecycle.py ← Durable job state machine (processing_jobs table)
│   │   ├── progress_store.py  ← In-memory sub-stage progress store (per token)
│   │   └── external_services.py ← Groq health check, model availability
│   ├── rule_engine/
│   │   ├── engine.py          ← Rule runner: DB config, execution order, isolation
│   │   └── rules_db.py        ← Seed + load rules config (togglable without restart)
│   ├── rules/                 ← 136 rules across 17 rule files
│   │   ├── subject_rules.py   ← S-1..S-12
│   │   ├── contract_rules.py  ← C-1..C-5
│   │   ├── neighborhood_rules.py ← N-1..N-7
│   │   ├── narrative_rules.py ← COM-1..COM-7 (LLM-driven commentary quality)
│   │   └── … (13 more rule files)
│   └── tasks/
│       └── celery_app.py      ← Celery worker definition, `process_document_async` task
```

### OCR Decision Logic

```
For each PDF page:

    word_count = page.get_text("text").split() count

    if word_count >= 100:       → Use PyMuPDF embedded text (FAST: 10ms)
    elif 30 <= word_count < 100:→ Run both; pick higher word count (HYBRID)
    else:                       → 5-step preprocessing + Tesseract --psm 6 (SLOW: 2-3s)

    Pages rendered in main thread (fitz not thread-safe)
    Tesseract runs in ThreadPoolExecutor(max_workers=4)
    All OCR text stored in page_ocr_results for caching
```

### Python → Java Communication Contract

Java calls Python via two modes:

**Synchronous mode** (Celery unavailable):
```
POST /qc/process   — multipart PDF + params → PythonQCResponse (blocks 5-15 min)
```

**Async Celery mode** (preferred):
```
POST /qc/submit    — multipart PDF + params → { job_id, status }
GET  /qc/job/{id}  — poll → { status: PENDING|STARTED|SUCCESS|FAILURE, result? }
GET  /qc/progress/{token} — sub-stage progress polling (1.5s interval from Java)
```

**Python returns to Java** (`PythonQCResponse`):
```json
{
  "success": true,
  "total_rules": 136,
  "passed": 98,
  "failed": 24,
  "verify": 14,
  "rule_results": [ { "rule_id": "S-1", "status": "fail", "message": "...", "bbox_x": 0.1, ... } ],
  "field_confidence": { "property_address": 0.92, "borrower_name": 0.88, ... },
  "processing_time_ms": 14500,
  "extraction_method": "HYBRID",
  "document_id": "uuid",
  "processing_job_id": "uuid",
  "cache_hit": false,
  "model_provider": "groq",
  "model_name": "gpt-oss-120b"
}
```

---

## Next.js Frontend

The frontend is a **Next.js 16.2.4 app** (App Router) with Tailwind CSS + Radix UI components.

### Route Structure

```
app/
├── login/              ← Auth form (dual: JWT + session)
├── page.tsx            ← Root redirect by role
├── admin/
│   ├── page.tsx        ← Admin dashboard (metrics, batch overview)
│   ├── batches/        ← Batch list, upload, QC trigger, reviewer assign
│   ├── users/          ← User management (CRUD)
│   ├── clients/        ← Client organization management
│   └── audit/          ← Audit event graph + timeline
├── reviewer/
│   ├── queue/          ← Reviewer queue (pending, submitted)
│   └── verify/[id]/    ← Full review session (PDF + rules side-by-side)
├── analytics/          ← OCR metrics, operator stats, SLA analysis
└── help/               ← Help page
```

### Key Hooks

| Hook | Purpose |
|------|---------|
| `useWebSocket` | Connects to `/ws/qc`, subscribes to topics, auto-reconnects (2.5s) |
| `useBatchPolling` | Polls batch status every 2s when QC is running |
| `useReviewSession` | Manages review lock heartbeat (120s), session token lifecycle |
| `useKeyboardShortcuts` | Full keyboard navigation (j/k, p/f decisions, /, s submit…) |

### Authentication Flow

```
1. POST /api/auth/authenticate  → JWT token stored in localStorage
2. POST /login (form)           → Session cookie (JSESSIONID) for server-side pages
3. All API calls: Authorization: Bearer {token} + credentials: "include"
4. WebSocket: ws://host/ws/qc?access_token={token}  ← token in URL (security risk)
```

> **⚠️ Security Note:** JWT stored in `localStorage` is vulnerable to XSS. Token also
> appears in WebSocket URL which is logged in server access logs. See Security Architecture.

---

## End-to-End Data Flow

### Phase 1 — Upload

```
Admin selects ZIP file
    ↓
POST /api/admin/batches/upload
    ↓
BatchService:
  1. Compute SHA-256 of ZIP → check for duplicate
  2. Extract ZIP entries → classify as APPRAISAL/ENGAGEMENT/CONTRACT by filename
  3. Store files to disk: uploads/EQSS/{clientCode}/xBatch/{parentBatchId}/
  4. Create Batch entity (status=UPLOADED) + BatchFile entities
  5. Record BusinessEvent: BATCH_CREATED
    ↓
Response: { batchId, parentBatchId, fileCount }
```

### Phase 2 — QC Processing

```
Admin triggers: POST /api/qc/process/{batchId}
    ↓
QCProcessingService.processBatchAsync() — @Async("qcTaskExecutor")
    ↓
  1. Claim batch (atomic DB update: UPLOADED → QC_PROCESSING)
  2. FileMatchingService.getMatchedPairs(batchId) — match appraisal + engagement + contract
  3. For each FilePair:
     a. Check if Celery worker running (GET /health → celery_worker_running)
     b. If YES: POST /qc/submit → poll GET /qc/job/{id} every 6s
        If NO:  POST /qc/process (synchronous fallback, blocks worker thread)
     c. WebSocket progress broadcast → /topic/qc/batch/{id}/progress
     d. persistPythonResult() [@Transactional(REQUIRES_NEW)]:
        - Create QCResult + QCRuleResult[] from PythonQCResponse
        - Save ProcessingMetrics
        - Record BusinessEvents per rule
  4. Determine final batch status (AUTO_PASS / REVIEW_PENDING / ERROR)
  5. saveFinalBatchStatus() [@Transactional(REQUIRES_NEW)]
  6. BusinessEvent: BATCH_QC_COMPLETED
```

### Phase 3 — Reviewer Workflow

```
Reviewer opens queue: GET /api/reviewer/qc/pending
    ↓
Select a QCResult: GET /api/reviewer/qc/{qcResultId}/rules
    ↓
Start session: POST /api/reviewer/qc/{qcResultId}/session/start
  → Acquires review lock (SERIALIZABLE-level check)
  → Returns sessionToken, expiresAt
    ↓
For each rule requiring verification:
  1. Reviewer sees PDF page (getBboxCoordinates) + rule details
  2. POST /api/reviewer/decision/save
       { ruleResultId, decision: PASS|FAIL, comment, sessionToken, decisionLatencyMs }
  3. Java updates QCRuleResult + recalculateCounters()
  4. Python feedback sync: POST /qc/feedback (async, fire-and-forget)
  5. WebSocket broadcast → /topic/reviewer/qc/{id}/decision
    ↓
Submit: POST /api/reviewer/qc/{qcResultId}/submit
  → Validates: all TO_VERIFY rules have decisions
  → Sets QCResult.finalDecision (PASS|FAIL)
  → BusinessEvent: REVIEW_SUBMITTED
```

---

## Database Design

### Dual-Schema on Single Neon Instance

Both Java and Python use the **same Neon PostgreSQL** cloud instance but distinct table
namespaces (no PostgreSQL schemas/schemas — same public schema, different table prefixes).

**Java-owned tables** (managed by JPA ddl-auto + Flyway disabled):
```
_user, client, batch, batch_file, qc_result, qc_rule_result,
audit_log, document_match, processing_metrics, business_events,
operator_session, revision_info, *_AUD (Envers audit tables)
```

**Python-owned tables** (managed by Alembic migrations):
```
documents, page_ocr_results, extracted_fields, rule_results,
processing_jobs, feedback_events, training_examples,
llm_call_logs, processing_stages, rules_config
```

### Entity Relationships

```
Client ─── (1:N) ─── Batch ─── (1:N) ─── BatchFile
                                              │
                                           (1:1) ─── QCResult ─── (1:N) ─── QCRuleResult
                                              │
                               documents (Python) ─── (1:N) ─── page_ocr_results
                                              │
                                           processing_jobs ─── (1:N) ─── extracted_fields
```

### Critical Indexes

```sql
-- Batch lookups
idx_batch_status_updated ON batch(status, updated_at)
idx_batch_file_hash ON batch(file_hash)

-- QC rule filtering (reviewer queue)
idx_qc_rule_needs_verif ON qc_rule_result(qc_result_id, needs_verification)
    WHERE needs_verification = TRUE
idx_qc_rule_qcresult_id ON qc_rule_result(qc_result_id)

-- MISSING (should be added):
-- idx_qc_rule_qcresult_status ON qc_rule_result(qc_result_id, status)
-- idx_audit_log_user_created ON audit_log(user_id, created_at DESC)

-- Python OCR cache
UNIQUE(file_hash, page_number) on page_ocr_results  -- prevents duplicate OCR
```

### Audit Trail

Hibernate Envers provides automatic entity history on:
`Batch`, `BatchFile`, `Client`, `User`, `QCResult`, `QCRuleResult`

Each revision stored in `revision_info` with: `timestamp`, `username`, `ip_address`, `correlation_id`

Manual `audit_log` table records: login/logout, user creation, batch deletion (supplementary).

---

## Real-Time Architecture

```
Java QCProcessingService
    │ updateProgress() → RealtimeEventPublisher.publish(topic, payload)
    ↓
WebSocketRealtimeEventPublisher
    │ Sends to STOMP /topic/...
    ↓
QcWebSocketHandler (Spring WebSocket, non-STOMP plain WS)
    │ Authenticated via WebSocketAuthHandshakeInterceptor
    ↓
Frontend useWebSocket hook
    │ Subscribes via "subscribe:/topic/qc/batch/{id}/progress"
    ↓
React state update → Progress bar / status UI
```

**Published Topics:**

| Topic | Payload | Emitter |
|-------|---------|---------|
| `/topic/qc/batch/{batchId}/progress` | QCProgress record | QCProcessingService |
| `/topic/reviewer/qc/{qcResultId}/decision` | Decision save result | VerificationService |

---

## Security Architecture

### Authentication

| Method | Used by | Token lifetime |
|--------|---------|---------------|
| JWT (HS256) | REST API calls from Next.js | 15 min access (configurable) |
| Session cookie | Form login (Thymeleaf pages) | Session duration |

JWT is signed with `JWT_SECRET` (from ENV). Default in `application.yml` is a hardcoded
256-bit hex string — **must be overridden in production**.

### Authorization

```java
// API chain (@Order(1))
/api/auth/**        → permitAll
/api/admin/**       → ADMIN only
/api/qc/process/**  → ADMIN only
/api/analytics/**   → ADMIN only
/api/reviewer/**    → ADMIN or REVIEWER
/api/qc/**          → ADMIN or REVIEWER

// Web chain (@Order(2))
/ws/**              → permitAll (auth via WebSocketAuthHandshakeInterceptor)
/files/**           → authenticated + ownership check in FileController
/admin/**           → ADMIN
/reviewer/**        → ADMIN or REVIEWER
```

### Password Security

- BCrypt (Spring default cost factor 10)
- Password never logged or returned in API responses
- Admin seed password from ENV (`ADMIN_PASSWORD`)

### CSRF

CSRF is **disabled** on both security chains. Protection relies on:
- `SameSite=Strict` cookie for session-based auth
- CORS allowlist (only configured origins can make credentialed requests)

> **Note:** The frontend also sends `Authorization: Bearer` headers, making CSRF moot for
> JWT-based calls. Session-based calls are protected by SameSite.

### Known Security Issues (as of May 2026 Audit)

| Severity | Issue | Status |
|----------|-------|--------|
| CRITICAL | Production credentials in `.env` committed to repo | **Rotate immediately** |
| CRITICAL | Redis port 6379 exposed without auth | Fix docker-compose |
| HIGH | JWT stored in `localStorage` (XSS vector) | Migrate to httpOnly cookie |
| HIGH | JWT token in WebSocket URL query param (logged in access logs) | Pass via header |
| HIGH | No rate limiting on `/api/auth/**` (brute force risk) | Add Resilience4j rate limiter |
| MEDIUM | `ddl-auto: update` in production config | Migrate to Flyway + `validate` |
| MEDIUM | HSTS disabled in SecurityConfig | Enable for production |
| MEDIUM | Path traversal in ZIP extraction only partially mitigated | Use `Path.normalize()` + boundary check |

---

## Processing Architecture — Celery

The Python service supports both synchronous and asynchronous processing:

```
Java submits: POST /qc/submit
                        ↓
            Celery broker (Redis)
                        ↓
            Celery worker picks up task
                        ↓
            process_document_async:
              1. Extract supporting docs from job_dir
              2. qc_processor.process_document()
                  a. OCR pipeline (ThreadPoolExecutor × 4 workers)
                  b. Phase 2 field extraction
                  c. Rule engine (136 rules with DB-togglable config)
                  d. LLM enrichment (Groq, with keyword fallback)
                  e. Persist to DB (page_ocr_results, extracted_fields, rule_results)
                  f. Update processing_job status = COMPLETED
              3. Return result payload
                        ↓
Java polls: GET /qc/job/{id} every 6s
  → When SUCCESS: deserialise result → persistPythonResult()
```

**Celery configuration:**
- Broker: Redis (REDIS_URL)
- Result backend: Redis (TTL 3600s)
- Concurrency: 1 (M1 dev, can scale)
- Task retry: automatic on transient errors
- Job result also persisted to `processing_jobs.result_json` (durable after Redis TTL)

---

## Scalability & Performance

### Current Limits

| Component | Current Design | Limit | Mitigation |
|-----------|---------------|-------|-----------|
| Java async pool | 2 core, 4 max threads | ~4 concurrent batches | Increase `maxPoolSize` |
| HikariCP | 10 connections | ~10 concurrent DB ops | Tune for Neon limits |
| QC progress state | In-memory ConcurrentHashMap | 1 JVM only | Redis-back for multi-instance |
| Review lock | Optimistic check (no `FOR UPDATE`) | Race condition possible | Add pessimistic lock |
| Python Celery | 1 worker (dev) | ~1 batch at a time | Scale workers horizontally |
| Reviewer queue | Unbounded JPQL query | OOM at scale | Add Pageable |
| Batch size | Hibernate `batch_size=50` | Good for 136 rules | No change needed |

### Horizontal Scaling Path

```
                    ┌──────────────────┐
                    │   Load Balancer  │
                    └────────┬─────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
       ┌──────▼────┐  ┌──────▼────┐  ┌──────▼────┐
       │  Java     │  │  Java     │  │  Java     │
       │  Instance │  │  Instance │  │  Instance │
       └──────┬────┘  └──────┬────┘  └──────┬────┘
              │              │              │
              └──────────────┼──────────────┘
                             │ JDBC (pool per instance)
                             ▼
                    ┌──────────────────┐
                    │   Neon PostgreSQL│
                    │   (Primary + RR) │
                    └──────────────────┘

                    ┌────────────────────────────────┐
                    │  Redis Cluster                  │
                    │  (Celery queue + WS pub/sub)    │
                    └────────────────────────────────┘
                    
                    ┌────────────────────────────────┐
                    │  Python OCR Workers (N ×)       │
                    │  Each: FastAPI + Celery worker  │
                    └────────────────────────────────┘
```

> **Blocker for horizontal Java scaling:** In-memory `progressByBatch`, `activeBatches`,
> `runningThreads` in `QCProcessingService` — must be moved to Redis before adding a
> second Java instance.

---

## Known Architectural Risks

| Risk | Impact | Priority |
|------|--------|----------|
| In-memory progress state | No HA for QC processing; progress lost on restart | HIGH |
| Dual audit systems (Envers + manual audit_log) | Three sources of truth for the same event | MEDIUM |
| `python_response` stored as TEXT blob | Can't query Python result fields from SQL | MEDIUM |
| JSONB→TEXT downgrade (V3, V4 migrations) | Lost PostgreSQL JSON query capability | MEDIUM |
| `ddl-auto: update` (not Flyway) | Schema drift in production | HIGH |
| Review lock race condition | Two reviewers can lock same QCResult simultaneously | HIGH |
| Unbounded reviewer queue query | OOM at scale (>10k pending results) | HIGH |
| No Redis auth (dev docker-compose) | Job queue poisoning if exposed | CRITICAL |

---

*Last updated: 2026-05-11 — Based on full code audit of SHAL commit cdf7616*
