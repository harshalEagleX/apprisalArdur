# Apprisal Platform — Scalability & Performance Engineering Plan

> **Purpose:** Take the platform from its current single-box, synchronous design to a
> deployment that reliably serves **50+ concurrent users**, stores **up to 5,000 source
> documents**, processes **250+ documents/day** through the Python + Java pipeline, and
> keeps every read/write path fast under load.
>
> **Scope rule:** Everything here stays *within the bound of this project* — the existing
> Java (Spring Boot, multi-module) + Python (FastAPI/OCR/QC) + Next.js stack, PostgreSQL,
> and local document storage. No re-platforming.
>
> **This document is the single source of truth for the scaling effort.** It is kept
> current by the `/scale-plan` skill (`.claude/skills/scale-plan.md`). Update the
> **Progress Tracker** and **Measured Baselines** sections as each increment lands.
>
> **Engineering discipline:** This plan obeys the platform principles in
> `ocr-service/CLAUDE.md` — especially **P-7** (deployable increments), **P-8** (define
> measurement before building), **P-1** (three-level "done"), **P-13** (measure before
> optimizing), and **P-4** (configuration over hardcoding).

---

## 0. Decisions (locked 2026-06-15)

| Decision | Choice | Consequence for the plan |
|---|---|---|
| **Deployment target** | One tuned host, **8–16 cores / 32–64 GB RAM** | Single logical instance of each service; sizing math below assumes this host. |
| **Job queue** | **Redis + Celery** | Wire the durable queue the Java side *already calls* (`/qc/submit`, `waitForJobResult`, `isCeleryWorkerRunning`). |
| **Document storage** | **Local filesystem + backups** | Keep `./uploads` on a sized volume; add scheduled backup + retention + disk alerts. |
| **First increment focus** | **All four** — throughput, read/query perf, concurrency correctness, observability | Phases 1–6 below cover all four; each ships independently. |
| **LLM** | **Groq cloud** (`gpt-oss-120b` text, `llama-4-scout` vision), 6k TPM | Shared token budget is the throughput ceiling once the queue is in place — see §4 and Risk R-1. |

---

## 1. Targets (the contract this plan must satisfy)

| # | Target | Definition of met | Measurement |
|---|---|---|---|
| T-1 | **50+ concurrent users** | 50 simultaneous reviewer/admin sessions; p95 read latency < 400 ms; no 5xx | k6 load test, 50 VUs (§Phase 6) |
| T-2 | **5,000 documents stored** | DB + filesystem hold 5,000 appraisals (≈1.4M `qc_rule_result` rows) with read paths still < 400 ms p95 | Seeded soak DB + EXPLAIN ANALYZE |
| T-3 | **250+ docs/day processed** | Sustained 250 docs through OCR→QC→persist in a 24 h window, incl. an 8 h burst of ≥31 docs/h, zero lost jobs | Processing soak test (§Phase 6) |
| T-4 | **Fast read/write** | Reviewer queue, report load, decision save all p95 < 400 ms at T-1 load | Per-endpoint metrics |
| T-5 | **Low latency / perfect perf** | No request blocked by a multi-minute OCR call; processing is async/durable | Architecture (Phase 1) + load test |
| T-6 | **Smart queries / every edge case** | The edge-case matrix in §7 is handled and tested | Unit/integration tests per row |

> **Honesty clause (P-8):** A target is "met" only when its measurement passes. Until the
> load test in Phase 6 runs, these are *design intents*, not achievements.

---

## 2. Current-state architecture (evidence-based)

```
Next.js (admin + reviewer)  ──HTTP/WS──▶  Spring Boot (single instance)
                                              │
                          qcTaskExecutor (core=max=2, queue=100)   ◀── HARD CAP 2 docs
                                              │  synchronous HTTP POST /qc/process (900s timeout)
                                              ▼
                                   FastAPI / uvicorn (SINGLE process)
                                              │  run_in_threadpool → OCR + Groq LLM + rules
                                              ▼
                                   PostgreSQL (Hikari=10 / SQLAlchemy 5+10)
                                   Local FS ./uploads
```

**Key facts established by reading the code:**

| Area | Finding | Evidence |
|---|---|---|
| Processing concurrency | Java QC executor is a **hard cap of 2** concurrent documents, explicitly sized "on an 8GB box" | `app/.../config/AsyncConfig.java:33-39` |
| Async queue | **Half-built.** Java calls `/qc/submit`, `submitQCJob`, `waitForJobResult`, `isCeleryWorkerRunning` | `qc/.../PythonClientService.java:354-470,577-585` |
| Async queue | **Python has no Celery/Redis** — `requirements.txt` is FastAPI-only; no `/qc/submit`; `/health` never returns `celery_worker_running` → `isCeleryWorkerRunning()` is **always false** → every doc takes the **synchronous** path | `ocr-service/requirements.txt`, `ocr-service/main.py:89-100,150` |
| Progress state | **In-memory on both sides** — `progressByBatch` map (Java), `_QC_PROGRESS` dict (Python). Lost on restart. | `QCProcessingService.java:66-70`, `main.py:136` |
| DB pool | Hikari `maximum-pool-size: 10` (prod), `5` (dev); Python SQLAlchemy `pool_size=5, max_overflow=10` **per process** | `app/.../application.yml:17-24`, `ocr-service/app/database.py:17-23` |
| Indexes | Mostly present on hot tables; **`scripts/add_missing_indexes.sql` exists but is not applied automatically** | entity `@Index` annotations; `scripts/add_missing_indexes.sql` |
| Read path | Partly optimized — `JOIN FETCH`/`@EntityGraph`/`Pageable` already used; pending queue paginated, **submitted queue + per-result rules are not** | `QCResultRepository.java`, `ReviewerApiController.java:72,379` |
| Persistence | Hibernate `batch_size: 50`, `order_inserts/updates` on; QC events fired `@Async` after status flip | `application.yml:39-44`, `QCProcessingService.java:925` |
| Resilience present | Content-hash OCR cache (`cacheHit`), `@Version` optimistic locking, `StuckBatchReconciler`, graceful degradation (P-6) | scattered — keep and build on these |

