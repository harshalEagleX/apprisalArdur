# Regression Test Audit — SHAL Appraisal QC (`demo` branch)

**Role:** Senior QA / regression engineer.
**Change range audited:** `ecce8ab..a16bcfa` (15 commits on `demo`, June 2026).
**Method:** map each change to its blast radius; mark coverage **Covered / Partial / Missing**
with concrete file evidence; flag missing coverage explicitly; "none found" where uncertain.

## Change set under review
| Commit | Area | Nature |
|---|---|---|
| `a16bcfa` | Python API | `/qc/rules` implemented; malformed body → **400 not 500** |
| `4e5fcb8` | cross-stack | security hardening, perf tuning, audit/extraction analysis |
| `37b181b` | frontend | activate dead auth middleware (`proxy.ts → middleware.ts`) — **shared/core** |
| `c4f6678` | frontend | clear 21 ESLint errors/warnings |
| `ecce8ab` | frontend | extract verify-page logic, dedupe API base URL, route fetches through client |
| `e22c9fb` | Java | per-module unit tests 0→25 |
| `7756736` | Java/DB | batch status filter 500 fix (cast null `:search` to avoid bytea inference) |
| `5722507` | frontend | batch progress via WebSocket instead of 2s polling |
| `2454c16` | DB | `ddl-auto` env-driven |
| `e65239c`,`d6cc764` | cross-stack | engine blocking signal → **BLOCKED** decision |
| `25bb119`,`75a476b` | Python | field_validators/layer_b tests; narrowed exception swallows |
| `efcbd77`,`39fdaca` | Python/Java | Groq response cache; DRY multipart body |

> **Blast-radius callout:** `37b181b` (auth middleware) and the `BLOCKED` decision
> (`e65239c`/`d6cc764`) touch **shared/core** code. Auth middleware gates *every* route;
> the QCDecision enum widening flows through Python DTO → Java mapping → frontend union types.
> Treat both as wider than their commit message suggests.

---

## Core flows
| Journey touched by this change | Status | Evidence | Risk if skipped | Recommended test |
|---|---|---|---|---|
| Admin login → batch upload → Run QC → assign reviewer | Partial | `brain/src/runners/demo-e2e.spec.ts` (UI E2E exists) but not run against live stack post-change | High | Run demo-e2e on a live UAT stack; assert batch reaches REVIEW with rows persisted |
| Reviewer queue → verify page → pass/fail → submit | Partial | verify-page logic now in `frontend/lib/reviewVerify.ts` + `reviewVerify.test.ts` (unit only) | High | Component/E2E render of verify page incl. BLOCKED status badge |
| Auth gate on protected routes (middleware activated) | Partial | `frontend/middleware.ts` activated; no middleware test found | High | Test: unauthenticated → redirect to login; reviewer → 403 on admin route |
| QC decision rollup incl. new BLOCKED | Covered | `app/src/test/java/com/shal/RerunGuardIntegrationTests.java`, `ocr-service/tests/test_blocking_signal.py` | Med | (covered) add frontend assertion BLOCKED renders "Blocked" |
| Batch progress over WebSocket | Missing | `5722507` swapped polling→WS; no WS test found | Med | Test: WS message triggers queue refresh; fallback if WS drops |

## Previously fixed bugs
| Prior bug in touched module | Status | Evidence | Risk if skipped | Recommended test |
|---|---|---|---|---|
| Batch status filter 500 (bytea inference on null `:search`) | **Covered** | `app/.../BatchSearchRepositoryTests` (4) — added in the fix commit `7756736` (status-only/search-only/combined "does not throw") + now a row-correctness case (COMPLETED filter returns the completed batch, excludes the pending one), real Postgres | High | (covered) |
| Malformed request body → 500 (now 400) | **Covered** | `a16bcfa` is a **Java** `GlobalApiExceptionHandler` fix (`HttpMessageNotReadableException`/`MethodArgumentNotValidException`→400), not Python. `app/.../GlobalApiExceptionHandlerTest` (5 cases) pins 400 on malformed/illegal body, 409 on optimistic-lock, 500 generic without leaking the raw message | Low | (covered) |
| Date parse silent bug (MM/DD/YYYY vs ISO) | Covered | rule/extractor tests in `test_subject_contract_rules.py`, `test_recon_addendum_sig_rules.py` | Low | (covered) |
| Rerun creating duplicates instead of superseding | Covered | `RerunGuardIntegrationTests.java` | Med | (covered) |

