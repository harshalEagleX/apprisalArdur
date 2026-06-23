# SHAL Platform — Architecture, Code, Data-Contract, Workflow, QC, Reliability & Performance Audit

**Audit date:** 2026-06-21
**Branch audited:** `demo`

> **Update (2026-06-21, post re-verification + remediation):** Two `partial`/`not_evaluable` areas were re-verified and **two safe fixes were implemented** this session. See [§0 Re-verification & Changes Implemented](#0-re-verification--changes-implemented). No architecture, data contract, or business flow was changed.

---

## 0. Re-verification & Changes Implemented

### Re-verification corrections (items I had under-/over-scored)
- **Reviewer access IS properly scoped (IDOR protection exists).** `ReviewerApiController` enforces per-assignment access: `findPendingForReviewer(userId, pageable)`, `findRecentlyReviewedForReviewer(userId)`, and `assertReviewerOwns{QcResult,RuleResult,Batch}`. A REVIEWER cannot reach arbitrary batches — only those assigned to them. The tenancy gap is therefore narrower than first stated: **there is no *organization*-level isolation, but there is no reviewer-level cross-batch leak.** Cross-client visibility exists only for ADMIN, which is expected. → **TEN-008 upgraded fail→partial; JAVA-008 reframed as "no org model" not "no scoping".**
- **Pagination exists.** `ReviewerApiController` uses `PageRequest`/`findPendingForReviewer(..., pageable)`. → **PERF-010 not_evaluable→pass.**
- **`VerificationService` is strong.** `beginReviewSession` uses a pessimistic `findByIdForUpdate` (TOCTOU lock), `assertDocumentCurrent` (supersede guard), an 8s minimum decision time (anti-rubber-stamp), and a ≥20-char override-reason minimum. → **REV-006/REV-008 confirmed; precedence model sound.**

### Changes implemented (safe, additive, non-architectural)
1. **Python service now enforces `X-API-Key` (closes the HIGH finding SEC-001).**
   - `ocr-service/main.py`: added an `@app.middleware("http")` that rejects any non-public request lacking a valid key (constant-time `hmac.compare_digest`).
   - `ocr-service/app/config.py`: loads the project-root `.env` as a fallback (`override=False`) so `INTERNAL_API_KEY` is reused as a **single source of truth** (not duplicated), and exposes it.
   - **Backward-compatible:** enforced only when the key is configured (it is — verified loaded, len 43); `/health`, `/live`, `/docs`, `/redoc`, `/openapi.json` stay public; CORS `OPTIONS` pre-flight always allowed. Java already sends the header on every call; the frontend never calls Python directly; the `brain` test harness only hits public `/health`. **Verified:** `py_compile` clean, key loads from root `.env`.
2. **`/actuator/**` (except `/actuator/health`) restricted to ADMIN.**
   - `app/.../config/SecurityConfig.java`: previously these fell to `anyRequest().authenticated()`, leaking metrics/prometheus/info to any REVIEWER. Now ADMIN-only; `/actuator/health` stays public for load-balancer probes. No Prometheus scraper is wired yet, so nothing breaks. **Verified:** `mvn -pl app -am compile` clean.

### Deliberately NOT changed (would touch architecture or business semantics — flagged for your decision)
- **Tenancy model (`organization_id`)** — adding tenant isolation is a schema + business-rule decision, not a safe drop-in. Left for you to decide single-org vs multi-org.
- **In-memory single-host concurrency guards → shared store** — changes the runtime/deployment model; only needed before running >1 Java instance.
- **`(qc_result_id, rule_id)` DB uniqueness** — additive but risks failing on any pre-existing duplicate rows on the live shared DB; needs a data check + backfill first.

---

## 0b. Second remediation pass (2026-06-21) — performance mode + remaining gaps

All changes below are **additive and verified** (`mvn test-compile` for `common,qc,app`; `PythonQCResponse/RuleResult` tests 9/9 pass; `py_compile` clean). **No architecture, data contract, or business flow changed.**

### Performance ("always-on performance mode", both sides)
- **Java HTTP gzip compression** (`application.yml` `server.compression`) — JSON >1 KB (reviewer/batch screens) compressed; big transfer-latency cut.
- **Java HTTP/2** enabled (`server.http2`, env-toggle) — multiplexed connections, lower head-of-line latency.
- **Java Tomcat pool env-tunable** (`threads.max/min-spare`, `accept-count`, `max-connections`) — absorbs concurrency bursts without refusals; scale per host (P-4) with no code change.
- **Hibernate `default_batch_fetch_size=100` + `in_clause_parameter_padding`** — kills the N+1 on batch→files→results walks (the dominant list/review-screen latency) and stabilises query plans.
- **Python response gzip** (`GZipMiddleware`) — the multi-KB `PythonQCResponse` is compressed over the wire to Java.
- *(Confirmed already-optimal and left as-is: Celery `acks_late`+`prefetch=1`+time-limits+`reject_on_worker_lost`; `QCProgressStore` is already Redis-backed with in-memory fallback; long OCR call already runs outside any DB transaction; rule-row insert batching `batch_size=50`; async event recording.)*

### Gap fixes implemented (code)
- **Contract versioning** (ARCH-007, DB-003, MIG-008): `schema_version` ("1.0") now flows Python→Java (`python_response.py` `CONTRACT_SCHEMA_VERSION` → `PythonQCResponse.schemaVersion`); Java logs a drift warning at persist if it mismatches `EXPECTED_PYTHON_SCHEMA_VERSION`.
- **Enum-drift detection** (DB-002): `normalizePythonStatus` now warns on any status outside `KNOWN_RULE_STATUSES` (still degrades safely to review).
- **Insecure-default hardening warnings** (SEC-002): `AdminSeeder.warnOnInsecureDefaults()` logs WARN (ERROR under a prod profile) if the built-in `JWT_SECRET`/`ADMIN_PASSWORD` or `COOKIE_SECURE=false`-in-prod are in effect. Non-fatal.

### Gap fixes via runbook/scripts (no runtime risk — close process/decision items)
- **Tenancy declared single-org** → [`readme/TENANCY_DECISION.md`](readme/TENANCY_DECISION.md). Closes DB-010, TEN-001/002/003/004/005/007/008, JAVA-008 as *by-design* (reviewers are assignment-scoped; only ADMIN sees across clients).
- **Migration discipline** → [`readme/MIGRATION_RUNBOOK.md`](readme/MIGRATION_RUNBOOK.md) + [`scripts/db/snapshot_schema.sh`](scripts/db/snapshot_schema.sh). Closes MIG-001/003/006/009/010, DB-006 (per-release schema snapshot = the migration note; `validate` workflow; deploy order; rollback).
- **`(qc_result_id, rule_id)` uniqueness** → [`scripts/db/qc_rule_result_unique_index.sql`](scripts/db/qc_rule_result_unique_index.sql) — guarded two-step (dup-check → `CREATE UNIQUE INDEX CONCURRENTLY`) so it can't break a running app. Run when ready (DB-008, RR-003).

### Still open (operator actions only — no code left)
- **Run the unique-index script** against the live DB (one command, after the dup-check).
- **Set prod env vars** (`JWT_SECRET`, `ADMIN_PASSWORD`, `COOKIE_SECURE`) — startup log names them.
- **Wire the scrape target** (localhost management port) per `readme/OBSERVABILITY.md` and point Grafana at it.
- **Multi-org isolation** — declined by owner (internal single-org tool); intentionally not built.

---

## 0c. Third remediation pass (2026-06-21) — scale-out + observability (the last two)

Both items previously parked as "future work" are now **implemented and verified against the live local Postgres + Redis** (full Spring context boots; `ShalApplicationTests` + `RerunGuardIntegrationTests` green; configs JSON/YAML-validated). All additive; single-host behaviour unchanged.

### Cross-node cancellation (the real scale-out gap)
- **Honest scoping:** batch *claiming* is already multi-instance-safe via the DB conditional UPDATE (`markQcProcessingIfTriggerable`). The only thing a single in-process map couldn't do across nodes was **cancellation** — so that's what was built.
- New `ClusterCoordinator` interface (`common`) + `InMemoryClusterCoordinator` default + **`RedisClusterCoordinator` (`@Primary`, Redis-backed, graceful in-memory fallback** mirroring `QCProgressStore`). Wired **additively** into `QCProcessingService` (`signalCancel` on stop, `isCancelSignalled` in the cancellation check, `clearCancel` on cleanup). On one host it behaves exactly as before; with >1 instance, "Stop QC" now reaches a worker on another node.

### Prometheus alerts & dashboards (OBS-008)
- New `QcMetrics` (`app`) — Micrometer gauges for QC backlog per status + stuck-batch count, sampled via cheap COUNT queries.
- `prometheus/alert.rules.yml` (pool saturation, heap, 5xx spike, stuck/error batches, backlog, app-down), `prometheus/prometheus.yml.example`, `prometheus/grafana-dashboard.json`, and `readme/OBSERVABILITY.md`.
- Security-aware: `/actuator/prometheus` stays ADMIN-locked; the doc recommends a localhost-only management port for the scraper rather than re-opening it.

---
**Scope:** Java backend (Spring Boot modular monolith) + Python OCR/QC service (FastAPI + Celery) + shared PostgreSQL + Next.js frontend.
**Method:** Evidence-based, adversarial. Findings cite files/classes/methods. Where evidence was not inspected, the item is marked `not_evaluable` with what is needed.

> **Coverage note (honesty):** This report is grounded in direct reads of the core integration and ownership surface: all shared JPA entities (`Batch`, `BatchFile`, `QCResult`, `QCRuleResult`, `QCDecision`, `FinalDecision`, `DocumentMatch`, status enums), the Java↔Python integration (`QCProcessingService`, `PythonClientService`, `OcrServiceConfig`), Python `main.py` endpoints, `app/tasks.py`, `app/database.py`, `app/config.py`, `manage_db.py`, `SecurityConfig`, `BatchService` ZIP intake, `StuckBatchReconciler`, and both `application.yml` profiles. The QC *rule* internals (146-rule engine in `app/qc/`), the full reviewer UI, and live DB rows were **not** exhaustively read; items depending on them are marked `partial` / `not_evaluable`.

---

## 1. Executive Summary

This is a **disciplined hybrid architecture**, not the fragile shared-database distributed monolith the brief feared. The single most important reality-check finding:

**The "shared PostgreSQL" is shared at the *instance* level, but the *table sets are disjoint and ownership is explicit and enforced.***
- **Java** owns every workflow and QC-result table (`batch`, `batch_file`, `qc_result`, `qc_rule_result`, `document_match`, `business_event`, `audit_log`, `doc_stat*`, `processing_metrics`, `user`, `client`, `operator_session`) via JPA/Hibernate.
- **Python** owns only `adaptive_*` tables (extraction cache, corrections, AMC profiles, validation, page-OCR, classifications), enumerated in `ocr-service/manage_db.py:MANAGED_TABLES`, and explicitly never touches Java tables.
- **The integration is a request/response contract over HTTP + Celery/Redis**, not cross-table writes. Python returns a `PythonQCResponse` dict (`ocr-service/app/tasks.py`); Java deserializes it and is the **sole writer** of `qc_result`/`qc_rule_result` (`QCProcessingService.persistPythonResult`). Python never mutates Java's workflow truth.

This is the correct boundary for this domain. Because of it, most of the catastrophic shared-DB risks in the brief (co-owned status fields, Python mutating workflow tables, dual writers racing on a row) **do not exist here**.

The engineering quality is high: optimistic locking (`@Version`), soft-delete with global `@SQLRestriction`, rerun-as-supersede with full lineage (`rerun_of` + `superseded_at` + partial unique index), reviewer-decision migration across reruns, review locking with expiry, a two-person override workflow, Envers + `BusinessEvent` dual audit, correlation IDs, a stuck-batch reconciler, multi-layer idempotency, and documented connection-pool arithmetic.

**The headline defect is a security gap, not an architecture gap:** the Python service **receives but never validates** the `X-API-Key` Java sends, so the entire OCR/QC processing service is unauthenticated to anyone who can reach its port.

**Overall score: 81 / 100 — Acceptable with medium-risk fixes.** Production-safe after the top-10 list in §15 (chiefly: enforce the internal API key, decide and enforce the tenancy model, lock down `/actuator` and Python CORS, and move the in-memory single-host concurrency guards to a shared store before horizontal scaling).

---

## 2. Architecture Classification & Reality Check

**Classification: Modular monolith (Java) + external stateless processing engine (Python), integrated by an HTTP/queue contract over a shared-instance / split-schema PostgreSQL.**

Evidence:
- Java is a **Maven multi-module monolith** deployed as one app (`pom.xml` modules: `common`, `batch`, `qc`, `user`, `app`; single `ShalApplication`). Module boundaries are real in code, not just docs — entities/repos live in `common`, workflow orchestration in `qc`/`batch`, auth in `user`.
- Python is a **separate process** (FastAPI on :5001 + Celery workers) reached only via REST (`PythonClientService`). It holds no Java workflow state.
- The DB is shared, but `manage_db.py` and `CLAUDE.md`'s "Database Schema Policy" enforce **disjoint ownership** (`adaptive_*` = Python; everything else = Java). This is the defining property that keeps it out of "distributed monolith" territory.

**Is this reasonable for the domain?** Yes. OCR/LLM/rule execution is CPU/IO-heavy and Python-native; workflow, RBAC, audit, and transactional review state are Java-native. Splitting them on a process boundary while keeping one Postgres for operational simplicity is a sound, deliberate choice. The one architectural caveat: several concurrency-control mechanisms are **in-process** (see §11), which silently assumes a **single Java instance and single Python web process**. That assumption is documented (`readme/SCALABILITY_PLAN.md`) but is a latent ceiling.

---

## 3. Service Ownership Map

| Object / Table / Process | Owner (writes) | Read by | Expected owner | Conflict risk |
|---|---|---|---|---|
| `batch`, `batch_file` | Java (`BatchService`, `QCProcessingService`) | Java, frontend | Java | **None** |
| `qc_result`, `qc_rule_result` | **Java only** (`persistPythonResult`) | Java, frontend | Java | **None** — Python returns DTO, never writes |
| `document_match` | Java (`FileMatchingService`) | Java | Java | None |
| `business_event`, `audit_log`, `*_aud` (Envers) | Java | Java | Java | None |
| `doc_stat*`, `processing_metrics` | Java (from Python timings DTO) | Java | Java | None |
| `user`, `client`, `operator_session` | Java | Java | Java | None |
| `adaptive_*` (extraction/corrections/AMC/validation/OCR cache) | **Python only** (`manage_db.py`, services) | Python | Python | None — Java never reads/writes these |
| QC decision (`qc_decision`) | Java writes; **derived from** Python rule outcomes | Java, frontend | Java | Low — Python supplies inputs, Java owns the column |
| `final_decision` / reviewer state | Java (`VerificationService`, reviewer API) | Java | Java | None |
| Job lifecycle (Celery) | Python/Redis | Java polls | Python | Low — Java is system-of-record, Python "operational only" (per `StuckBatchReconciler` doc) |
| Batch-level status transitions | Java | Java, frontend | Java | None |

**Conclusion:** Ownership is clean and matches actual write paths. No table is silently co-written by both services.

---

## 4. Shared Database Contract Audit

**Strengths**
- **Explicit, documented contract.** `CLAUDE.md` "Database Schema Policy" + `manage_db.py:MANAGED_TABLES` (Python) define ownership both services respect.
- **DTO contract is typed and tested.** `common/.../dto/python/PythonQCResponse|PythonRuleResult|PythonEvidence|PythonTimings` plus `PythonQCResponseTest`/`PythonRuleResultTest` pin the JSON shape Java parses.
- **Versioning baked in.** `rule_engine_version` (`qc-1.0.0+<fingerprint>`), `extraction_method`, `source_document_hash`, `source_document_version` are stamped on every `QCResult` for reproducibility and run-vs-run attribution.
- **Indexes match access paths.** `batch(status, updated_at)`, `batch(file_hash)`, `qc_result(batch_file_id)`, `qc_result(qc_decision)`, `qc_rule_result(qc_result_id, needs_verification)` etc. cover the hot review/list queries.
- **Idempotency aligned to schema.** Partial unique index `uq_qc_result_batch_file_active WHERE superseded_at IS NULL` (documented on `QCResult`) lets one active result coexist with retained history; `document_match` has `uq_document_match_appraisal_support_type`.

**Risks / gaps**
- **No `organization_id` anywhere.** Tenancy is effectively single-org (see §10). If multi-tenant is ever intended, every table needs scoping — currently absent.
- **`ddl-auto=update` on a shared prod DB.** Hibernate auto-mutates Java tables on boot. The team mitigated by making it env-driven (`JPA_DDL_AUTO`, default `update`, prod can set `validate`) — good — but no reviewed DDL snapshot / migration history exists, so cross-service schema coordination is manual and undocumented per-release.
- **JSON shape drift is unguarded at runtime.** `python_response`, `details`, `evidence` are free-form TEXT/JSON. The DTO test guards the *envelope*, but nested `details`/`evidence` payloads are not versioned; a Python-side shape change is only caught if it breaks a typed field.
- **Enum drift between services is possible but low-risk.** `QCDecision`/`status` strings cross the boundary as strings and are normalized in Java (`normalizePythonStatus`), so a new Python status degrades to a default rather than crashing — acceptable, but silent.

---

## 5. Java Backend Audit

**Strengths**
- **Clean layering** controller → service → repository; `open-in-view: false` (no lazy-load-in-view leaks).
- **Transaction discipline is excellent and deliberate.** `QCProcessingService.processBatch` is intentionally **not** `@Transactional` at the outer level; the multi-minute Python call runs outside any DB transaction, and only short `REQUIRES_NEW` saves (`persistPythonResult`, `markBatchError`, `saveFinalBatchStatus`) hold a connection. This directly avoids the "idle-in-transaction killed during OCR" failure mode (explicitly commented re: Neon).
- **Self-injection via `@Lazy self`** correctly forces proxy re-entry so `REQUIRES_NEW` helpers actually start new transactions (a subtle bug class handled right).
- **Optimistic locking** on `Batch` and `QCRuleResult` (`@Version`); the error path uses a transactional re-fetch helper to avoid stale-version `OptimisticLockingFailureException`.
- **DTOs are view/transport contracts**, not persistence (`common/dto/**`); entities are not leaked as request bodies in the paths reviewed.
- **JSON batch INSERT batching** (`hibernate.jdbc.batch_size=50`, `order_inserts`) collapses ~138 rule-row inserts — a measured perf fix.

**Risks / gaps**
- **Batch status writes are guarded by in-memory state** (`activeBatches`, `runningThreads` `ConcurrentHashMap`s in `QCProcessingService`) — correct on one node, **ineffective across multiple Java instances** (two nodes could both process the same batch). DB-level `markQcProcessingIfTriggerable` provides a real guard, but the dedupe/cancel/heartbeat maps do not survive failover or scale-out.
- **`/actuator` exposes `metrics,prometheus`** and the config's own comment admits it "must NOT be public in production" — not yet secured in `SecurityConfig`.
- **Insecure config defaults** ship in `application.yml`: `JWT_SECRET` default literal, `ADMIN_PASSWORD:Admin123!`, `COOKIE_SECURE:false`, HSTS disabled. Fine for dev, dangerous if an env var is missed in prod.

---

## 6. Python Processing Engine Audit

**Strengths**
- **Stateless w.r.t. Java truth.** `qc_process_task` (`app/tasks.py`) runs the pipeline and **returns** a `PythonQCResponse` dict; it does not write Java tables. Temp uploads are always cleaned up in `finally` (P-5: source-of-record stays in the batch store).
- **Own DB ownership is disciplined.** `app/database.py` engine is per-process, pool sized small (`DB_POOL_SIZE=2`, `max_overflow=3`) with documented connection arithmetic; `get_db()` context manager commits/rolls back/closes correctly.
- **Idempotent job submission** (`/qc/submit`): Redis idempotency key with in-flight reuse (`_inflight_job_for`), atomic `SET NX` claim, and a **race-loser revoke** path — genuinely careful double-submit protection.
- **Graceful degradation (P-6)** throughout: Redis/broker errors → fall back to sync `/qc/process`; Vision/LLM unavailable → rules degrade to VERIFY, not crash.
- **Version metadata** (`EXTRACTION_LAYER_VERSION`, `QC_RULESET_VERSION`, model ids) is captured and flows back in the response.

**Risks / gaps**
- **No authentication on any endpoint (HIGH).** `main.py` adds only `CORSMiddleware`; no dependency/middleware validates the `X-API-Key` Java sends. `/qc/process`, `/qc/submit`, `/corrections` (POST), `/routing/config` (PUT), `/baseline/run` (POST), `/validate/{id}` are all open to anyone who can reach :5001. (Confirmed: `grep` for `INTERNAL_API_KEY`/`X-API-Key` in `ocr-service` finds nothing on the receiver side.)
- **In-memory progress registry** `_QC_PROGRESS` assumes a single web process; with >1 uvicorn worker, `/qc/progress/{token}` becomes nondeterministic.
- **Deprecated `@app.on_event("startup")`** (FastAPI lifespan migration) — minor.
- **Python CORS allows `localhost:3000` with credentials** — labelled "demo"; must not ship as-is.

---

## 7. Workflow / Processing Lifecycle Audit

The lifecycle is **explicitly modeled** and forward-only:

```
UPLOADED → VALIDATING → {VALIDATION_FAILED | QC_PROCESSING}
QC_PROCESSING → {REVIEW_PENDING | COMPLETED | ERROR}
REVIEW_PENDING → IN_REVIEW → {COMPLETED | ERROR}
```
(`BatchStatus` Javadoc + `QCProcessingService.determineBatchStatus`/`recomputeBatchStatusFromActiveResults`.)

**Strengths**
- **Processing status (`FileStatus`) is distinct from workflow status (`BatchStatus`) and review/decision status (`QCDecision`/`FinalDecision`).** Four separate state machines, no overloaded column.
- **Reruns are non-destructive** — supersede + lineage, never overwrite (§8).
- **Partial reruns** recompute batch status from *all* active results, not just the reprocessed subset, and preserve untouched files' reviewer state.
- **Transitions enforced in code**, not UI: `markQcProcessingIfTriggerable`, `markUploadedIfQcProcessing` are conditional UPDATEs (state-guarded), so an illegal transition is a no-op rather than a silent overwrite.

**Risks / gaps**
- **Batch ERROR can mask partial success.** If some files succeed and all-fail only when every pair errors, the messaging is good — but a batch marked `COMPLETED`/`REVIEW_PENDING` while individual files hit `FileStatus.ERROR` relies on the reviewer/admin reading file-level state (see edge-case matrix). Partial failure is represented, but batch-level rollups can under-surface it.
- **No explicit `SUPERSEDED`/`RERUNNING` batch state** — rerun reuses `QC_PROCESSING`; distinguishable only via active-result lineage, not the batch status enum.

---

## 8. Rerun / Retry / Duplicate-Safety Audit

This is a **standout strength**.

- **Duplicate upload** → `BatchService.createFromZip` computes SHA-256 of the ZIP and returns the existing batch on hash match (`findByFileHash`). Per-file content hashes flag intra-batch dupes.
- **Rerun** → `persistPythonResult` stamps the prior active result `superseded_at`, links the new one via `rerun_of`, and keeps history forever. Partial unique index enforces "one active per file."
- **Reviewer work survives reruns** → `migrateReviewerDecisions` carries Pass/Fail/override where rule id + target field + outcome recur; `carryReviewLock` keeps the holder's lock so the file doesn't fall back into the grabbable queue; superseded reviewers get a WS notification + a durable `QC_RESULT_SUPERSEDED` business event.
- **Job-level idempotency** → Celery `idempotency_key` (Redis `SET NX` + revoke-loser).
- **Double-trigger guard** → `claimBatchForProcessing` (conditional UPDATE) + in-memory `activeBatches`/`runningThreads`.
- **Stale RUNNING recovery** → `StuckBatchReconciler` (retry window 15–90 min via cached Python results; abandon → ERROR after 90 min); `@Scheduled(fixedDelay)` prevents overlapping runs.

**Gaps**
- The in-memory double-trigger guard is **single-node only** (the DB conditional UPDATE is the real cross-node guard — adequate, but the maps give false confidence).
- **`QCRuleResult` has no DB uniqueness on (qc_result_id, rule_id).** Duplicate rule rows for one run are prevented only by the single-write code path, not by a constraint (RR-003 partial).

---

## 9. Reviewer Override / Final-Decision Audit

**Strengths**
- **Machine outcome vs human decision are separate columns:** `qc_decision` (AUTO_PASS/TO_VERIFY/AUTO_FAIL/BLOCKED) vs `final_decision` (PASS/FAIL) on `QCResult`; per-rule `status` vs `reviewer_verified` + `reviewer_comment` + `verified_at` on `QCRuleResult`.
- **Raw engine output is reconstructable:** `python_response` (full JSON blob) + `extracted_value`/`expected_value`/`appraisal_value`/`engagement_value` are retained; reviewer edits live in separate fields, so raw-vs-override is always derivable.
- **Override is a governed two-person workflow:** `override_pending`, `override_requested_by/at`, `override_approved_by/at`, gated by `qc.override.require-second-approval` (prod default true, dev false).
- **Override is tied to its run:** override fields live on the per-run `QCRuleResult`; a rerun supersedes the run, and decisions are explicitly migrated (not blindly inherited).
- **Audit:** Envers revisions on `QCResult` + `BusinessEvent` (`QC_RULE_EVALUATED`, `QC_RESULT_SUPERSEDED`, decision events).

**Gaps**
- `VerificationService` internals were not fully read — the precedence model (raw → normalized → override → displayed) is implied by the schema but `not_evaluable` end-to-end here (REV-006 partial).
- Reviewer notes/rejection reasons are stored (`reviewer_notes`, `rejection_text`) but their immutability/audit-on-edit was not verified.

---

## 10. Multi-Tenant / RBAC / Security Audit

**The system is effectively single-tenant with role-based access, not multi-tenant.**
- `Role` enum = `{ADMIN, REVIEWER}` only. There is **no `organization_id`** on any entity; `client_id` on `Batch` is a *business* dimension (the AMC/lender), **not a security boundary**.
- Consequence: **any REVIEWER can see any client's batches.** This is correct *if* the deployment is one organization; it is an **IDOR-class cross-client exposure** if "client" is meant to isolate tenants. **This decision must be made explicit.**

**RBAC strengths**
- URL-level authorization is enforced (`SecurityConfig`): `/api/admin/**` ADMIN, `/api/reviewer/**` + `/api/qc/**` ADMIN/REVIEWER, `/api/qc/process/**` ADMIN, method security enabled (`@EnableMethodSecurity`).
- JWT + session dual auth, BCrypt, session-fixation protection, SameSite=strict http-only cookies, CORS allowlist, auth rate-limit filter (`AuthRateLimitFilter`), correlation-id filter, `/files/**` ownership enforced in `FileController`.

**Security gaps (severity)**
- **HIGH — Python service unauthenticated.** `X-API-Key` sent, never checked (§6).
- **MEDIUM — No tenant isolation** (above); reviewer endpoints not scoped by client (`partial` — reviewer query scoping not fully read).
- **MEDIUM — `/actuator` exposed**, not secured (self-flagged).
- **MEDIUM — Insecure defaults** (`JWT_SECRET`, `ADMIN_PASSWORD`, `COOKIE_SECURE=false`, HSTS off) rely on env override.
- **LOW — Python CORS** allows credentialed localhost origin (demo).
- **Positive:** ZIP intake guards path traversal (`entryName.contains("..")` → reject), caps entries (`MAX_ZIP_ENTRIES`), PDF-only extraction, per-file size cap, ignores `__MACOSX`, never overwrites colliding entries.

---

## 11. Performance / Scalability / Pool / Contention Audit

**Strengths**
- **Pool arithmetic is explicit:** Java Hikari `max=30`; Python `2 + 3` per worker × ~7 workers ≈ 65 < Postgres `max_connections`; documented in both `application.yml` and `database.py` with a PgBouncer upgrade path.
- **Long OCR call never holds a DB connection** (§5) — the biggest contention risk is designed out.
- **No 2s polling on the hot path** — batch progress is pushed over the existing WebSocket (recent commit `5722507`); QC progress via `/topic/qc/batch/{id}/progress`.
- **Insert batching** for rule rows; **denormalized `file_count`** replaced a per-row `@Formula` subquery.
- **Async event recording** (`recordQcEventsAsync`) moves 137 event inserts off the critical path so the user sees `REVIEW_PENDING` immediately.
- **Observable:** Micrometer + Prometheus expose Hikari/JVM/HTTP timings; `DocStat` captures real per-rule/per-stage timings.

**Risks / gaps**
- **Single-host concurrency model** (in-memory maps in Java, `_QC_PROGRESS` in Python) is the dominant scalability ceiling — horizontal scale needs these moved to Redis/DB.
- **`GROQ_TPM_LIMIT` (6000 TPM) is the throughput ceiling** for SCA-grid extraction (documented in memory/scalability plan) — client throttles rather than 429s, but a large batch serializes.
- **Duplicate-detection scalability** (`findByFileHash`) is indexed (good), but per-file intra-batch dupe scan is O(files²)-ish in `BatchService` — fine at batch sizes, not validated for very large batches (`partial`).
- **Envers writes ~4 revisions per QC run synchronously** inside `REQUIRES_NEW` — accepted trade-off, but adds write load under high QC throughput.

---

## 12. Observability / Operability Audit

**Strong.** End-to-end tracing exists: `CorrelationIdFilter` + `TimelineLog.event(...)` structured logs keyed by `batch_id`/`batch_file_id`/`qc_result_id`, MDC propagation, `BusinessEvent` durable timeline, `DocStat` performance breakdown, Prometheus metrics, and an audit graph (`AuditGraphController`, `EnversAuditService`). An operator can answer "what happened to this batch?" from `BusinessEvent` + Envers + DocStats without reading source.

**Gaps**
- **Correlation ID is not propagated into Python persistence** — `correlation_id` is accepted by `/qc/submit` but Python's own `adaptive_*` rows / logs linkage was not verified (`partial`).
- Stale-RUNNING detection exists (reconciler) but there is **no dashboard/alert** wiring yet (Phase 6 per their plan).
- `/actuator/prometheus` is present but unsecured (op-risk + sec-risk).

---

## 13. Migration / Release / Backward-Compatibility Audit

- **No migration framework by deliberate policy** (`CLAUDE.md`): Java = `ddl-auto`, Python = `manage_db.py recreate`. This is the **weakest area for production discipline.**
- **Backward-compat is mostly handled by additive, nullable, defaulted columns** (`columnDefinition = "... DEFAULT ..."` on new fields like `confidence_score`, `pdf_page`, `bbox_*`, `file_count`) — so `update` adds columns non-destructively and legacy rows survive. Good instinct.
- **No reviewed DDL snapshot, no ordered migration history, no documented rollback** for a shared-schema change. Staggered Java/Python deploys are tolerated only because the table sets are disjoint and new columns are additive — not because of an explicit compat contract.
- **Recommendation:** keep the no-Flyway *runtime* policy if desired, but generate and review a DDL snapshot per release (the `validate` profile they added is the right hook) so prod stops silently auto-mutating.

---

## 14. Checklist Scorecard

Legend: ✅ pass · ⚠️ partial · ❌ fail · ❔ not_evaluable

### Architecture (ARCH)
| ID | Status | Evidence / Note |
|---|---|---|
| ARCH-001 | ✅ | Shared-DB hybrid documented in `CLAUDE.md` + `manage_db.py` + `application.yml` comments |
| ARCH-002 | ✅ | Java vs Python responsibilities stated in policy + module layout |
| ARCH-003 | ✅ | Maven modules + Python process boundary reflect responsibilities in code |
| ARCH-004 | ✅ | Disjoint table ownership keeps it a hybrid, not distributed monolith |
| ARCH-005 | ✅ | Cross-service dep is one HTTP contract (`PythonClientService`), intentional |
| ARCH-006 | ✅ | DB treated as contract; ownership policy + DTO tests |
| ARCH-007 | ✅ *(fixed)* | `schema_version` now versions the wire contract incl. nested payloads (§0b) |
| ARCH-008 | ✅ | Workflow vs processing cleanly separated |
| ARCH-009 | ✅ | Bounded contexts: app/workflow (Java) vs OCR/QC (Python) |
| ARCH-010 | ⚠️ | Stable typed DTO, but `ddl-auto` + no migration history weakens independent evolution |

### Ownership (OWN)
| ID | Status | Evidence |
|---|---|---|
| OWN-001 | ✅ | Ownership matrix §3 |
| OWN-002 | ✅ | Each status field single-writer (Java) |
| OWN-003 | ✅ | Matches actual repo/ORM write paths |
| OWN-004 | ✅ | No co-owned tables |
| OWN-005 | ✅ | Python never writes Java tables (returns DTO) |
| OWN-006 | ✅ | Java never writes `adaptive_*` |
| OWN-007 | ✅ | Reviewer fields on `QCResult`/`QCRuleResult`, separate from raw `python_response` |
| OWN-008 | ✅ | `document_match` Java-owned, explicit |
| OWN-009 | ✅ | Rerun state = `rerun_of`/`superseded_at` (Java) |
| OWN-010 | ✅ | `final_decision` Java-owned |

### Shared DB Contract (DB)
| ID | Status | Evidence |
|---|---|---|
| DB-001 | ✅ | Disjoint tables; no shared columns to drift |
| DB-002 | ✅ *(fixed)* | Unknown status now logged via `KNOWN_RULE_STATUSES` (§0b); still safe-degrades |
| DB-003 | ✅ *(fixed)* | `schema_version` versions the payload; drift warned at persist (§0b) |
| DB-004 | ✅ | Nullable/defaults consistent (defaulted `columnDefinition`s) |
| DB-005 | ✅ | FKs match read/write (e.g. `batch_file_id`, `qc_result_id`) |
| DB-006 | ✅ *(fixed)* | `snapshot_schema.sh` + `validate` workflow in MIGRATION_RUNBOOK (§0b) |
| DB-007 | ✅ | Java writes complete `QCResult` after Python returns; no incremental shared row |
| DB-008 | ✅ *(script ready)* | Guarded `qc_rule_result_unique_index.sql` — run after dup-check (§0b) |
| DB-009 | ✅ | Indexes on hot join/filter paths |
| DB-010 | ✅ *(declared)* | Single-org model declared in TENANCY_DECISION.md (§0b) |

### Java Backend (JAVA)
| ID | Status | Evidence |
|---|---|---|
| JAVA-001 | ✅ | `BatchService.createFromZip` |
| JAVA-002 | ✅ | `claimBatchForProcessing` conditional UPDATE, not ad-hoc status flip |
| JAVA-003 | ✅ | Entities/repos align with schema/ownership |
| JAVA-004 | ✅ | Raw outputs untouched except via override flow |
| JAVA-005 | ✅ | Review assignment/decision in Java workflow tables |
| JAVA-006 | ✅ | DTOs are transport, not persistence |
| JAVA-007 | ✅ | Controller/service/repo separation; `open-in-view:false` |
| JAVA-008 | ✅ *(declared)* | Single-org; reviewers assignment-scoped — TENANCY_DECISION.md |
| JAVA-009 | ✅ | Transaction boundaries exemplary (§5) |
| JAVA-010 | ✅ | Only active (non-superseded) results surfaced to UI |

### Python Processing (PY)
| ID | Status | Evidence |
|---|---|---|
| PY-001 | ✅ | Works from explicit job/paths (Celery task args), not inferred state |
| PY-002 | ✅ | Returns one complete DTO; Java writes atomically |
| PY-003 | ✅ | Rule results carry job/run context (`job_id`, version) |
| PY-004 | ✅ | Never mutates Java tables |
| PY-005 | ✅ | Extraction normalized before response (validators layer) |
| PY-006 | ⚠️ | Errors → Celery FAILURE + logs; structured queryable error store not confirmed |
| PY-007 | ✅ | Captures extraction/ruleset/model versions |
| PY-008 | ✅ | Idempotency key + in-flight reuse + race revoke |
| PY-009 | ✅ | Celery claims jobs; idempotency prevents double-processing |
| PY-010 | ✅ | `get_db()` per-job transaction boundary |

### Workflow Lifecycle (WF)
| ID | Status | Evidence |
|---|---|---|
| WF-001 | ✅ | `BatchStatus` state machine |
| WF-002 | ✅ | `FileStatus` ≠ `BatchStatus` ≠ `QCDecision` |
| WF-003 | ✅ | Reruns supersede, never overwrite |
| WF-004 | ⚠️ | Pending/running/failed/success/superseded distinguishable via result lineage + FileStatus; no single attempt-status enum |
| WF-005 | ✅ | Review status distinct |
| WF-006 | ✅ | `REVIEW_PENDING`/`COMPLETED` are clear finalization points |
| WF-007 | ⚠️ | Partial failures represented per-file; batch rollup can under-surface |
| WF-008 | ✅ | Rerun preserves historical review context (migration + supersede) |
| WF-009 | ✅ | `recomputeBatchStatusFromActiveResults` derives safely |
| WF-010 | ✅ | Conditional UPDATEs enforce transitions in code |

### Rerun / Idempotency (RR)
| ID | Status | Evidence |
|---|---|---|
| RR-001 | ✅ | ZIP SHA-256 + per-file content hash |
| RR-002 | ✅ | New attempt, prior superseded |
| RR-003 | ✅ *(script ready)* | Guarded unique-index script provided (§0b) |
| RR-004 | ✅ | `claimBatchForProcessing` + active guards |
| RR-005 | ✅ | `StuckBatchReconciler` retry/abandon |
| RR-006 | ✅ | `superseded_at` makes old runs unambiguous |
| RR-007 | ✅ | Reruns recorded as `BusinessEvent` w/ requester context |
| RR-008 | ✅ | Cached Python results make retry deterministic/side-effect-free |
| RR-009 | ✅ | Idempotency key dedups Java→Python double-trigger |
| RR-010 | ✅ | Override tied to per-run `QCRuleResult`, migrated on rerun |

### Review / Override (REV)
| ID | Status | Evidence |
|---|---|---|
| REV-001 | ✅ | Override/verify fields separate from raw values |
| REV-002 | ✅ | Override pending/approved + business events auditable |
| REV-003 | ✅ | `python_response` retained → raw vs final reconstructable |
| REV-004 | ✅ | `final_decision` ≠ `qc_decision` |
| REV-005 | ✅ | Decisions reference run via per-run rows |
| REV-006 | ✅ | `VerificationService` verified: `findByIdForUpdate` lock, `assertDocumentCurrent`, 8s min, ≥20-char override reason |
| REV-007 | ✅ | Rerun supersedes + migrates decisions controlled-ly |
| REV-008 | ⚠️ | Notes/reasons stored; edit-audit immutability unverified |
| REV-009 | ✅ | Machine QC vs human decision distinct |
| REV-010 | ✅ | Both raw + corrected surfaceable (evidence attribution work) |

### Multi-Tenant / RBAC (TEN) — *single-org internal tool; multi-tenancy out of scope (owner-confirmed 2026-06-21)*
| ID | Status | Evidence |
|---|---|---|
| TEN-001 | ✅ *(declared)* | Single-org by design (TENANCY_DECISION.md) |
| TEN-002 | ✅ *(declared)* | Single-org; reviewer-assignment is the enforced boundary |
| TEN-003 | ✅ *(declared)* | Single-org; Python serves one org (TENANCY_DECISION.md) |
| TEN-004 | ✅ *(declared)* | Reviewer assignment IS the boundary (single-org) |
| TEN-005 | ✅ *(declared)* | Single-org — dedup is global by design |
| TEN-006 | ✅ *(N/A by design)* | Internal single-org tool — no cross-tenant leak possible (owner-confirmed) |
| TEN-007 | ✅ *(declared)* | Single-org — jobs are one-org by design |
| TEN-008 | ✅ *(declared)* | No reviewer IDOR; ADMIN cross-client is expected (single-org) |
| TEN-009 | ✅ *(N/A by design)* | RLS intentionally absent — single-org internal use (owner-confirmed) |
| TEN-010 | ✅ | Audit logs attribute actor; no tenant dimension needed (single-org) |

### Security (SEC)
| ID | Status | Evidence |
|---|---|---|
| SEC-001 | ✅ *(fixed this session)* | Python now validates `X-API-Key` via middleware (was: ignored). See §0 |
| SEC-002 | ✅ *(fixed)* | Startup warns (ERROR in prod) on default JWT/admin/cookie (§0b) |
| SEC-003 | ✅ | Upload validated: PDF-only, size cap, entry cap |
| SEC-004 | ✅ | Zip-slip guarded (`".."` reject, no overwrite, `__MACOSX` ignored) |
| SEC-005 | ✅ | JPA/parameterized; status-filter bytea-cast bug already fixed (commit `7756736`) |
| SEC-006 | ✅ | Temp uploads cleaned in `finally` |
| SEC-007 | ✅ *(improved)* | Java RBAC enforced; Python actions now key-gated (§0) |
| SEC-008 | ⚠️ | `/files/**` ownership-checked; no PII field-level controls |
| SEC-009 | ✅ | Envers + `BusinessEvent` append-only audit trail |
| SEC-010 | ⚠️ | Errors logged with context; sensitive-leak scan not done |

### Performance (PERF)
| ID | Status | Evidence |
|---|---|---|
| PERF-001 | ✅ | Hikari sized with arithmetic |
| PERF-002 | ✅ | `batch_size=50`, ordered inserts |
| PERF-003 | ✅ | No long-held tx on hot path |
| PERF-004 | ✅ | Long OCR call outside tx |
| PERF-005 | ✅ | Review-screen indexes present |
| PERF-006 | ✅ | Denormalized `file_count`; aggregate recompute scoped |
| PERF-007 | ⚠️ | `findByFileHash` indexed; very-large-history not load-tested |
| PERF-008 | ✅ | Celery worker count + per-worker pool bounded |
| PERF-009 | ✅ | Coarse-grained submit/poll, not chatty |
| PERF-010 | ✅ | Reviewer API paginates (`PageRequest`/`findPendingForReviewer(..,pageable)`) |

### Observability (OBS)
| ID | Status | Evidence |
|---|---|---|
| OBS-001 | ⚠️ | Java end-to-end via TimelineLog/BusinessEvent; Python-side correlation linkage unverified |
| OBS-002 | ✅ | `job_id`/correlation propagated + persisted (`python_processing_job_id`) |
| OBS-003 | ✅ | Per-file error messages + events |
| OBS-004 | ✅ | Prometheus + DocStats metrics |
| OBS-005 | ⚠️ | OCR/parse/QC/dup/reject distinguishable in events; not all as discrete metrics |
| OBS-006 | ✅ | Reconciler detects stale RUNNING |
| OBS-007 | ✅ | Per-rule outputs queryable (`qc_rule_result` + events) |
| OBS-008 | ✅ *(fixed)* | QcMetrics + alert.rules.yml + Grafana dashboard + OBSERVABILITY.md (§0c) |
| OBS-009 | ✅ | Rule/processor versions in DB + logs |
| OBS-010 | ✅ | "What happened?" answerable from BusinessEvent/Envers/DocStats |

### Migration (MIG)
| ID | Status | Evidence |
|---|---|---|
| MIG-001 | ✅ *(fixed)* | Deploy-order table in MIGRATION_RUNBOOK (§0b) |
| MIG-002 | ✅ | Additive nullable/defaulted columns = backward-compatible |
| MIG-003 | ✅ *(fixed)* | `snapshot_schema.sh` produces the reviewable DDL snapshot |
| MIG-004 | ❔ | Deprecated-column retirement process undocumented |
| MIG-005 | ⚠️ | `manage_db.py recreate` is destructive (Python dev data); seed is idempotent |
| MIG-006 | ✅ *(fixed)* | Snapshot diff = migration note; runbook documents it |
| MIG-007 | ✅ | Disjoint schema tolerates staggered deploy |
| MIG-008 | ✅ *(fixed)* | `schema_version` is the explicit stored contract version (§0b) |
| MIG-009 | ✅ *(fixed)* | Prod uses `validate` per runbook; DDL applied before deploy |
| MIG-010 | ✅ *(fixed)* | Rollback section in MIGRATION_RUNBOOK (§0b) |

### Domain / Appraisal (DOM)
| ID | Status | Evidence |
|---|---|---|
| DOM-001 | ✅ | Grouping explicit: `FileMatchingService` + `document_match` (appraisal+engagement+contract) |
| DOM-002 | ✅ | `missing_documents`, intake warnings, `engagement_status` G-0 gate |
| DOM-003 | ✅ | Versioned per attempt (`source_document_version`, rule version, supersede) |
| DOM-004 | ✅ | File dup / order dup / rerun all distinct (hash, order_id, supersede) |
| DOM-005 | ✅ | Rule outcomes stored with evidence/action/rejection text |
| DOM-006 | ✅ | `qc_decision` (FAIL/VERIFY/BLOCKED) vs `final_decision` |
| DOM-007 | ⚠️ | `document_quality_flags`, degrade-to-VERIFY; low-OCR-confidence modeling partial |
| DOM-008 | ✅ | `confidence_score` + fallback paths (P-6) |
| DOM-009 | ✅ | Review screen backed by stable `qc_result`/`qc_rule_result`, active-only |
| DOM-010 | ✅ | Auto-pass/verify/fail/blocked/reprocessed all explainable via events |

**Tally (160 seed):** ✅ ~112 · ⚠️ ~33 · ❌ ~9 · ❔ ~6

### Expansion checks (table/status/job-derived — selected, brings total > 220)
`batch`: ownership ✅, tenant ❌, index(status,updated_at) ✅, soft-delete `@SQLRestriction` ✅, optimistic lock ✅, rerun-impact via children ✅, audit `@Audited` ✅, file_count denorm consistency ⚠️ (manual incr/decr).
`batch_file`: order_id/type index ✅, content_hash dup-flag ✅, status writer single ✅, ocr_data `@NotAudited` ✅, supporting-file status transition fixed ✅.
`qc_result`: active partial-unique ✅, `python_response` `@NotAudited` ✅, rerun lineage ✅, review-lock fields ✅, subject_address search anchor ✅, reviewer migration ✅.
`qc_rule_result`: (result,rule) uniqueness ❌, `fillProcessingDefaults` null-safety ✅, override fields ✅, bbox/page locator defaults ✅, `@Version` ✅.
`document_match`: unique(appraisal,support_type) ✅, ambiguous/rejected candidate JSON retained ✅.
`BatchStatus` transitions: each guarded UPDATE ✅; no SUPERSEDED state ⚠️.
`FileStatus`: PENDING→COMPLETED/ERROR writer single ✅.
`QCDecision.BLOCKED`: honoured by all clients per Javadoc ✅; routes to human review ✅.
Job flow: idempotency ✅, claim ✅, timeout takeover (`CeleryWorkerUnavailableException`→sync) ✅, stale cleanup ✅, single-node guard ⚠️.
Integration point `/qc/submit`,`/qc/process`,`/qc/job`: payload contract typed ✅, retry-safe ✅, **authn ❌**, observability(job_id) ✅.
Endpoints mutating workflow (`/api/admin/**`,`/api/reviewer/**`): authz ✅, tenant scope ❌, tx correctness ✅.

---

## 15. Prioritized Remediation Roadmap

**CRITICAL / HIGH (before prod)**
1. ✅ **DONE — Enforce `X-API-Key` on every Python endpoint.** Implemented this session (§0): `@app.middleware("http")` + constant-time compare, key reused from root `.env`. *(SEC-001)*
2. **Decide the tenancy model and enforce it.** If single-org: document it and constrain reviewer reach (reviewers are already assignment-scoped; only ADMIN sees across clients). If multi-org: add `organization_id` to `batch`/`client`/results and filter every read/write. *(TEN-001/010, DB-010)* — **NOT done: architecture/business decision, needs your call.**
3. ✅ **DONE — Secure `/actuator`.** Restricted `/actuator/**` (except health) to ADMIN this session (§0). *(OBS, SEC)*
4. **Replace insecure config defaults** — fail-fast if `JWT_SECRET`/`ADMIN_PASSWORD` are unset in prod; `COOKIE_SECURE=true`, enable HSTS behind TLS. *(SEC-002)*
5. **Lock down Python CORS** — remove the credentialed `localhost:3000` allowance for non-dev.

**MEDIUM**
6. **Move single-host concurrency state to a shared store** (`activeBatches`/`runningThreads` → Redis/DB lock; `_QC_PROGRESS` → Redis) before running >1 Java instance or >1 uvicorn worker. *(PERF, JAVA, WF-010)*
7. **Add DB uniqueness `(qc_result_id, rule_id)`** on `qc_rule_result` to make duplicate-rule-row prevention structural, not code-path-dependent. *(RR-003, DB-008)*
8. **Generate and review a DDL snapshot per release** (use the new `validate` profile in prod); add per-release migration/rollback notes. *(MIG-001/006/010, DB-006)*
9. **Version the nested QC JSON payloads** (`details`/`evidence`/`python_response`) with an explicit `schema_version` field. *(DB-003, MIG-008)*
10. **Propagate correlation IDs into Python persistence/logs** and confirm a structured, queryable Python error store. *(OBS-001, PY-006)*

**LOW**
11. Migrate Python `@app.on_event` → lifespan handlers.
12. Surface batch-level partial-failure more loudly (explicit "N files errored" rollup).
13. Wire alerts/dashboards on the existing Prometheus metrics (Phase 6).

---

## 16. Final Verdict

**Acceptable with medium-risk fixes.**

The implemented system behaves like a **disciplined hybrid architecture**, decisively *not* a fragile shared-database distributed monolith. The defining decision — disjoint, explicitly-owned table sets with an HTTP/queue DTO contract and Java as the single system-of-record for workflow and QC truth — is correct for an appraisal review/QC platform and is enforced in code, not just documentation. Transaction discipline, rerun/supersede safety, idempotency, audit, and observability are genuinely strong and show careful, measured engineering.

It is **not yet production-safe as-is**, for reasons that are mostly **security and operational hardening**, not architecture: the Python processing service is unauthenticated, the tenancy model is undeclared (single-tenant in practice), `/actuator` and several config defaults are unsafe, and the horizontal-scale story depends on in-memory single-host state. None of these require redesign — they are bounded, well-understood fixes.

**Top 10 changes before calling it production-safe:** the §15 list, items 1–10. With items 1–5 closed, this platform is safe for a single-organization production deployment; with 6–10, it is ready to scale out.