**Bottom line:** the architecture *anticipates* scaling (the Celery contract, the cache, the
reconciler) but the throughput half was never finished, and all sizing is pinned to an 8 GB
laptop. The work is to **finish the queue, re-size for the new host, harden the read path,
and prove it.**

---

## 2A. Service inventory — the bounds we are covering

> Result of a service-by-service read of both backends (June 2026). Profile legend:
> **DB** = database-query-bound · **IO** = disk/file-bound · **NET** = network (Python/Groq)
> · **CPU** = compute-bound · **LLM** = Groq-bound · **WS** = WebSocket push · **MEM** = in-memory state.

### Java services (Spring Boot, single instance)

| Service / area | Responsibility (the bound it covers) | Profile | Query/latency note |
|---|---|---|---|
| `AuthController` + `UserService` + `AuthRateLimitFilter` | Login, register, JWT issue, rate-limit | CPU (BCrypt), DB | BCrypt ~100 ms/login; rate-limited; fine at 50 users |
| `DashboardApiController` | `/me`, role dashboards | DB (light) | Small reads; cache `/config/password-policy` |
| `BatchService` | ZIP upload → extract → SHA-256 → per-file rows; list; delete (file+DB) | CPU(hash)+IO, DB | Upload runs on the request thread; hash in memory (25 MB cap); dedup by hash (idempotent) |
| `BatchApiController` | Batch CRUD + `/{id}/status` (polled during processing) | DB | Status polled frequently — keep cheap; list is paginated (`@EntityGraph`) |
| `FileMatchingService` | Group appraisal/engagement/contract within a batch | CPU (in-mem) | Per-batch, small N; not a hotspot |
| `FileController` `/files/{id}` | Stream source PDF to the reviewer viewer | **IO** | 50 reviewers streaming multi-MB PDFs from local disk — see QL-13 |
| `QCProcessingService` | Orchestrate batch QC: match → Python → persist → decide | MEM, NET, DB | **Hard cap 2** workers; in-memory progress; long Python call kept outside DB txn (good) |
| `PythonClientService` | All HTTP to Python (process/submit/poll/health) | **NET** | No conn pool; 900 s timeout shared with health/poll — see QL-8 |
| `QCApiController` | Trigger/cancel/progress/results/history/findings | DB, WS | History/diff endpoints load full result graphs |
| `ReviewerApiController` | Reviewer queue, rules, decision save, session, overrides | DB, WS | `pending` paginated; **`submitted` + `/rules` are not** — QL-7 |
| `VerificationService` | Decision save / submit / override (reviewer hot path) | DB (locks) | Pessimistic row lock per `QCResult` (5 s); per-item `.save()` loops — QL-12 |
| `AnalyticsService` | All admin dashboards (overview/OCR/ML/operators/SLA/anomaly) | **DB (heavy)** | N+1 over users; double full-list SLA loads; ~8–12 aggregates/load — QL-4/5/6 |
| `AnalyticsApiController` | `/api/analytics/*` (7 endpoints) | DB | Polled by dashboards; prime cache target |
| `AuditGraphController` | Audit graph overview/batch/file/reviewer/search | DB (heavy) | Builds graphs from `business_event`+`audit_log` — verify index use at 5k docs |
| `AdminApiController` | Users/clients CRUD, system health, batch audit/assign | DB | Mostly light; `/system/health` should not call Python with 900 s timeout |
| `DocStatsApiController` + `DocStatRepository` | Per-doc timing dashboards (list/ranking/trend/compare) | DB (aggregates) | Paginated + grouped queries already; good pattern to mirror |
| `BusinessEventService` | Capture business events (≈138/doc) | **DB (write)** | `REQUIRES_NEW` per event **and** bulk `recordAll`/`recordAllAsync` — QL-10 |
| `AuditLogService` | Audit-log writes (+ Envers revisions) | DB (write) | Doubles write volume; index present |
| `OperatorSessionService` | Operator session lifecycle + `@Scheduled` cleanup (5 min) | DB, MEM | One of only two scheduled jobs |
| `StuckBatchReconciler` | `@Scheduled` (10 min) requeue/abandon stuck `QC_PROCESSING` | DB | Extend to cover Celery jobs — Phase 4 |
| `QCProgressStore` + realtime publishers | In-memory progress + STOMP/WebSocket push | **MEM, WS** | Lost on restart; move to Redis — QL-11 |

### Python services (FastAPI / OCR / QC — single process today)

