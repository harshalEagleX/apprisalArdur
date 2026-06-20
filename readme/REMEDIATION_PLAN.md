# SHAL — Architecture, Load & Quality Remediation Plan

> **Prepared as:** senior-architect + inspector review of the SHAL platform
> (Semantic Heuristic Appraisal Liaison — appraisal QC automation).
> **Scope:** Frontend (Next.js/TS), Java backend (Spring Boot, multi-module),
> Python compute service (FastAPI + Celery), Postgres (Neon), Redis, Groq.
> **Target operating point:** 50 users · 5,000 docs · ~250 docs/day · single 8 GB host.
> **Status:** findings are evidence-based (file:line where applicable); this is a
> remediation plan, not a record of completed work.

---

## 1. Executive summary

The platform is **functional and, in several places, genuinely well-engineered**:
Celery `acks_late` + `prefetch=1`, `@Version` optimistic locking, ~56
JOIN-FETCH/`@EntityGraph` usages, `REQUIRES_NEW` per-file transaction isolation,
idempotent submit with Redis in-flight dedup, graceful degradation (P-6), an
`AuthRateLimitFilter`, global exception handlers, and a single-system Python
extraction/rules pipeline (the old parallel `phase2_extraction` / `app/rules`
system has been removed).

It is, however, a strong **single-tenant / low-concurrency build that is not yet
production-hardened for scale, schema evolution, or audit-grade discipline**.
Three issues genuinely gate a compliance launch:

1. **Groq TPM throughput ceiling** — caps the platform near its 250-docs/day goal.
2. **Schema managed by `ddl-auto=update` in production** — no migrations/rollback.
3. **Test coverage on the decision + UI layers is near zero.**

Everything else is correctness, maintainability, or cost.

### Quality scorecard

| Dimension | Grade | One-line |
|---|---|---|
| API design & contract | B | Clean BFF split; chatty progress; unbounded rules payload |
| Load & performance | C+ | Groq TPM is a hard ceiling; blocking sync fallback |
| Concurrency & data integrity | B+ | Optimistic locking, idempotency, txn isolation — solid |
| Security | B | Good baseline; secrets-on-disk, WS permitAll to verify |
| Resilience & observability | B− | Graceful degradation real; silent excepts; uncalibrated confidence |
| Testing | D | 22 Py / 4 Java / 0 frontend test files |

### DRY scorecard

| Stack | DRY | Biggest duplication |
|---|---|---|
| Frontend | **B+** | status/severity style maps copied across files; monolithic `api.ts` |
| Python | **B−** | ~46% of rule results bypass the `_res` helper; god rule files |
| Java | **C+** | 7 client overloads + duplicated multipart/error code; 30× manual DTO `put()`; manual entity boilerplate |

---

## 2. Consolidated findings (severity-ranked)

| # | Sev | Finding | Evidence / location |
|---|---|---|---|
| 1 | 🔴 | Groq TPM (6k) is a hard throughput ceiling; ~13 LLM calls/doc ≈ 26k tokens/doc → ~230 LLM-docs/day max | `llm_groq.py`, `celery_app.py`, `GROQ_TPM_LIMIT` |
| 2 | 🔴 | `ddl-auto: update` in **production** — no migration history/rollback, silent drift | `app/src/main/resources/application.yml:36` |
| 3 | 🔴 | Test coverage: 0 frontend, 4 Java test files for ~15k LOC / 60 endpoints | repo-wide |
| 4 | 🔴 | 2s HTTP polling per active batch despite an existing WebSocket stack | `frontend/hooks/useBatchPolling.ts:220` |
| 5 | 🔴 | 31 silent `except Exception` blocks (pass / return {} / no log) | `ocr-service/app/qc`, `app/extraction` |
| 6 | 🟠 | Blocking decision is count-based; HOLD folded into verify count → blocking enforced only in the UI | `QCProcessingService.determineDecision` |
| 7 | 🟠 | Static per-layer confidence constants drive routing (uncalibrated) | `app/extraction/layers/orchestrator.py` `_CONF` |
| 8 | 🟠 | Sync `/qc/process` fallback blocks Tomcat request threads for full OCR (20–25s) | `PythonClientService.processQC`, `RestTemplateConfig` |
| 9 | 🟠 | Envers write-amplification + unbounded `_AUD` growth (14 audited entities), no pruning | `@Audited` entities |
| 10 | 🟠 | 53× naive `LocalDateTime.now()` vs 11× `Instant.now()` for audit/SLA timestamps | Java backend |
| 11 | 🟠 | Inconsistent date normalization: `_extract_signature_date` emits `MM/DD/YYYY`, others ISO → breaks SIG-D | `l5_uad_template._extract_signature_date` |
| 12 | 🟠 | DB connection budget ~60 (Java 30 + Python 5×6) scales linearly with workers | `database.py`, `application.yml` Hikari |
| 13 | 🟠 | Nested concurrency: orchestrator `ThreadPool(7)` + OCR `ThreadPool(4)` × 6 Celery procs on 8 GB | `orchestrator.py:163`, `adaptive_ocr.py:372` |
| 14 | 🟠 | 256 MB upload, no ZIP entry-count cap (OOM/DoS); error msg says 100 MB | `application.yml:59`, `GlobalWebExceptionHandler:47` |
| 15 | 🟠 | 7 god files concentrate responsibility (`main.py` 2,293; `QCProcessingService` 1,573; …) | see §6 |
| 16 | 🟡 | Unbounded rules payload + ~30 manual `put()` per rule, no pagination/projection | `ReviewerApiController:390` |
| 17 | 🟡 | Float arithmetic for money (concession %, value compare) | `document_reconciler.py:155`, `contract_extractor.py:230` |
| 18 | 🟡 | No general API rate-limit (only login); `details` JSON-in-column unqueryable; orphaned temp files on SIGKILL; `/ws/** permitAll` to verify; secrets on disk (no vault) | various |