## Integration points
| Integration touched | Status | Evidence | Risk if skipped | Recommended test |
|---|---|---|---|---|
| Java → Python `/qc/process` multipart | Partial | DTO shape: `PythonQCResponseTest`, `PythonRuleResultTest`; multipart build DRY'd (`39fdaca`) — no live round-trip test | High | WireMock/live integration test of `processQC` happy + 4xx/5xx/timeout paths |
| Java → Python `/qc/rules` (new) | Missing | `a16bcfa` added it; `getRules()` in `PythonClientService` has no test | Med | Test `getRules()` parses live `/qc/rules` payload |
| Java → Python retry/timeout/409-dedup | Missing | full retry loop in `PythonClientService`; **no test** exercises retry/backoff/409 | High | Unit test with mocked RestTemplate: 5xx→retry, 409→poll job, timeout→clean error |
| Redis (Groq cache) | Partial | `test_llm_cache.py` (in-process LRU + Redis path) | Low | (mostly covered) add Redis-down fallback assertion |
| Postgres status-filter query | **Covered** | `BatchSearchRepositoryTests` exercises `searchAdminBatches` against real Postgres | High | (covered) |
| WebSocket batch progress topic | Missing | no test | Med | Subscribe to `/topic/qc/batch/{id}/progress`, assert payload shape |

## Boundary conditions
| Edge case previously handled | Status | Evidence | Risk if skipped | Recommended test |
|---|---|---|---|---|
| Empty/corrupt PDF | Partial | now 400 (`a16bcfa`); assert in test | High | Upload 0-byte + corrupt PDF → 400, no stack trace leaked |
| Missing engagement / contract (N/A vs HOLD) | Covered | G-0 gate + `engagement_status`; `test_blocking_signal.py`, `test_qc_engine.py` | Med | (covered) |
| Null `:search` in status filter | **Covered** | `BatchSearchRepositoryTests.statusFilterWithNullSearchDoesNotThrow` | High | (covered) |
| Value-parse exceptions narrowed (ValueError/TypeError) | Partial | `75a476b`; covered indirectly by rule tests | Med | Feed malformed numeric/date field → no crash, VERIFY not 500 |
| Concurrent reviewer edit (optimistic lock) | Missing | `@Version` on QCRuleResult; no concurrency test found | Med | Two-writer test → second gets optimistic-lock failure |

## Permissions & roles
| Check | Status | Evidence | Risk if skipped | Recommended test |
|---|---|---|---|---|
| Unaffected endpoints keep prior access rules | **Covered** | `app/.../security/ApiAuthorizationMatrixTest` (8) — full `@SpringBootTest` MockMvc over the real `/api/**` SecurityConfig chain | High | (covered) |
| Reviewer cannot reach admin routes | **Covered** | same — REVIEWER→403 on `/api/admin/**`, `/api/qc/process/**`, `/api/graph/**`; both roles on `/api/{reviewer,qc,analytics}/**`; anon→401/403; `/api/auth/**` public | High | (covered) |
| Expired/!invalid JWT handling | Partial | `JwtUtilsTest` (util level), not route level | Med | Expired token → redirect/401 at the middleware boundary |

## Old API responses
| Touched endpoint | Status | Evidence | Risk if skipped | Recommended test |
|---|---|---|---|---|
| `PythonQCResponse` schema (BLOCKED fields added) | Partial | `PythonQCResponseTest` covers shape; widening is additive (`blocking`, `blocking_rules`) | Med | Contract test: old consumer ignores new fields; no field removed/retyped |
| `/qc/rules` response (new) | Missing | new endpoint, no schema test | Med | Snapshot test of `/qc/rules` JSON shape |
| Batch list response after status-filter fix | Missing | none found | Med | Snapshot batch-list JSON before/after fix — fields unchanged |
| QCDecision enum (frontend union widened) | Partial | tsc-clean per commit notes; no render test for BLOCKED | Med | StatusBadge test renders all enum values incl. BLOCKED |