| Service / module | Responsibility | Profile | Query/latency note |
|---|---|---|---|
| `main.py` endpoints | `/qc/process` (live sync path), `/health`, `/qc/progress`, corrections, baseline, validate, routing, amc, `/qc/transaction(s)`, `/qc/report` | NET | `/qc/process` is the long pole; `/qc/transactions` is N+1 — QL-9 |
| `qc/transaction.py` `run_transaction_qc_paths` | Live per-doc QC: extract 3 docs + overlays (incl. Groq `sca_llm`/`subject_llm`) + rule engine + persist | **CPU+IO+LLM** | Long, mostly sequential; the per-document latency budget lives here |
| `qc/engine.py` | Rule engine (`run_qc`, `persist_report`) ~146 rules | CPU | <100 ms on cached docs |
| `qc/report.py` | `transaction_report` read path (dedupe latest per rule) | DB | Fine per-transaction; the loop is in the `/qc/transactions` caller |
| `services/pipeline_runner.py` | Adaptive pipeline (baseline/corpus): per-page + per-field persist | CPU+IO, DB(write) | ~120–170 extraction rows + N page rows per doc |
| `ocr/pipeline.py` + `adaptive_ocr.py` | Per-page OCR: PyMuPDF direct vs Tesseract scanned | **CPU** | ~400–500 MB peak; cached by `file_hash` (indexed) |
| `extraction/llm_groq.py` | Groq calls + **process-local** TPM throttle (`GROQ_TPM_LIMIT`) | **LLM, NET** | `_tpm_lock` per process → breaks across workers — QL-2 |
| `extraction/llm_resilience.py` | Legacy Ollama path: **process-local** `Semaphore(1)` + 2 s min interval | LLM | Suppressed but still serializes Ollama within a process |
| `extraction/*` overlays | `comp_grid`(Camelot), `sca_grid`, `sca_llm`, `subject_llm`, `narrative`, `photos`, `sketch`, embeddings tier | CPU/LLM | Sequential overlays add up; LLM overlays are the Groq-bound ones |
| `services/` (classifier, semantic_validator, routing_config, correction, amc_profile, cross_document_checker) | Classification, validation, per-field thresholds, feedback | CPU, DB | `routing_config.get_thresholds` called per field — cache in-process |
| `database.py` | SQLAlchemy engine (`pool_size=5, max_overflow=10` **per process**) | DB | Over-subscribes Postgres once workers multiply — shrink to 2/3 (Phase 2) |

---

## 2B. Query & latency findings (the new, concrete work items)

> Each finding is tied to the phase that fixes it. These are the specifics behind the
> "fast read/write" (T-4) and "smart query / every edge case" (T-6) targets.

| ID | Finding (evidence) | Impact | Phase |
|---|---|---|---|
| **QL-1** | Live QC is one long **synchronous** `/qc/process` call (up to 900 s) per doc; no durable queue (`main.py:150`, `PythonClientService.processQC`) | Blocks a worker for minutes; restart loses in-flight work | 1 ✅ built (queue verified) |
| **QL-2** | Groq TPM throttle (`_tpm_lock`/`GROQ_TPM_LIMIT`) and LLM `Semaphore(1)` are **process-local** (`llm_groq.py:35-57`, `llm_resilience.py:43`) | Multiple workers each keep their own counter → collective 429s; true ceiling is the account TPM | 2 ✅ Redis token bucket (verified) |
| **QL-3** | **No caching layer anywhere** — zero `@Cacheable`/`CacheManager`/Caffeine | Rules registry, schema, clients, AMC profiles, routing thresholds re-queried every request | 3 ✅ Caffeine 30s cache (built) |
| **QL-4** | AnalyticsService **N+1**: `userRepo.findById(userId)` inside per-row loops (`AnalyticsService.java:136,203,217`) | Dashboard latency scales with #operators | 3 ✅ batch `findAllById` (built) |
| **QL-5** | `getReviewSlaDashboard` calls `findOverdueReviewItems` **twice**, materializes full lists just for `.size()`, walks lazy `rule→qc→file` (`AnalyticsService.java:172-186`) | Heavy at scale; load grows with overdue count | 3 ✅ COUNT + top-50 (built) |
| **QL-6** | Overview/OCR/ML dashboards run ~8–12 aggregate COUNT/AVG per load over time windows | 50 users polling → repeated full aggregates | 3 ✅ cached (30s TTL) |
| **QL-7** | Unbounded `List<>` finders on growing tables: `findByBatchId`, `findByQcDecision`, `findPendingVerification`, `findByEntityTypeAndEntityId`, `findByBatchIdOrderByOccurredAtAsc`; reviewer **`submitted` queue** + per-result **`/rules`** not paginated (`ReviewerApiController:72,379`) | Memory + latency spikes at 5k docs | 3 |
| **QL-8** | One `RestTemplate` with `SimpleClientHttpRequestFactory` (**no pool**) and `readTimeout=900 s` applied to **every** Python call incl. `/live` health + progress polls (`RestTemplateConfig.java:20-22`) | A hung Python can block a health check for 15 min; no connection reuse under concurrency | 1 ✅ split (pooled JDK client) |
| **QL-9** | `/qc/transactions` builds the reviewer picker by looping **every** distinct `transaction_id` → `transaction_report(tid)` each (`main.py:443-470`) | N+1 across the whole table on dashboard load | 3 |
| **QL-10** | ≈138 `QCRuleResult` + ≈138 `BusinessEvent` + metrics + ≈138 `DocStatRule` per doc → **~70k+ rows/day** at 250 docs; `business_event`/`audit_log` grow fastest | Table bloat; bulk insert already used, but needs retention/partition | 0 (index) / 5 (partition) |
| **QL-11** | Progress is **in-memory** both sides (`QCProgressStore`/`progressByBatch`, `_QC_PROGRESS`) | Lost on restart; not shareable | 4 |
| **QL-12** | VerificationService save loops `.save()` per item; reviewer decision uses pessimistic row lock (`VerificationService.java:157-164,375-379`) | Minor; relies on Hibernate batching; lock only contends on same result | 3 ✅ `saveAll` (built) |
| **QL-13** | `FileController GET /files/{id}` streams source PDFs from local disk to the viewer | 50 reviewers loading multi-MB PDFs = disk-IO bound | 5 (volume) + add HTTP caching headers |

**Two scheduled jobs total** (`StuckBatchReconciler` 10 min, `OperatorSessionService` 5 min) —
no other background sweeps; the queue/reconciler work in Phases 1/4 is the right place to add
job-level recovery rather than more polling loops.

---

## 3. Gap analysis — why current ≠ targets

1. **Throughput ceiling = 2 concurrent docs, synchronous.** At ~2–4 min/doc with Groq, two
   workers yield ~30–60 docs/h *best case* and **zero durability** — a restart mid-batch
   loses in-flight work. A 250-doc burst has no safe landing zone. (Blocks T-3, T-5.)