---

## 3. Detailed findings by area

### 3.1 API design & call contract
- **Chatty progress (🔴 #4):** `useBatchPolling` polls every 2,000 ms per active batch; with N watchers this is `N × batches × 0.5 req/s` of DB-hitting status reads — while `WebSocketConfig` + `WebSocketAuthHandshakeInterceptor` already exist.
- **Unbounded rules payload (🟡 #16):** `GET /qc/{id}/rules` returns all 150–218 rules with evidence + `details` JSON (200–500 KB), assembled with ~30 manual `ruleMap.put(...)` per rule. No pagination/projection.
- **`details` as JSON string column (🟡):** display-only OK, but unqueryable/unvalidated.

### 3.2 Load & performance
- **Groq TPM ceiling (🔴 #1):** ~13 LLM calls/doc × ~2k tokens ≈ 26k tokens/doc against a 6,000 TPM Redis bucket shared by 6 workers ⇒ one doc ≈ 4.3 min of the *whole account's* budget. At ~31 docs/hr the demand (~13k tokens/min) exceeds supply (6k) → hard cap ≈ **230 LLM-docs/day**. Concurrency=6 is already past the TPM limit (workers throttle-wait).
- **Blocking sync fallback (🟠 #8):** `RestTemplate` thread-per-call; the `/qc/process` fallback holds a Tomcat thread for the full OCR; a burst (Celery down) can exhaust the request pool.
- **Nested concurrency (🟠 #13):** up to ~42+ threads + 3× PyMuPDF pixmaps + Tesseract on 8 GB; masked today only because the TPM throttle serializes LLM docs.
- **Connection budget (🟠 #12):** `pool_size 2 + overflow 3 = 5` per Celery proc × 6 = 30, plus Java Hikari 30 = ~60 Postgres connections; grows linearly with workers.

### 3.3 Concurrency & data integrity
- **Strong:** `@Version` (Batch, QCRuleResult), `REQUIRES_NEW` per file-pair, long Python call outside the DB txn, idempotent submit, reviewer-decision carry-over on rerun.
- **Weak (🟠 #6):** `determineDecision` = `verify>0 → TO_VERIFY; failed>0 → AUTO_FAIL; else PASS`. HOLD is counted as verify; a BLOCKING G-0 HOLD is indistinguishable from a routine VERIFY at the decision layer — only the reviewer UI enforces blocking.

### 3.4 Security
- **Good:** non-wildcard CORS with `allowCredentials(true)`, `/api/auth/** permitAll` + `anyRequest().authenticated()`, Python behind `X-API-Key`, `.env` git-ignored (verified), `AuthRateLimitFilter` for login.
- **Watch:** secrets on disk with no vault for the prod path; `/ws/** permitAll` (verify the handshake interceptor rejects anonymous upgrades); no per-user/IP throttle on the 60 authenticated endpoints.

### 3.5 Resilience & observability
- **Good:** real graceful degradation (P-6).
- **Weak (🔴 #5):** 31 silent exception swallows hide root causes (no log) — can't distinguish "no data" from "crashed."
- **Weak (🟠 #7):** confidence is asserted via static constants, not measured; routing thresholds are therefore uncalibrated despite the measurement harness existing.

### 3.6 Time & numeric correctness
- **Naive timestamps (🟠 #10):** 53× `LocalDateTime.now()` for audit/SLA/decision-latency → DST/TZ drift in the compliance trail.
- **Date-format inconsistency (🟠 #11):** most extractors emit ISO; `_extract_signature_date` emits `MM/DD/YYYY` → SIG-D signature-vs-effective comparison breaks.
- **Float money (🟡 #17):** concession `%` math and value compares use floats.

### 3.7 Data model & schema
- **`ddl-auto=update` in prod (🔴 #2):** Hibernate mutates the live schema with no history/review/rollback; never drops/renames safely. CLAUDE.md bans Flyway/Liquibase — so the fix must live *within* that policy (see §4.E2).
- **Envers growth (🟠 #9):** 14 audited entities double writes and grow `_AUD` tables unbounded; no pruning/archival.

### 3.8 Testing (🔴 #3)
22 Python / 4 Java / **0 frontend** test files. The Java decision/persistence layer and the reviewer UI (where blocking is actually enforced) have no automated coverage. Combined with `ddl-auto` and naive timestamps, regressions can ship silently.

---

## 4. Remediation playbook (the "how", kept clean)

For each: **pattern → specific how in this stack → the rule that keeps it clean.**

### A. Chatty progress + too many API calls

**A1 — Progress over the existing WebSocket.**
```
Python task ──publish progress JSON──▶ Redis pub/sub "batch:{id}:progress"
Java @RedisMessageListener ─▶ SimpMessagingTemplate.convertAndSend("/topic/batch/{id}", payload)
Frontend: one STOMP subscription per *visible* batch (no interval)
```
One Redis listener fans out to N clients; keep a single 20–30 s reconnect-fallback poll.
*Clean rule:* progress is an event stream, never a query.

**A2 — TanStack Query (or SWR) in front of every read.** Free request dedup,
stale-while-revalidate caching, retries, and invalidation-on-mutation. Components
call typed `useXxx()` hooks, never `fetch` directly.

**A3 — Cacheable reads.** ETag / `Cache-Control` on `GET /qc/{id}/rules` and the
queue (304s); wrap hot read services in the existing Caffeine `CacheConfig`
(short TTL → request collapsing); paginate + field-project the queue and rules
(load summaries, fetch evidence on expand).

**A4 — BFF aggregates; client never fans out.** One screen ⇒ one (or few)
aggregate endpoints assembled server-side.

### B. Throughput (Groq TPM — the only hard cap)
1. **Collapse ~13 calls → 1–2** via one structured multi-field prompt (gap-fill + Layer-B reasoning batched).
2. **Content-hash LLM cache (Redis)**, keyed by `hash(section + prompt_version)`; re-runs cost 0 tokens.
3. **LLM only on demand** — gate behind deterministic-extraction-failed/low-confidence.
4. **Make the ceiling visible**: emit queue depth + token-budget utilization; tune Celery `concurrency` down to ~2–3 to match the real bottleneck.
*Clean rule:* every LLM call flows through one `llm_call(purpose, prompt, cache_key)` wrapper (cache → budget → telemetry). No raw Groq calls in extractors.

### C. Performance & capacity (8 GB host)
- **Bounded executor** for the sync Python fallback (use `QC_EXECUTOR`), never Tomcat's request pool.
- **Connection-pool budget as one documented formula**; use Neon's **pooled (PgBouncer)** endpoint; set `DB_POOL_SIZE` per worker explicitly.
- **Cap nested concurrency** under Celery (orchestrator pool → 3–4 via env); the worker process is already the parallelism unit.
- **Guard uploads**: cap ZIP entry count + uncompressed size; fix the 100 MB/256 MB message mismatch; render PDF at the lowest DPI that still OCRs.
*Clean rule:* every resource limit is config with a documented budget (P-4).

### D. DRY
- **Java:** one `PythonCallRequest` params object + `buildMultipartBody(req)` (replaces 7 overloads + duplicated multipart/error code); a `RuleResultMapper` (entity→DTO, one place, replaces ~30 `put()`); Lombok on entities (delete manual builder/getters).
- **Python:** make the `_res`/`_mk` helper mandatory (lint/test fails on direct `RuleResult(`); one `llm_call(...)` wrapper; keep the `field_validators` registry (P-3 boundaries).
- **Frontend:** hoist status/severity maps into `lib/ruleStatus.ts`; TanStack Query removes fetch/loading/error boilerplate.
*Clean rule:* status→style, fetch logic, and DTO mapping each have exactly one home.

### E. Cleanliness that lasts
- **E1 — Decision as explicit state in the engine.** Add a `BLOCKED` decision derived from rule statuses (any HOLD → BLOCKED), computed in `determineDecision`/the engine, so the blocking contract holds for any client — not just the UI.
- **E2 — Migrations within the no-Flyway policy.** Prod `ddl-auto: validate`; generate a reviewed DDL snapshot from entities (Hibernate schema export), commit it, apply manually per policy; add a **CI drift check** that fails on unreviewed entity↔snapshot divergence.
- **E3 — Time discipline.** Persist timestamps as `Instant`/UTC; format to local only at the edge; fix the one `MM/DD/YYYY` extractor so all dates are ISO before rules consume them.
- **E4 — Observability.** Log every silent except (field + stage); wire the measurement harness as a calibration loop so confidence is earned (then routing thresholds mean something).
- **E5 — Tests where blocking lives.** Unit-test `determineDecision` + decision/persist (Java); component-test `RuleCard`/verify flow (Vitest + Testing Library); one Playwright E2E (reuse the `brain` harness): upload → block → acknowledge → pass.
- **E6 — Envers hygiene.** Add a scheduled prune/archive for `_AUD` tables.
- **E7 — God-file split** opportunistically when touched (P-9), by responsibility (`main.py`→routers; `QCProcessingService`→orchestrator/persister/decision/events).

---

## 5. Phased rollout

| Phase | Work | Why first | Risk |
|---|---|---|---|
| **1 — Safe wins** | Log the 31 silent excepts · `lib/ruleStatus.ts` · ETag on reads · ZIP entry cap + fix upload error msg | pure upside, no behavior change | 🟢 low |
| **2 — Chatty fix** | Progress over WS (A1) + single fallback poll · TanStack Query for reads (A2) | removes the call-volume problem | 🟡 med |
| **3 — Throughput** | Batch LLM 13→1–2 (B1) · content-hash cache (B2) · tune Celery concurrency | lifts the only hard ceiling | 🟡 med |
| **4 — Correctness** | `BLOCKED` decision state (E1) · `Instant`/UTC (E3) · date-format fix | compliance integrity | 🟡 med |
| **5 — Structural** | Java params-object + mapper + Lombok (D) · pool budget (C) · `ddl-auto=validate` + CI drift (E2) · tests (E5) · god-file splits (E7) · Envers prune (E6) | long-game health | 🟠 higher |

**Measurement gate (P-8):** each phase states what metric moves and by how much
before it's "done" — e.g. Phase 2: progress req/s → ~0 steady-state; Phase 3:
tokens/doc and docs/day-capacity; Phase 4: extraction accuracy unchanged + a
BLOCKED decision visible end-to-end.

---

## 6. God files (split targets, by LOC)

| File | LOC | Suggested split |
|---|---|---|
| `ocr-service/app/services/…`/`main.py` | 2,293 | FastAPI routers by domain (qc / docstats / progress / admin) |
| `qc/.../QCProcessingService.java` | 1,573 | orchestrator · persister · decision · event-recorder |
| `ocr-service/app/qc/rules/sales_comparison.py` | 1,336 | split by rule cluster (grid / adjustments / dates / photos) |
| `ocr-service/app/extraction/layers/l5_uad_template.py` | 1,224 | per-section extractors |
| `qc/.../ReviewerApiController.java` | 904 | controller + `RuleResultMapper` |
| `frontend/app/reviewer/verify/[id]/page.tsx` | 1,055 | extract sub-components + query hooks |
| `frontend/lib/api.ts` | 1,023 | split per domain module |

---

## 7. Guiding principle (so the debt doesn't creep back)

> **Every cross-boundary value is an event or a typed contract; every repeated
> shape has exactly one home; every resource limit is config with a budget; and
> every decision is a state computed once in the engine.**

This is the through-line that prevents the chatty/duplicated/uncalibrated/
UI-enforced-blocking patterns from reappearing, and it is consistent with the
project's own engineering principles (P-3 separation, P-4 config-over-hardcoding,
P-6 graceful degradation, P-8 measure-first, P-9 incremental debt paydown,
P-11 observability).

---

## 8. How these findings were gathered

Structural metrics from the code-review knowledge graph (303 files, 2,756 nodes,
`find_large_functions`, stats) + targeted scans (exception handling, polling
intervals, JOIN-FETCH/index counts, pool config, upload limits, `ddl-auto`,
timestamp APIs, test-file counts, multipart caps) + direct reading of the
hot-path files during the review session. Counts cited (31 silent excepts, 53
`LocalDateTime.now()`, ~56 JOIN-FETCH, 60 endpoints, test-file counts) are from
those scans and should be treated as accurate-as-of-review, not continuously
verified.

*Last updated: 2026-06-20.*