## Business rules
| Rule area in touched modules | Status | Evidence | Risk if skipped | Recommended test |
|---|---|---|---|---|
| Blocking (HOLD → BLOCKED decision) | Covered | `test_blocking_signal.py`, `RerunGuardIntegrationTests` | Med | (covered) |
| ~135 `@rule` engine rules fire under same inputs | Partial | `test_qc_engine.py`, `test_nsi_rules.py`, `test_subject_contract_rules.py`, `test_recon_addendum_sig_rules.py`, `test_field_validators.py`, `test_layer_b.py` (~340 tests total) | Med | Corpus snapshot test: rule status distribution stable run-to-run |
| Field validators (type-confusion suppression) | Covered | `test_field_validators.py` | Low | (covered) |
| Doc-type gating (1004D → SCA N/A) | Partial | logic present; confirm a test asserts SCA→N/A on update form | Med | Test 1004D fixture → SCA rules all NOT_APPLICABLE |

## Dependency / config changes
| Change | Status | Evidence | Risk if skipped | Recommended test |
|---|---|---|---|---|
| `ddl-auto` now `${JPA_DDL_AUTO:update}` | Partial | `2454c16`; default unchanged (dev safe). `validate` path needs a baselined schema | High | Boot under `JPA_DDL_AUTO=validate` against current schema → no drift error |
| Groq response cache (Redis + LRU) | Covered | `test_llm_cache.py` | Low | (covered) |
| WebSocket replaces polling | Missing | `5722507`; client behavior change | Med | Verify graceful degradation if WS unavailable |
| No library version bumps detected in range | n/a | — | — | re-check `pom.xml`/`package.json` diff before release |

---

## Top 5 regression risks (impact × likelihood)

1. **Auth middleware activation gates every route** (`37b181b`) — a single mistake locks out
   valid users or exposes a route. *Test:* full route × role matrix (anon/reviewer/admin →
   200/302/403), plus expired-JWT redirect. → **PARTIALLY COVERED:** `frontend/middleware.test.ts`
   (added 2026-06-22, 7 cases) pins public bypass / unauth→login / ADMIN allow / REVIEWER block
   on `/admin`+`/analytics` / REVIEWER allow. → **NOW COVERED** on the authoritative side too:
   `app/.../security/ApiAuthorizationMatrixTest` (8) drives the real `/api/**` SecurityConfig
   chain via MockMvc. Remaining gap: expired-JWT behavior at the filter boundary.
2. **Batch status-filter 500 fix** (`7756736`) → **COVERED:** `app/.../BatchSearchRepositoryTests`
   (4) — the fix commit shipped 3 "does-not-throw" cases (status-only/search-only/combined) and
   a row-correctness case was added (COMPLETED filter returns only COMPLETED rows), all against
   real Postgres. (The audit's original "no test found" was incorrect.)
3. **Java→Python retry/timeout/409-dedup** — the most failure-prone integration path.
   → **COVERED (2026-06-22):** `qc/.../PythonClientServiceTest` (8 cases) — happy path,
   empty body, 5xx→retry→success, 4xx no-retry, timeout-exhausted, 409→poll-job, `getRules()`
   ok + error. Mocked RestTemplates, no live Python needed.
4. **BLOCKED decision spans Python→Java→frontend with no end-to-end assertion** — enum
   widening that compiles but may mis-render or mis-route. *Test:* live E2E producing a HOLD
   rule → batch shows BLOCKED → StatusBadge renders "Blocked".
5. **`ddl-auto=validate` in UAT/prod against an un-baselined schema** — boot failure or
   silent drift. *Test:* CI step boots the app with `JPA_DDL_AUTO=validate` on a fresh
   `manage_db.py recreate`d + JPA-migrated DB.

---

### Coverage summary
- **Strong:** Python rule engine + field validators + blocking signal + Groq cache (~340 tests);
  DTO shape; rerun/supersede.
- **Weak / Missing:** route-level auth/role matrix, status-filter regression, Java→Python
  integration (retry/timeout/`/qc/rules`), WebSocket progress, live cross-stack E2E.
- **Do not assume "probably fine"** for the five risks above — each maps to a shared/core path
  changed in this range with no direct test.