2. **Single uvicorn process.** CPU-bound OCR under the GIL + a shared in-process Groq
   throttle means the two Java workers partially **serialize** inside Python. (Blocks T-3.)
3. **Pool/host sizing is laptop-grade.** Hikari=10, no Postgres tuning, per-worker
   SQLAlchemy pools that would *over*-subscribe Postgres once workers multiply. (Blocks T-1/T-2.)
4. **Read path gaps (see §2B QL-3…QL-9).** No caching layer anywhere; AnalyticsService
   dashboards do per-row user N+1 and double full-list SLA loads; the `/qc/transactions`
   picker is N+1 across the table; the `submitted` queue + per-result `/rules` are unpaginated
   and build `Map`s from full entity graphs; the shared `RestTemplate` has no pool and a 900 s
   timeout on health/poll. Memory + latency spikes at 5,000 docs / 50 users. (Blocks T-4.)
5. **No proof.** No load test, no slow-query logging, no throughput dashboard. Can't claim
   any target is met. (Blocks T-1…T-6 verification.)
6. **Restart-fragile state.** In-memory progress + no durable job record = lost jobs and
   stuck batches under real concurrency. (Blocks T-5, T-6.)

---

## 4. Target architecture (single host)

```
Next.js ──HTTP/WS──▶ Spring Boot (1 instance)
                         │ enqueue + poll (I/O-bound, light pool)
                         ▼
                      Redis  ◀── broker + result backend + distributed Groq token bucket + progress
                         │
                  Celery workers (N prefork, sized to host)  ── OCR + Groq + rules
                         │                                       (shared OCR cache by content hash)
                         ▼
                  PostgreSQL (tuned; PgBouncer optional)   +   Local FS ./uploads (backed up)
```

### 4.1 Capacity / sizing model (12 core / 48 GB reference; scale within 8–16 / 32–64)

**Memory budget (48 GB host):**

| Component | Reserve |
|---|---|
| OS + headroom | 3 GB |
| PostgreSQL (`shared_buffers` 8 GB + work) | ~12 GB |
| Spring Boot (heap `-Xmx4g`) | 5 GB |
| Next.js (Node) | 2 GB |
| Redis | 2 GB |
| **Available for Celery workers** | **~24 GB** |

A Celery worker peaks ~0.5–1 GB during OCR → RAM allows **~16 workers**; CPU is the real
limit. Leave ~4 cores for Postgres + Java + Node → **Celery concurrency = 6–8** (prefork).

**Throughput:**
- OCR/rules-bound docs: 7 workers × (one doc / ~2.5 min) ≈ **~168 docs/h** → 250/day with wide margin.
- **Groq-bound stages are gated by 6k TPM, shared across all workers.** A distributed
  Redis token bucket (Phase 2) shares the budget correctly but means LLM-heavy stages
  *serialize* near the cap. **This — not CPU — is the true ceiling.** See Risk **R-1**:
  to get full parallel throughput, raise the Groq tier; otherwise size expectations to the
  token budget and lean on the content-hash cache for reruns.

**Recommended config (all P-4 configurable):**

| Knob | Current | Target (12c/48GB) | Where |
|---|---|---|---|
| Celery worker concurrency | — | `6` (`--concurrency=6`, prefetch=1) | new `celery_app.py` / systemd |
| Java `qc.executor.*` (now enqueue+poll, I/O-bound) | core=max=2 | core=`4`, max=`8`, queue=`200` | `AsyncConfig.java` via props |
| Hikari `maximum-pool-size` | 10 | `30` (min-idle `10`) | `application.yml` |
| SQLAlchemy `pool_size` / `max_overflow` **per worker** | 5 / 10 | `2` / `3` | `database.py` |
| Postgres `max_connections` | default 100 | `200` (or PgBouncer txn pooling) | `postgresql.conf` |
| Postgres `shared_buffers` / `effective_cache_size` / `work_mem` | defaults | `8GB` / `24GB` / `32MB` | `postgresql.conf` |
| Tomcat max threads | default 200 | keep `200` | (default ok for 50 users) |
| Spring `-Xmx` | default | `4g` | launch flag |

> **Connection arithmetic (must hold):** Java 30 + (7 workers × 5) 35 + reconciler/health
> ≈ 70 < 200. If workers grow, add **PgBouncer** (transaction pooling) instead of raising
> `max_connections` further.

---

## 5. Phased implementation plan

Each phase is an independently deployable increment (P-7) with an explicit measurement gate
(P-8) and three-level "done" (P-1). **Do not start a phase before the prior phase's gate passes.**

### Phase 0 — Baseline, safety net, indexes *(no behavior change)*
**Goal:** Know today's numbers; make later phases measurable and safe.
- Apply `scripts/add_missing_indexes.sql` to the target DB (idempotent, `IF NOT EXISTS`).
- Turn on Postgres slow-query log: `log_min_duration_statement = 500ms`.
- Expose Hikari + JVM metrics via Actuator (`management.endpoints...include: health,metrics,prometheus`).
- Capture **Measured Baselines** (below): per-doc processing time, reviewer-queue p95, max
  safe concurrent docs, current docs/h.
- **Gate:** baseline table filled in with real numbers. **Done(L2):** numbers reproducible.

