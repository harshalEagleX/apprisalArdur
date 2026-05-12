# Apprisal Platform — Implementation Plan & Enterprise Audit

**Document Version:** 3.0  
**Last Audit:** 2026-05-11  
**Audit Method:** Full code analysis across all 7 platform components
(app, batch, brain, common, frontend, ocr-service, qc, user)  
**Knowledge Graph:** 1,417 nodes, 8,518 edges, 175 files across Java/Python/TypeScript

---

## Table of Contents

1. [Platform Status — What Is Built](#1-platform-status--what-is-built)
2. [Complete Architecture Assessment](#2-complete-architecture-assessment)
3. [End-to-End Data Flow Analysis](#3-end-to-end-data-flow-analysis)
4. [Python ↔ Java Synchronisation Analysis](#4-python--java-synchronisation-analysis)
5. [Database & Storage Audit](#5-database--storage-audit)
6. [Frontend UX & Product Experience Audit](#6-frontend-ux--product-experience-audit)
7. [Backend Scalability & Concurrency Analysis](#7-backend-scalability--concurrency-analysis)
8. [Security & Enterprise Risk Audit](#8-security--enterprise-risk-audit)
9. [Missing Product Workflows & Enterprise Gaps](#9-missing-product-workflows--enterprise-gaps)
10. [Performance Bottleneck Analysis](#10-performance-bottleneck-analysis)
11. [Enterprise-Readiness Score](#11-enterprise-readiness-score)
12. [Prioritised Remediation Roadmap](#12-prioritised-remediation-roadmap)
13. [Long-Term Architecture Recommendations](#13-long-term-architecture-recommendations)

---

## 1. Platform Status — What Is Built

The platform has grown far beyond its original Phase-1 MVP specification. The following
is the actual current state as verified by code inspection.

### Core Capabilities (Implemented & Working)

| Capability | Status | Notes |
|-----------|--------|-------|
| ZIP batch upload with SHA-256 deduplication | ✅ Production | BatchService.java |
| File classification (appraisal/engagement/contract) | ✅ Production | Filename-keyword matching |
| Multi-file document matching | ✅ Production | FileMatchingService with confidence scoring |
| Async QC processing with cancellation | ✅ Production | QCProcessingService + @Async |
| Celery async job queue with sync fallback | ✅ Production | PythonClientService |
| 136-rule QC engine (17 rule categories) | ✅ Production | ocr-service/app/rules/ |
| OCR pipeline (PyMuPDF + Tesseract, parallel) | ✅ Production | ThreadPoolExecutor×4 |
| OCR cache (SHA-256 per page, ~14s→114ms) | ✅ Production | cache_service.py |
| Phase 2 spatial field extraction | ✅ Production | phase2_extraction.py |
| LLM commentary analysis (Ollama, with fallback) | ✅ Production | llm_enrichment.py |
| PDF bounding-box coordinate persistence | ✅ Production | bbox_x/y/w/h on QCRuleResult |
| Real-time WebSocket progress broadcast | ✅ Production | QcWebSocketHandler |
| Reviewer queue with session locking | ✅ Production | VerificationService |
| Per-rule PASS/FAIL decisions with latency tracking | ✅ Production | saveDecision() |
| Decision feedback to Python ML loop | ✅ Production | PythonClientService.submitFeedback() |
| Hibernate Envers full audit trail | ✅ Production | All core entities @Audited |
| BusinessEvent log (136-rule level granularity) | ✅ Production | BusinessEventService |
| Processing metrics (OCR confidence, pass rate, timing) | ✅ Production | ProcessingMetrics |
| Role-based access (ADMIN / REVIEWER) | ✅ Production | Spring Security method-level |
| Client/tenant scoping | ✅ Production | Client entity + user.clientId |
| Analytics dashboard (OCR, operators, SLA, anomalies) | ✅ Production | AnalyticsService |
| Audit graph visualisation (force-directed) | ✅ Production | AuditGraphController |
| Stuck batch reconciler (scheduled) | ✅ Production | StuckBatchReconciler |
| Operator session tracking | ✅ Production | OperatorSessionService |
| Impersonation (admin → any user) | ✅ Production | ImpersonationService |
| ML feedback loop + retraining | ✅ Production | training/retrain.py |
| Next.js reviewer workflow (full keyboard shortcuts) | ✅ Production | frontend/app/reviewer/ |
| PDF viewer with bbox highlighting | ✅ Production | PdfDocumentViewer.tsx |

### Not Yet Implemented

| Feature | Priority | Notes |
|---------|----------|-------|
| Bulk actions on batch list | P1 | Select multiple, bulk assign/delete/QC |
| QC rerun (from frontend) | P1 | Button missing; API exists |
| Token refresh / session expiry warning | P1 | JWT expires with no UI warning |
| Rate limiting on auth endpoints | P1 | Brute-force vulnerability |
| Redis auth in docker-compose | P0-SECURITY | Currently unauthenticated |
| httpOnly cookie for JWT | P1 | Currently localStorage |
| Export to CSV/PDF | P2 | No export functionality |
| Multi-select / bulk decisions in reviewer | P2 | One-at-a-time only |
| Saved filter presets | P2 | |
| QC history / version comparison | P2 | Only latest QC visible |
| Admin rule toggle UI | P2 | Python API exists, no frontend |
| Production Flyway migrations | P1 | Using `ddl-auto: update` |

---

## 2. Complete Architecture Assessment

### Strengths

**Transaction design is excellent.** `QCProcessingService` correctly avoids holding open
DB connections during the 5-15 minute Python OCR call by using `REQUIRES_NEW` isolated
micro-transactions for each file save. This prevents Neon's idle connection timeout from
corrupting results — a subtle and hard-to-get-right problem.

**The dual sync/async processing path is thoughtfully implemented.** When Celery is
unavailable, Java falls back to synchronous Python calls without interrupting the workflow.
The 180-second Celery grace window before assuming the worker is down prevents false
fallbacks on slow worker startup.

**Envers audit coverage is comprehensive.** All core entities (`Batch`, `BatchFile`,
`QCResult`, `QCRuleResult`, `User`, `Client`) are `@Audited` with enhanced `AppRevisionEntity`
capturing username, IP address, and correlation ID per revision. This is enterprise-grade
audit infrastructure.

**The rule engine at 136 rules across 17 categories is genuinely sophisticated.** The
DB-backed config (`rules_config` table) allows toggling individual rules without restart.
Execution order is DB-controlled. Severity levels drive reviewer workflow. This is real
compliance infrastructure, not a toy.

**Frontend keyboard shortcuts are exceptional for an enterprise product.** Full keyboard
navigation on both the reviewer queue and the review verification page covers 20+ shortcuts.
This dramatically reduces reviewer fatigue on high-volume workflows.

### Structural Weaknesses

**In-memory processing state is the largest single architectural risk.** `QCProcessingService`
stores active batch state (`progressByBatch`, `activeBatches`, `runningThreads`,
`cancellationRequests`) in `ConcurrentHashMap` fields on the Spring bean. This means:
- All in-flight progress is lost on JVM restart
- A second Java instance cannot see progress from the first
- The race condition checks (TOCTOU) between `activeBatches` and `runningThreads` cannot be
  made atomic across instances

**`ddl-auto: update` in production is a schema time-bomb.** If a field is renamed in Java,
`update` mode silently creates a new column and leaves the old one populated with stale data.
Migrations are not tracked, schema drift is invisible, and rollback is impossible.

**The documentation described a Thymeleaf + session-only architecture that no longer
exists.** The platform now uses Next.js, dual JWT+session auth, WebSocket, Celery, and
a sophisticated reviewer workflow. Previous documentation was misleading at best.

---

## 3. End-to-End Data Flow Analysis

### Data Correctness: Python → Java

The mapping from `PythonQCResponse` to `QCResult` + `QCRuleResult[]` is implemented in
`QCProcessingService.persistPythonResult()` and is generally correct with the following
verified issues:

**CONFIRMED BUG (FIXED in recent commit):** `saveMetrics()` compared confidence values as
`v < 70.0` instead of `v < 0.70`, classifying all values (e.g. `0.88`) as low-confidence.
This inflated `fieldsLowConfidence` to 100% across all historical records.

**SENTINEL VALUE LEAKAGE:** The service uses private string constants for missing data
(`__NOT_PROVIDED__`, `__NO_APPRAISAL_VALUE__`, `__NO_ENGAGEMENT_VALUE__`, etc.) that are
stored directly in the database when Python returns null values. Frontends and SQL queries
must filter for these sentinels explicitly. Any consumer that treats them as real values
will display garbage.

**RULE RESULT FALLBACK CHAIN:** `actionItem` is populated by trying `pr.actionItem()` →
`pr.verifyQuestion()` → `pr.rejectionText()` → `"No reviewer action required."`. This means
the first non-null of three semantically different fields wins. A rule that has both a
verify question and a rejection text loses the rejection text silently.

**NO FIELD VALIDATION FROM PYTHON:** Confidence scores from Python are stored as-is with no
clamping to [0.0, 1.0]. A malformed Python response could store `-5.2` as a confidence score.

### Data Correctness: Java → Frontend

The frontend `QCRuleResult` TypeScript interface is well-matched to the Java entity.
Identified gaps:

- `help?: RuleHelp | null` field exists in the TypeScript type but the Java entity has no
  `help` column — this field is always `null`
- `sourceDocuments`, `comparedFields`, `comparedValues`, `comparisonMethod`, `decisionPath`,
  `exceptionType` — all typed in TypeScript but these fields appear to come from Python rule
  results and may be `null` in many cases without UI handling

---

## 4. Python ↔ Java Synchronisation Analysis

### What Works Well

- Idempotency key prevents duplicate processing: `{batchFileId}|{contentHash}|{provider}|{textModel}|{visionModel}|rules:1.0`
- `409 Conflict` on duplicate sync calls; Java polls the existing job instead of erroring
- Java correlation IDs passed to Python (`X-Correlation-ID` header + `correlation_id` form field)
- Sub-stage progress polling via `/qc/progress/{token}` gives Java fine-grained visibility
  into Python's OCR page processing

### Critical Synchronisation Risks

**Redis TTL vs DB persistence:** Celery job results expire from Redis after 3600 seconds (1 hour).
If Java polls after this window, it gets a 404. The `processing_jobs.result_json` column in
PostgreSQL is the durable backup, but `processing_lifecycle.complete_job()` is called inside
the Celery task without transaction guarantees — if the DB write fails, the result is permanently
lost.

**OCR cache failure is silent and unrecoverable:** If `save_ocr_pages()` returns `None` (DB
unavailable), the OCR result is thrown away. The exception raised causes the Celery job to fail.
On retry, OCR runs again (14 seconds), fails to save again, loops. There is no fallback to
disk-based journaling.

**Extracted field persistence is not atomic:** `save_extracted_fields()` and `save_rule_results()`
are called sequentially without a transaction wrapping both. If the second write fails, Java receives
rule results in `processing_jobs.result_json` but `extracted_fields` table is incomplete.
The QC result appears complete to Java (it got the JSON payload) but the Python DB is inconsistent.

**Path injection in job_dir:** The Celery task accepts `job_dir` from the `/qc/submit` request
body and uses it directly in `os.path.join()` and `shutil.rmtree()` calls without validating
that the path is within the expected job directory. A crafted `job_dir` of `"/../../../etc"`
could delete arbitrary directories.

**Temp file accumulation:** Job directories are created for each submitted job but only cleaned
up in the `finally` block. If Celery retries the task after a worker restart, the `finally`
block from the previous attempt already ran with `cleanup_job_dir=False`. After 1,000 jobs,
2-3 GB of orphaned PDFs accumulate in `/tmp`.

---

## 5. Database & Storage Audit

### Redundancy Analysis

**Triple representation of QC outcomes:**

| Layer | Table | Fields |
|-------|-------|--------|
| Python DB (source) | `rule_results` | status, message, action_item |
| Java DB (materialised) | `qc_rule_result` | status, message, action_item, reviewer_verified, … |
| Java DB (aggregate) | `qc_result` | total_rules, passed_count, failed_count, verify_count |

The `qc_result` aggregate counts must be kept in sync with `qc_rule_result` row statuses.
`VerificationService.recalculateCounters()` does this in a separate transaction after each
decision save — meaning there is a window where the aggregate counts are stale.

**JSON downgrade (V3, V4 migrations):** `audit_log.details` and `batch_file.ocr_data` were
downgraded from JSONB to TEXT. This disables PostgreSQL's native JSON query operators on these
columns. Querying audit details now requires application-level JSON parsing.

**`python_response` TEXT blob in `qc_result`:** Stores the full Python response (typically 50-200 KB
of JSON) as a TEXT column. This is not queryable, wastes storage, and cannot be indexed.
The fields worth querying (`extraction_method`, model names) are already decomposed into
separate columns — the raw blob serves no production purpose.

### Missing Indexes

```sql
-- Add these:
CREATE INDEX idx_qc_rule_qcresult_status
    ON qc_rule_result(qc_result_id, status);

CREATE INDEX idx_audit_log_user_created
    ON audit_log(user_id, created_at DESC);

CREATE INDEX idx_feedback_untrained
    ON feedback_events(used_for_training)
    WHERE used_for_training = false;
```

### Duplicate Indexes (Remove)

V12 and V13 both create `ON qc_rule_result(qc_result_id)` with different names.
One should be dropped:
```sql
DROP INDEX IF EXISTS idx_qc_rule_qcresult_id;  -- keep idx_qc_rule_result_qc from V13
```

### `QCRuleResult` — Over-Normalisation

The entity has 33+ columns mixing four concerns:

- **Rule outcome:** `rule_id`, `status`, `message`, `severity`
- **Reviewer workflow state:** `override_pending`, `review_session_token`, `decision_latency_ms`
- **UI display hints:** `appraisal_value`, `engagement_value`, `bbox_*`, `pdf_page`
- **ML training features:** `confidence_score`, `extracted_value`, `expected_value`

Long-term, these should be decomposed. For now, the existing design is workable but makes
the entity hard to reason about and contributes to a 300-400 byte average row size.

### Storage Recommendations

1. **Drop `python_response` blob** from `qc_result` — migrate to a separate `qc_raw_response`
   table with a foreign key, keeping the hot `qc_result` table lean
2. **Revert `audit_log.details` to JSONB** — V3 downgrade was a mistake
3. **Add Neon branching strategy** for schema migrations — use Neon branch per PR, migrate,
   verify, merge

---

## 6. Frontend UX & Product Experience Audit

### What Feels Enterprise-Grade

- **Visual design:** Dark theme, consistent Radix UI components, good information hierarchy
- **Keyboard shortcuts:** 20+ shortcuts covering reviewer queue navigation, rule filtering,
  decision recording, PDF zoom, focus mode — exceptional for enterprise productivity
- **Real-time progress:** Sub-stage progress bars with model name, elapsed time, smoothed
  percentage — users always know what the system is doing
- **PDF viewer:** Inline PDF rendering with page navigation and bounding-box highlighting
  that jumps directly to the flagged form field — extremely useful for reviewer workflow
- **Error message sanitisation:** Hibernate `OptimisticLockingFailureException` and similar
  internal messages are caught and replaced with user-friendly "refresh and retry" guidance

### Critical UX Gaps

**No QC rerun button.** The API exists (`POST /api/qc/process/{batchId}`), but there is no
rerun button in the frontend. Reviewers who spot a processing error cannot trigger re-OCR
without admin intervention.

**JWT expires mid-review with no warning.** A reviewer can spend 25 minutes on a document,
save decisions successfully, and then fail on submit because the 15-minute JWT expired
20 minutes earlier. There is no "Session expiring in 2 minutes" banner and no silent token
refresh.

**Token in WebSocket URL.** `getRealtimeUrl()` appends `?access_token={jwt}` to the WebSocket
URL. JWT tokens in URLs appear in server access logs, browser history, and any HTTP proxy
layer. This is a compliance risk for sensitive appraisal data.

**No bulk actions.** Processing 50 batches requires 50 individual reviewer assignments.
There is no multi-select checkbox on the batch list.

**Progress polling stops when admin navigates away.** `useBatchPolling` only runs on the
batches page. A batch completing QC while the admin is on the Users page generates no
notification.

**Reviewer queue is paginated, not virtual-scrolled.** At 500+ pending items, the page
controls require many clicks and render slowly.

### Missing Features for Enterprise Workflow

| Feature | User Impact |
|---------|-------------|
| Bulk batch assignment | High (50+ batches = 50 clicks) |
| Date range filtering on batches | High (can't find batches from last week) |
| Export QC results to CSV | Medium (reporting to clients) |
| Advanced search (by client, reviewer, rule ID) | Medium |
| QC rerun button | Medium (must go to admin to re-OCR) |
| Session expiry warning + auto-refresh | High (data loss risk mid-review) |
| Audit trail viewer per batch | Medium (compliance) |
| Side-by-side document comparison | Medium (cross-document rules) |
| Saved filter presets | Low |
| Undo last decision | Low |

---

## 7. Backend Scalability & Concurrency Analysis

### Thread Pool Configuration

```yaml
# AsyncConfig.java
corePoolSize:  2
maxPoolSize:   4
queueCapacity: 20
rejectionPolicy: CallerRunsPolicy   # ← 21st request blocks HTTP thread
```

With 4 max workers and OCR taking 5-15 minutes per batch, the platform supports
approximately 4 concurrent batches. The 21st queued batch causes the HTTP thread
that submitted it to block (CallerRunsPolicy), effectively halting new API requests.

**Target:** Increase `maxPoolSize` to 10, `queueCapacity` to 100, and switch rejection
policy to `AbortPolicy` with a `503` response to the client.

### Neon PostgreSQL Connection Pool

```yaml
hikari.maximum-pool-size: 10   # 10 concurrent DB connections per Java instance
hikari.minimum-idle: 2
```

Neon's free tier allows 20 concurrent connections total. With Python also connecting,
the effective Java budget is ~15 connections. This is adequate for single-instance
development but will be exhausted under load. The `REQUIRES_NEW` transactions in
`QCProcessingService` each consume a connection briefly, then release — this is the
correct pattern for Neon.

### Reviewer Lock Race Condition

`VerificationService.beginReviewSession()` checks for an existing lock with a plain
`@Transactional` read, then sets the lock in the same transaction. Two concurrent lock
attempts can both pass the "no active lock" check before either commits. The probability
is low but not zero.

**Fix:** Use `SELECT ... FOR UPDATE` on the lock acquisition query:
```java
@Lock(LockModeType.PESSIMISTIC_WRITE)
@Query("SELECT qr FROM QCResult qr WHERE qr.id = :id")
QCResult findByIdForLock(@Param("id") Long id);
```

### Unbounded Reviewer Queue Query

```java
List<QCResult> findPendingVerification();  // No Pageable — loads all pending results
```

At 10,000 pending results (each with ~136 rule results), this loads the entire queue
into memory, potentially several hundred MB. This will cause OOM under load.

**Fix:** Add `Pageable` parameter and return `Page<QCResult>`.

### WebSocket Scalability

Current WebSocket broadcast is per-JVM (Spring's internal STOMP). Adding a second Java
instance means clients connected to instance A won't receive broadcasts from instance B.

**Fix for multi-instance:** Use Redis pub/sub as the STOMP message broker:
```java
@Override
protected void configureMessageBroker(MessageBrokerRegistry config) {
    config.enableStompBrokerRelay("/topic", "/queue")
        .setRelayHost("redis-host")
        .setRelayPort(6379);
}
```

---

## 8. Security & Enterprise Risk Audit

### CRITICAL — Act Immediately

**Production credentials committed to repository:**

The file `apprisalArdur/.env` contains real Neon PostgreSQL credentials, JWT signing
secret, and admin password. If this file has ever been committed to git, those credentials
are in the git history permanently and must be considered compromised.

```
DB_PASSWORD=npg_3xwKmGDfrVy0         ← ROTATE NOW
JWT_SECRET=404E6352...                ← ROTATE NOW
ADMIN_PASSWORD=Admin123!              ← ROTATE NOW
PYTHON_API_KEY=apprisal-local-dev-key ← ROTATE NOW
```

**Immediate actions:**
1. Rotate the Neon database password from the Neon dashboard
2. Generate a new 256-bit JWT secret and deploy it to the environment
3. Change the admin password
4. Verify `.env` is in `.gitignore` and has never been committed:
   `git log --all --full-history -- .env`
5. If commits found: use `git filter-repo` to purge history and force-push all branches

**Redis unauthenticated on network:**

`docker-compose.yml` binds Redis to `0.0.0.0:6379` with no password. Any host on the
network can flush the Celery job queue or inject malicious tasks.

```yaml
# Fix:
redis:
  command: redis-server --requirepass "${REDIS_PASSWORD}"
  ports:
    - "127.0.0.1:6379:6379"    # localhost only
```

### HIGH Severity

| Issue | Location | Risk |
|-------|----------|------|
| JWT in localStorage | `frontend/lib/api.ts:8` | XSS leads to full session compromise |
| JWT in WebSocket URL | `frontend/lib/api.ts:354` | Token in server logs, browser history |
| No brute-force protection on `/api/auth/**` | `SecurityConfig.java:82` | Unlimited password attempts |
| Path traversal in ZIP extraction | `BatchService.java:~350` | Only checks literal `..`; URL-encoded paths may bypass |
| `job_dir` path injection (Python) | `celery_app.py:56` | `shutil.rmtree()` on attacker-controlled path |
| No token refresh / expiry handling | Frontend | Data loss mid-review; silent auth failure |
| `ddl-auto: update` in production | `application.yml:26` | Schema drift, data corruption |
| HSTS disabled | `SecurityConfig.java:131` | Session hijack on HTTP |
| `COOKIE_SECURE=false` default | `application.yml:59` | Cookies transmitted in plaintext |

### MEDIUM Severity

| Issue | Location | Risk |
|-------|----------|------|
| Review lock race condition | `VerificationService.java` | Two reviewers acquire same lock |
| Bulk deletes bypass Envers | `BatchService.java` | No audit trail for deleted QC data |
| Reviewer decision counters not atomic | `VerificationService.java` | Stale counts on concurrent decisions |
| Python `save_rule_results` not transactional | `cache_service.py` | Partial rule persistence |
| Anonymous WebSocket upgrade | `SecurityConfig.java:117` | `/ws/**` is permitAll (auth delegated) |
| Temp file accumulation | `celery_app.py` | Disk fills up after ~1000 jobs |
| No claim when Celery job result expires | `celery_app.py` | Results lost after 1 hour if not polled |

### Authentication & Authorisation Assessment

- **Object-level auth:** `FileController` enforces ownership on PDF downloads — correct.
  `BatchApiController` does NOT verify the batch belongs to the admin's client — any
  admin can delete any client's batch.
- **Horizontal privilege escalation:** Reviewer A can call `POST /api/reviewer/qc/{id}/session/start`
  with a QCResult ID they have no access to — no ownership check is performed.
- **Impersonation audit:** `ImpersonationService` exists; verify it logs the impersonation
  event to `audit_log` so there is a traceable record.

### Compliance Readiness

| Requirement | Status | Gap |
|------------|--------|-----|
| Immutable audit trail | Partial | Envers covers entity changes; manual audit_log is mutable TEXT |
| Data access logging | Partial | No logging of PDF download access |
| Session management | Partial | Max 5 concurrent sessions; no forced logout on password change |
| Encryption in transit | Partial | Neon uses SSL; Redis/Python service do not enforce TLS |
| Encryption at rest | Unknown | Neon handles DB encryption; local file storage unencrypted |
| Data retention policy | Missing | No archival or deletion policy on old batches |
| Reviewer action accountability | Good | Decision latency, session token, timestamp all recorded |

---

## 9. Missing Product Workflows & Enterprise Gaps

### QC Rerun Workflow

The API supports re-triggering QC (`POST /api/qc/process/{batchId}`), but:

1. There is no frontend button for rerun
2. Rerunning creates new `QCResult` + `QCRuleResult` rows — the old results are NOT
   preserved or marked superseded
3. If a reviewer had partially completed decisions on the old QCResult, those decisions
   are orphaned (the new QCResult starts fresh)

**Required design:**
- Mark old `QCResult` as `SUPERSEDED` (add status field or soft-delete)
- Link old and new via a `rerun_of` foreign key for history
- Frontend: show "Re-run QC" button on COMPLETED/ERROR batches
- Frontend: show QC history (list of QC runs per batch with timestamps and decision counts)

### QC Version Comparison

No capability exists to compare two QC runs on the same document (e.g., after appraiser
submits corrections). Required for any compliance workflow where the original and revised
appraisals must both be retained.

### Override / Escalation Workflow

`QCRuleResult` has `override_pending`, `override_requested_by/at`, `override_approved_by/at`
columns — the data model supports escalation. But there is no frontend UI for this workflow:

- Reviewer cannot request an override via UI
- Admin cannot see pending overrides
- No notification when override is requested/approved

### Operational Observability

| Gap | Impact |
|-----|--------|
| No Prometheus/Grafana metrics | Cannot alert on high error rates |
| No distributed tracing (OpenTelemetry) | Cannot trace a request across Java + Python |
| Python processing stages not timed in DB | Cannot identify which stage is slow |
| No health dashboard | Operations team cannot see system status at a glance |
| Celery queue depth not monitored | No alert when queue backs up |

---

## 10. Performance Bottleneck Analysis

### OCR Processing (Primary Bottleneck)

The dominant cost is the Python OCR pipeline:

| Stage | Cold (first run) | Warm (cached) |
|-------|-----------------|---------------|
| PyMuPDF embedded text | 0.01s/page | 0 (cache hit) |
| Tesseract OCR (4 workers) | 2-3s/page | 0 (cache hit) |
| LLM enrichment (Ollama) | 2-5s/call | ~0.1s (LLM cache) |
| Rule engine (136 rules) | ~0.1s | ~0.1s |
| **Total (27-page doc, cold)** | **~14-30s** | **~0.1-1s** |

The OCR cache is the single most important performance feature. A 14-second cold OCR
becomes 114ms on re-submission. Protecting this cache (SHA-256 dedup, DB persistence)
is critical.

### Database Query Performance

| Query | Risk | Fix |
|-------|------|-----|
| `findPendingVerification()` (no limit) | OOM at scale | Add `Pageable` |
| Batch list with `@Formula` subquery | N+1 on formula | Acceptable (1 COUNT per row) |
| QC result with document matches | 2 extra queries | JOIN FETCH |
| Analytics queries over all records | Slow at scale | Read replica / materialized views |

### Frontend Rendering

- Large batches (100+ files) in the batch detail view load all `BatchFile` entities —
  should be paginated
- Rule result list (136 rules per QC result) renders all at once — virtualisation needed
  for smooth scrolling on slow machines
- Analytics chart re-fetches on every `days` slider change — should debounce

### Batch Insert Performance (Resolved)

`batch_size=50` in `application.yml` reduces the 136 `QCRuleResult` INSERT statements
from sequential (50+ seconds on Neon) to ~1 second with batched multi-row inserts.
This is correctly configured and should not be changed.

---

## 11. Enterprise-Readiness Score

Scored across dimensions critical for a commercially deployable appraisal QC product.

| Dimension | Score | Rationale |
|-----------|-------|-----------|
| **Core QC Accuracy** | 8.5/10 | 136 rules, spatial extraction, LLM commentary — genuinely sophisticated |
| **Audit Trail** | 7/10 | Envers is solid; dual audit systems create confusion; bulk deletes untracked |
| **Security** | 3/10 | Credentials in repo, localStorage JWT, Redis unauthed — CRITICAL gaps |
| **Frontend UX** | 7.5/10 | Excellent keyboard nav and design; missing bulk actions, expiry handling |
| **Backend Reliability** | 6/10 | In-memory state, race conditions, no rate limiting |
| **Scalability** | 5/10 | Single JVM bottleneck, unbounded queries, no distributed state |
| **Observability** | 3/10 | Basic logging only; no metrics, tracing, or dashboards |
| **Data Correctness** | 6.5/10 | Mostly correct; sentinel leakage, confidence bug (fixed), partial saves |
| **Documentation** | 4/10 | Previous docs described a different architecture; now updated |
| **Deployment Readiness** | 3/10 | `ddl-auto: update`, hardcoded secrets, no TLS enforcement |
| **Compliance** | 4/10 | Data model supports compliance; execution is incomplete |
| | **Overall: 5.3/10** | |

**Verdict:** The platform has a sophisticated, well-thought-out core (OCR, rules, workflow).
It is demonstrably more capable than the documentation suggested. However, it is not
yet commercially deployable due to critical security vulnerabilities and missing operational
hardening. With 4-8 weeks of focused effort on the items below, it can reach 8+/10.

---

## 12. Prioritised Remediation Roadmap

### IMMEDIATE — Before Any External Demo or Deployment (Week 1)

| # | Task | Owner | Effort |
|---|------|-------|--------|
| I-1 | **Rotate all secrets** (Neon password, JWT secret, admin password) | DevOps | 2h |
| I-2 | **Add Redis `requirepass`**, bind to `127.0.0.1:6379` | DevOps | 1h |
| I-3 | **Verify `.env` files are in `.gitignore` and never committed** (`git log --all -- .env`) | DevOps | 1h |
| I-4 | **Add brute-force protection on `/api/auth/**`** (5 attempts/min via IP; use Spring Security's `failureHandler` or Bucket4j) | Backend | 4h |
| I-5 | **Fix `job_dir` path injection in Celery** — validate path is within `SAFE_JOB_ROOT` before `shutil.rmtree()` | Python | 3h |
| I-6 | **Fix temp file accumulation** — always cleanup in `finally` block regardless of success/failure | Python | 2h |

### SHORT-TERM — Before User Acceptance Testing (Weeks 2-3)

| # | Task | Owner | Effort |
|---|------|-------|--------|
| S-1 | **Migrate to Flyway** — disable `ddl-auto: update`, write V20 migration to capture current schema state, enable Flyway `validate` | Backend | 1 day |
| S-2 | **Move JWT from localStorage to httpOnly cookie** — backend sets `Set-Cookie` on login; frontend stops managing token manually | Full-stack | 1 day |
| S-3 | **Remove JWT from WebSocket URL** — pass token via `Sec-WebSocket-Protocol` header or first-message auth | Full-stack | 4h |
| S-4 | **Add JWT expiry warning + auto-refresh** in frontend — intercept `401` responses, silently refresh, retry request | Frontend | 6h |
| S-5 | **Add QC Rerun button** — `POST /api/qc/process/{batchId}` from admin batch detail page | Frontend | 2h |
| S-6 | **Fix reviewer lock race condition** — `SELECT FOR UPDATE` in `beginReviewSession()` | Backend | 3h |
| S-7 | **Add `Pageable` to `findPendingVerification()`** — prevents OOM at scale | Backend | 2h |
| S-8 | **Validate `job_dir` in Python OCR service** — ensure path is within job root | Python | 3h |
| S-9 | **Enable HSTS** in `SecurityConfig` for production profile | Backend | 1h |
| S-10 | **Set `COOKIE_SECURE=true`** as default; make `false` require explicit opt-in | Backend | 1h |
| S-11 | **Add missing database indexes**: `(qc_result_id, status)`, `(user_id, created_at DESC)` | DBA | 1h |
| S-12 | **Add `BatchApiController` client-isolation check** — admin can only act on their client's batches | Backend | 3h |
| S-13 | **Wrap `save_extracted_fields` + `save_rule_results` in a single DB transaction** | Python | 2h |
| S-14 | **Fix OCR cache fallback** — disk-based journal when DB is unavailable | Python | 6h |

### MEDIUM-TERM — Before Production Launch (Month 1-2)

| # | Task | Owner | Effort |
|---|------|-------|--------|
| M-1 | **Bulk batch actions in admin UI** — multi-select, bulk assign, bulk delete | Frontend | 2 days |
| M-2 | **QC history/versioning** — `QCResult.rerun_of` FK, `SUPERSEDED` status, history view | Full-stack | 3 days |
| M-3 | **Override/escalation workflow UI** — request override, admin approval queue | Full-stack | 2 days |
| M-4 | **Move QC progress state to Redis** — replace `ConcurrentHashMap` with Redis hashes | Backend | 2 days |
| M-5 | **Add OpenTelemetry** to Java and Python — export to Jaeger or Honeycomb | Full-stack | 2 days |
| M-6 | **Add Prometheus metrics endpoint** — JVM, queue depth, OCR timings, rule pass rates | Backend | 1 day |
| M-7 | **Horizontal reviewer access control** — verify reviewer can only access assigned batches | Backend | 1 day |
| M-8 | **Export to CSV** — batches, QC results, reviewer decisions | Frontend | 1 day |
| M-9 | **Advanced filtering** — date range, client, reviewer on batch list | Frontend | 1 day |
| M-10 | **Revert JSONB downgrade** — V20 migration: `ALTER COLUMN details TYPE JSONB USING details::jsonb` | DBA | 2h |
| M-11 | **Python Celery result durability** — ensure `processing_jobs.result_json` is always written; remove Redis as sole result store | Python | 4h |
| M-12 | **Request timeout handling in frontend** — wrap `fetch()` with `AbortController`, show timeout error | Frontend | 3h |

### LONG-TERM — Enterprise Scale (Quarter 2-3)

| # | Task | Owner | Effort |
|---|------|-------|--------|
| L-1 | **Redis STOMP broker** for multi-instance WebSocket | Backend | 3 days |
| L-2 | **Separate OLAP analytics** — materialized views or read replica for dashboard queries | DBA | 1 week |
| L-3 | **S3/object storage** for uploaded ZIPs and PDFs (replace local disk) | Backend | 1 week |
| L-4 | **Multi-tenant isolation** — row-level security on critical tables by `client_id` | DBA | 1 week |
| L-5 | **Decompose `QCRuleResult`** — separate RuleOutcome, ReviewWorkflow, UIHints entities | Backend | 2 weeks |
| L-6 | **Dead-letter queue** for failed Celery tasks — admin retry UI | Python/Backend | 1 week |
| L-7 | **API gateway** (Kong or AWS API GW) — rate limiting, auth, TLS termination | Infra | 1 week |
| L-8 | **SOC 2 / GLBA preparation** — formal data retention policy, tamper-evident audit logs, access reviews | Compliance | Ongoing |

---

## 13. Long-Term Architecture Recommendations

### Target Architecture (18 months)

```
                    ┌──────────────────────────────┐
                    │   CDN + API Gateway           │
                    │   (TLS termination,           │
                    │    rate limiting, WAF)         │
                    └──────────────┬───────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                    │
       ┌──────▼──────┐     ┌───────▼──────┐     ┌──────▼──────┐
       │  Java Inst  │     │  Java Inst   │     │  Java Inst  │
       │  (stateless)│     │  (stateless) │     │  (stateless)│
       └──────┬──────┘     └───────┬──────┘     └──────┬──────┘
              └────────────────────┼────────────────────┘
                                   │
         ┌─────────────────────────┼─────────────────────────┐
         │                         │                         │
  ┌──────▼──────┐           ┌──────▼──────┐           ┌──────▼──────┐
  │  Redis      │           │  Neon       │           │  S3 / GCS   │
  │  Cluster    │           │  PostgreSQL │           │  (Files)    │
  │  (WS, queue,│           │  + Read     │           │             │
  │   progress) │           │  Replica    │           └─────────────┘
  └─────────────┘           └─────────────┘
  
  ┌───────────────────────────────────────────────────────────┐
  │  Python OCR Worker Pool  (Kubernetes HPA or ECS tasks)    │
  │  N × { FastAPI + Celery worker + Ollama sidecar }         │
  └───────────────────────────────────────────────────────────┘
```

### Key Migration Steps

1. **Now → Flyway + secrets management** — establish schema control and remove credential risk
2. **Month 1 → Redis state** — make Java stateless; enable horizontal scaling
3. **Month 2 → S3 storage** — move uploaded ZIPs/PDFs off local disk; enable horizontal scaling
4. **Month 3 → Celery autoscaling** — Python worker pool scales with OCR queue depth
5. **Month 6 → Neon read replica** — separate OLTP writes from analytics reads
6. **Month 12 → Multi-tenant isolation** — row-level security per client; proper tenant billing

### Zero-Trust Security Recommendations

| Layer | Current | Target |
|-------|---------|--------|
| Auth tokens | localStorage JWT | httpOnly, Secure, SameSite=Strict cookie |
| Python service auth | Optional API key | Mutual TLS + short-lived API keys rotated by Vault |
| Redis | No auth | TLS + strong password + ACL per consumer |
| Internal service calls | Plain HTTP | mTLS via service mesh (Istio/Linkerd) |
| File storage | Local disk, no encryption | S3 with SSE-KMS, pre-signed URLs |
| Secrets | `.env` files | HashiCorp Vault or AWS Secrets Manager |
| Logging | Unstructured | Structured JSON → SIEM (no PII in logs) |

---

*Document maintained by the Apprisal engineering team.*
*For architecture diagrams, see [ARCHITECTURE.md](./ARCHITECTURE.md)*
*For complete API reference, see [API_REFERENCE.md](./API_REFERENCE.md)*