### Phase 1 — Durable job queue (Redis + Celery)  ⟵ *biggest throughput lever (T-3, T-5)*
**Goal:** Finish the async contract Java already speaks; decouple processing from HTTP.
- Add `redis`, `celery` to `ocr-service/requirements.txt`; add `celery_app.py` (broker +
  result backend = Redis) and a `tasks.py` `qc_process_task` that calls the existing
  `run_transaction_qc_paths` (reuse, don't re-implement).
- Add FastAPI endpoints to match the Java client **exactly**:
  - `POST /qc/submit` → enqueue task, return `{job_id}` (Celery task id).
  - `GET /qc/jobs/{job_id}` (or whatever `waitForJobResult` polls) → status/result.
  - `/health` → include `"celery_worker_running": <bool>` so `isCeleryWorkerRunning()` works.
- Run worker: `celery -A celery_app worker --concurrency=6 --prefetch-multiplier=1` (systemd unit).
- Keep the **synchronous `/qc/process` path as the fallback** (already coded in Java) — graceful degradation (P-6).
- **Split the `RestTemplate` (QL-8):** replace `SimpleClientHttpRequestFactory` with a pooled
  Apache `HttpClient`, and use a **short-timeout** client (~5 s) for `/live` health, `/qc/submit`,
  and progress polls; reserve the long (900 s) timeout only for the now-deprecated sync call.
  This stops a hung Python from blocking health checks for 15 minutes and reuses connections.
- **Gate (P-8):** with the worker up, Java takes the async path (log shows `submitQCJob`,
  not `python_sync`); kill+restart Java mid-batch → **no job lost**, batch resumes/completes.
- **Done(L3):** worker restarts cleanly; queue depth visible.

### Phase 2 — Throughput sizing + Groq rate limiter + cache  *(T-3)*
**Goal:** Hit 250+/day with margin; share the Groq budget correctly.
- Set Celery `--concurrency`, Java `qc.executor.*`, SQLAlchemy pool per §4.1 (config only).
- Replace the in-process Groq throttle with a **Redis distributed token bucket** (6k TPM
  shared across workers) in `app/extraction/llm_groq.py` / `llm_resilience.py`.
- Verify the content-hash OCR cache short-circuits reruns (already wired via `cacheHit`);
  add a cache-hit-rate metric.
- **Gate:** processing soak — push 250 docs in 8 h; **all complete, zero lost**, p95
  per-doc within target; Groq rate-limit hits logged but not fatal.
- **Done(L2):** documented docs/h with N workers.

### Phase 3 — Read/query performance for 50 users  *(T-1, T-4 — fixes QL-3…QL-9, QL-12)*
**Goal:** Every read path fast and bounded under concurrency.
- **Paginate the unbounded reads (QL-7):** reviewer `submitted` queue + per-result `/rules`
  first (mirror the existing `pending` `Pageable` pattern); bound the other `List<>` finders
  on hot paths.
- **Kill the dashboard N+1 (QL-4):** in `AnalyticsService.getOperatorInsights` /
  `getWeeklyAnomalyReport`, collect the user-id set and batch-fetch with `findAllById` instead
  of `userRepo.findById` per row.
- **Fix the SLA dashboard (QL-5):** replace the two full-list `findOverdueReviewItems` loads
  with COUNT queries for the 4 h/8 h totals + one bounded projection for the 50 shown rows.
- **De-N+1 the transaction picker (QL-9):** replace the `/qc/transactions` per-id loop with a
  single grouped query (status counts per `transaction_id`).
- Replace controller `Map`-from-entity building with **DTO projections** (interface/record
  projections) for list views so 138-row rule graphs aren't hydrated for lists.
- **Add caching (QL-3):** Caffeine `@Cacheable` for read-mostly hot data — rules registry,
  field schema, client list, AMC profiles, routing thresholds, and short-TTL analytics
  snapshots (QL-6) — with explicit eviction on write.
- Apply the §4.1 Hikari + Postgres tuning; add HTTP cache headers to `/files/{id}` (QL-13).
- Minor: switch VerificationService per-item `.save()` loops to `saveAll` (QL-12).
- Audit hot endpoints with `EXPLAIN ANALYZE` against the seeded 5,000-doc DB.
- **Gate:** k6 at 50 VUs on reviewer+admin reads → **p95 < 400 ms, 0 5xx**; no full-table
  scans on hot paths (verified via slow-query log).
- **Done(L2):** per-endpoint latency table recorded.

### Phase 4 — Concurrency correctness & resilience  *(T-5, T-6)*
**Goal:** 50 users + parallel processing stay consistent; nothing gets stuck.
- Move live progress to **Redis** (key per batch/job) so it survives Java restart and is
  consistent (single instance today, but this also unblocks future horizontal scale).
- Idempotent submit: dedup by `(batch_file_id, content_hash)` so a double-click / retry
  never double-enqueues (extend existing `activeBatches`/content-hash logic).
- Extend `StuckBatchReconciler` to cover Celery jobs: TTL + requeue on worker death;
  honor `QC_RECONCILER_*` settings already in `application.yml`.
- Backpressure: rely on the durable Redis queue (bursts wait, not 503); set a sane max
  queue depth + alert.
- Wrap the QC persist in optimistic-lock **retry** (the `@Version` is already there).
- **Gate:** chaos test — kill a Celery worker and the Java app mid-burst; **every job
  reaches a terminal state**, no duplicate `qc_result` rows, reviewer queue consistent.
- **Done(L3):** runbook entry for "stuck job" recovery.

### Phase 5 — Storage durability + Postgres operational tuning  *(T-2)*
**Goal:** 5,000 docs safely stored and fast.
- `./uploads` on a dedicated, sized volume (≥150 GB headroom: 5,000 × up to 25 MB).
- Scheduled backup (e.g. `restic`/`rsync` to a second volume/offsite) + **retention policy**
  that *archives, never silently deletes* (P-15 "data is the asset").
- Disk-usage + inode monitoring + alert at 80%.
- `pg_dump`/PITR backup for the DB; `VACUUM/ANALYZE` autotuning; consider monthly
  partitioning or retention for the high-growth `business_event` / `audit_log` tables
  (≈138 rows/doc → ~700k rows at 5,000 docs; plan partition before ~10M).
- **Gate:** restore drill — recover docs + DB from backup into a scratch env successfully.
- **Done(L3):** backup/restore runbook.

### Phase 6 — Observability + the load test that proves the targets  *(verifies T-1…T-6)*
**Goal:** Make the numbers visible and prove the contract in §1.
- Dashboards: Celery queue depth + worker count (Flower), Hikari pool usage, Postgres
  slow queries, per-stage QC timings (the **DocStats** feature already captures these —
  surface them), Groq call/throttle counts.
- Alerts: queue depth, pool exhaustion, disk, error rate.
- **Load test suite (committed under `scripts/loadtest/`):**
  - `read_50vu.js` (k6): 50 VUs across reviewer queue, report load, decision save → T-1/T-4.
  - `process_soak.py`: enqueue 250+ docs over 8 h, assert all terminal, measure docs/h → T-3.
  - Seed script to 5,000 docs for T-2.
- **Gate:** all of T-1…T-6 measurements pass and are recorded in **Measured Baselines**.
- **Done(L2):** the targets table in §1 flips from "design intent" to "met (date, number)".

---

## 6. Concrete change map (file → what changes)

| File / area | Phase | Change |
|---|---|---|
| `scripts/add_missing_indexes.sql` | 0 | apply to target DB |
| `app/.../application.yml` (+ `application-prod.yml`) | 0,2,3 | metrics exposure; Hikari 30/10; prod profile |
| `ocr-service/requirements.txt` | 1 | add `celery`, `redis` |
| `ocr-service/celery_app.py`, `tasks.py` (new) | 1 | Celery app + `qc_process_task` reusing `run_transaction_qc_paths` |
| `ocr-service/main.py` | 1 | `POST /qc/submit`, `GET /qc/jobs/{id}`, `/health` → `celery_worker_running` |
| `app/.../config/RestTemplateConfig.java` | 1 ✅ | pooled **JDK** `HttpClient` (no new dep); short-timeout client for health/poll/submit, long only for sync (QL-8) |
| `ocr-service/app/database.py` | 2 ✅ | `pool_size=2, max_overflow=3` (env-overridable) |
| `application.yml` `qc.executor.*` | 2 ✅ | enqueue+poll sizing core=4/max=8/queue=200 (AsyncConfig already reads these props — no Java change) |
| `app/extraction/llm_groq.py` | 2 ✅ | Redis distributed token bucket for the TPM budget (QL-2); `llm_resilience.py` `Semaphore(1)` left as-is (Ollama-only, suppressed) |
| `app/.../config/CacheConfig.java` (new) + `app/pom.xml` | 3 ✅ | `@EnableCaching` + Caffeine 30s manager; cache + caffeine deps (QL-3) |
| `app/.../service/AnalyticsService.java` | 3 ✅ | `@Cacheable` 7 dashboards; batch-fetch users (QL-4); COUNT-based SLA (QL-5/6) |
| `common/.../repository/QCRuleResultRepository.java` | 3 ✅ | `countOverdueReviewItems` + `Pageable` top-N overdue (QL-5) |
| `qc/.../service/VerificationService.java` | 3 ✅ | per-item `.save()` → `saveAll` (QL-12) |
| `application.yml` Hikari | 3 ✅ | `maximum-pool-size` 30, `minimum-idle` 10 (§4.1) |
| `qc/.../ReviewerApiController.java`, repos | 3 ⏸ deferred | paginate `submitted` + `/rules`; DTO projections (QL-7 — frontend-coordinated) |
| `ocr-service/main.py` (`/qc/transactions`) | 3 ⏸ deferred | single grouped query for the picker (QL-9) |
| `batch/.../controller/FileController.java` | 3 ⏸ deferred | stream + HTTP cache headers for `/files/{id}` (QL-13) |
| `app/.../service/QCProgressStore.java` + `QCProcessingService` | 4 | Redis-backed progress; idempotent submit; lock retry |
| `qc/.../StuckBatchReconciler.java` | 4 | cover Celery job TTL/requeue |
| `scripts/backup_*.sh`, systemd timers (new) | 5 | doc + DB backup, retention, disk alerts |
| `postgresql.conf` | 5 | shared_buffers/effective_cache_size/work_mem/max_connections |
| `scripts/loadtest/*` (new) | 6 | k6 read test, processing soak, 5k seed |
| Actuator + Flower + Grafana wiring | 6 | dashboards/alerts |

---

## 7. Edge-case matrix ("smart query, every edge case" — T-6)

| Edge case | Required behavior | Mechanism / phase |
|---|---|---|
| Duplicate upload / re-run | Dedup by content hash; supersede prior active result, carry reviewer decisions | existing cache + `persistPythonResult` rerun logic; idempotent submit (4) |
| Worker dies mid-doc | Job requeued, reaches terminal state, no half-written `qc_result` | Celery acks-late + reconciler (1,4) |
| Java restarts mid-batch | Jobs durable in Redis; batch resumes; progress restored | durable queue (1) + Redis progress (4) |
| Groq 429 / TPM exceeded | Backoff, throttle wait logged, keyword fallback, never fatal | distributed token bucket + P-6 fallback (2) |
| 50 users hit reviewer queue at once | Paginated, projected, cached; pool not exhausted | pagination + Caffeine + Hikari 30 (3) |
| 5,000-doc table scans | Index-backed; no seq scan on hot path | indexes + EXPLAIN audit (0,3) |
| Burst of 250 docs in an hour | Queue absorbs; workers drain at steady rate; no 503 | durable queue + backpressure (1,4) |
| Two admins click "Run QC" on same batch | Single claim wins; duplicate rejected cleanly | `activeBatches`/`claimBatch` + idempotent submit (4) |
| Disk fills during ingest | Storage pre-check fails fast with clear error; alert fires | existing `assertFileReadable` + disk alert (5) |
| Stale/idle DB transaction during long OCR | OCR call held *outside* any DB txn (already designed) | keep `processFilePair` contract (no regression) |
| Optimistic lock clash on persist | Retry once, then surface | `@Version` + retry wrapper (4) |
| Corrupt/zero-page PDF | Page skipped/flagged, doc still produces partial result | P-6 graceful degradation (no regression) |

---

## 8. Risk register

| ID | Risk | Mitigation |
|---|---|---|
| **R-1** | **Groq 6k TPM is the real throughput ceiling**, not CPU. With 6–8 workers, LLM stages serialize at the cap. | Distributed token bucket shares budget honestly (2); **recommend a higher Groq tier** for full parallel 250/day; lean on OCR cache for reruns. Re-measure after Phase 2 and decide. |
| R-2 | Per-worker SQLAlchemy pools over-subscribe Postgres | Shrink to 2/3 per worker; connection arithmetic in §4.1; PgBouncer if workers grow. |
| R-3 | Single host = single point of failure | Backups + restore drill (5); architecture is horizontal-ready (Redis progress, durable queue) if a second box is added later. |
| R-4 | `business_event`/`audit_log` row growth (~138/doc) | Index now (0); partition/retention before ~10M rows (5). |
| R-5 | Adding Redis/Celery = new ops surface | systemd units, health checks, Flower, runbooks (1,6). |
| R-6 | Changing pool/worker sizes destabilizes under real load | All values are P-4 config; tune from measured load test, not intuition (P-13). |

---

## 9. Measured Baselines  *(filled by `/scale-plan` as phases land — do not guess, P-8)*

| Metric | Baseline (Phase 0) | After Phase 2 | After Phase 3 | Target |
|---|---|---|---|---|
| Per-doc processing time (p50/p95) | _TBD_ | | | < 4 min p95 |
| Sustained docs/hour (N workers) | _TBD_ | | | ≥ 31/h burst |
| Docs/day proven | _TBD_ | | | ≥ 250 |
| Reviewer queue p95 @ load | _TBD_ | | | < 400 ms |
| Report load p95 @ load | _TBD_ | | | < 400 ms |
| Decision save p95 @ load | _TBD_ | | | < 400 ms |
| Max safe concurrent docs | 2 (code: `AsyncConfig` core=max=2) | | | host-limited |
| Concurrent users sustained | _TBD_ | | | ≥ 50 |
| OCR cache hit rate | _TBD_ | | | track |
| Groq throttle-wait per doc | _TBD_ | | | track |

**Phase 0 execution log (2026-06-15, local `ardurApprisal`):**
- **Indexes applied** — ran `scripts/add_missing_indexes.sql`: 6 created
  (`idx_qc_rule_qcresult_status`, `idx_qc_rule_result_needs_review`, `idx_audit_log_user_created`,
  `idx_audit_log_entity_created`, `idx_qc_result_final_decision`, `idx_batch_client_status`) +
  duplicate `idx_qc_rule_qcresult_id` dropped. The two `feedback_events` indexes were **skipped**
  (Python-owned table, absent in this DB — created via `ocr-service/manage_db.py`); apply them
  when running the script against a DB that has the Python schema.
- **Slow-query logging ON** — `log_min_duration_statement=500`, `log_lock_waits=on` (via
  `ALTER SYSTEM` + reload; reversible with `ALTER SYSTEM RESET`). NOTE: `logging_collector=off`
  → slow queries go to Postgres stderr; a dedicated rotating logfile needs a restart (optional).
- **Actuator metrics exposed** — `application.yml` now exposes `health,info,metrics,prometheus`
  (deps already present). `/actuator/health` is public; `metrics`/`prometheus` are auth-gated by
  `SecurityConfig` `.anyRequest().authenticated()` (no leak). Hikari/JVM/HTTP timers auto-bound.
- **Baseline caveat (P-8):** current DB is a near-empty **dev** DB
  (`qc_result`=2, `qc_rule_result`=409, `business_event`=464, `batch`=2). Load/processing/p95
  numbers above require the **running stack + a seeded ~5,000-doc DB** (Phase 6 seed) and are
  intentionally left `_TBD_` rather than filled with non-representative dev numbers.

**Phase 1 execution log (2026-06-15) — durable queue built & queue-mechanism verified:**
- **Python:** added `celery`/`redis` to `requirements.txt`; new `celery_app.py` (Redis
  broker+backend, `task_track_started`, `acks_late`, prefetch=1, soft/hard time limits) and
  `app/tasks.py::qc_process_task` (reuses `run_transaction_qc_paths` + `report_to_python_qc_response`).
- **FastAPI:** added `POST /qc/submit` + `GET /qc/job/{id}` (Celery `AsyncResult` → status/result),
  and `/health` now returns `celery_worker_running` (drives Java's async/sync switch).
- **Java (QL-8):** `RestTemplateConfig` split into a pooled JDK-HttpClient short-timeout client
  (health/submit/poll, 30s) + a dedicated long client for the sync `/qc/process` only;
  `PythonClientService` wired to use the long client solely for that call. **`mvn compile` green.**
- **Verified:** celery 5.6.3 / redis 7.4.0 present in the `apprisal` env, Redis server up; task
  registers; FastAPI app loads with the new routes; **end-to-end round-trip** through Redis
  observed `PENDING→STARTED→SUCCESS` with the result dict returned (so `task_track_started` and
  the result backend both work); pipeline degraded gracefully on a missing file (P-6).
- **Worker run command:** `cd ocr-service && celery -A celery_app.celery_app worker --concurrency=6 --prefetch-multiplier=1 --loglevel=info`
- **Open gate (needs full stack + GROQ key + real PDF):** the true *no-job-lost-on-restart*
  integration test via the Java→Python HTTP path (start Java + uvicorn + a worker, run a batch,
  kill+restart mid-flight). Mechanism proven; this is the operational confirmation.

**Phase 2 execution log (2026-06-15) — throughput sizing + distributed Groq limiter built & verified:**
- **QL-2 distributed Groq TPM limiter:** `llm_groq.py` now shares the `GROQ_TPM_LIMIT` budget
  across all worker processes via a **Redis token bucket** (atomic Lua refill/deduct), falling
  back to the per-process rolling-window throttle when Redis is down (P-6). The old in-process
  throttle is retained as `_throttle_tpm_local`.
- **Sizing (P-4, all configurable):** Java `qc.executor` → core 4 / max 8 / queue 200
  (`application.yml`); per-worker SQLAlchemy pool → `pool_size=2, max_overflow=3` (`database.py`,
  env-overridable) to respect the §4.1 connection arithmetic; Celery `--concurrency=6` (run cmd);
  `REDIS_URL` + pool knobs documented in `ocr-service/.env.example`.
- **Verified:** Python syntax + `application.yml` YAML valid; against live Redis — allow path
  deducted 900/1000 → 100 tokens left, 0 ms slept; wait path on a near-empty bucket returned
  allow=0 / wait≈5.7 s; **a second independent caller hit the same shared bucket (allow=0)** →
  cross-process enforcement proven.
- **Open gate (needs full stack + GROQ key + ~250 docs):** the docs/day **soak test** to record
  real sustained throughput (§9), and a cache-hit-rate metric. Re-assess Risk R-1 (Groq tier)
  from the measured numbers then.

**Phase 3 execution log (2026-06-16) — read/query performance, built & compile-verified:**
- **QL-3/QL-6 caching:** added `spring-boot-starter-cache` + Caffeine (`CacheConfig`,
  `@EnableCaching`, 30s write-TTL, max 1000); annotated the seven AnalyticsService dashboards
  (`@Cacheable("analytics")`) so 50 users polling collapse to one query-set per 30s window.
- **QL-4 N+1:** AnalyticsService `getOperatorInsights`/`getWeeklyAnomalyReport` now batch-fetch
  users via `userRepo.findAllById` (new `usersByIds` helper) instead of `findById` per row.
- **QL-5 SLA dashboard:** new `countOverdueReviewItems` + a `Pageable` top-N `findOverdueReviewItems`;
  `getReviewSlaDashboard` uses COUNTs for the 4h/8h totals and fetches only the 50 shown rows.
- **QL-12:** VerificationService `markItemsPresented`/`acceptAll` per-item `.save()` → `saveAll`.
- **Hikari (§4.1):** `maximum-pool-size` 10→30, `minimum-idle` 2→10 (env-overridable).
- **Verified:** `mvn compile` green (cache deps resolved, new repo methods + AnalyticsService
  rewrite compile); `application.yml` valid YAML.
- **Deferred (honest scope):** QL-7 (paginate the `submitted` queue + `/rules`) and QL-9
  (`/qc/transactions` N+1) change API response shapes / need frontend coordination + the
  dedup rewrite — left for a frontend-coordinated pass; QL-13 (file streaming cache headers) minor.
- **Open gate:** the **k6 50-VU read test** (p95 < 400 ms, 0 5xx) — needs the running stack +
  the seeded 5,000-doc DB to prove the latency target; cache hit-rate visible via Actuator then.

---

## 10. Progress Tracker  *(maintained by `/scale-plan`)*

| Phase | Status | Owner | Started | Gate passed | Notes |
|---|---|---|---|---|---|
| 0 — Baseline & indexes | ◐ In progress | | 2026-06-15 | (partial) | Indexes applied, slow-query log on, Actuator metrics exposed (local). **Open:** load/processing baseline needs running stack + seeded DB; `feedback_events` indexes pending Python-schema DB |
| 1 — Durable queue (Redis+Celery) | ◐ In progress | | 2026-06-15 | (mechanism verified) | Celery app+task+endpoints built, RestTemplate split, Java compiles, end-to-end Redis round-trip PENDING→STARTED→SUCCESS proven. **Open:** no-job-lost integration test via full stack |
| 2 — Throughput sizing + Groq limiter | ◐ In progress | | 2026-06-15 | (limiter verified) | Redis distributed TPM bucket built+verified (cross-process); Java executor 4/8/200, SQLAlchemy 2/3, Celery concurrency=6, REDIS_URL documented. **Open:** docs/day soak + cache-hit metric |
| 3 — Read/query performance | ◐ In progress | | 2026-06-16 | (built, compiles) | Caffeine cache on 7 dashboards (QL-3/6), AnalyticsService N+1 fixed (QL-4), SLA count-based (QL-5), saveAll (QL-12), Hikari 30/10. **Deferred:** QL-7/QL-9 (frontend-coordinated). **Open:** k6 50-VU latency gate |
| 4 — Concurrency correctness | ☐ Not started | | | | |
| 5 — Storage durability + PG tuning | ☐ Not started | | | | |
| 6 — Observability + load test | ☐ Not started | | | | |

Legend: ☐ Not started · ◐ In progress · ☑ Gate passed

---

*Created: 2026-06-15 · Updated: 2026-06-16 — Phase 0 applied (indexes + slow-query log + Actuator); Phase 1 built & queue-verified (Redis+Celery durable queue, /qc/submit + /qc/job, RestTemplate split); Phase 2 built & verified (Redis distributed Groq TPM bucket, executor/pool sizing); Phase 3 built & compile-verified (Caffeine dashboard cache, N+1 + SLA fixes, Hikari 30/10). Open gates (need running stack): no-job-lost test, docs/day soak, k6 50-VU latency. · Stack: Spring Boot (Java 21) + FastAPI (Python) + Next.js + PostgreSQL + Redis/Celery · Host: single 8–16c/32–64GB*
*Maintained by `/scale-plan` (`.claude/skills/scale-plan.md`). Keep §9 and §10 current with every increment.*
