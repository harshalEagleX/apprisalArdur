# SHAL Appraisal QC — UAT Readiness Plan

Branch: `uat` (cut from `demo`, June 2026)
Owner: engineering
Purpose: take the product from "late dev on `demo`" to "handed off to a UAT team on a stable shared environment."

---

## 0. Status correction (read this first)

An earlier gap assessment was written from point-in-time memory notes (12–40 days old).
Several items it flagged as ❌/⚠️ are **already done** in current code on `demo`. Verified
against the working tree on 2026-06-22:

| Previously flagged | Real current state | Evidence |
|---|---|---|
| "31 rules" stale in CLAUDE.md | **No such text anywhere** in repo | `grep "31 rule"` → 0 hits |
| Dead files `outcome.py`, `nlp_checks.py` not deleted | **Already deleted** | files absent |
| Frontend "0 tests" | **vitest + 4 lib test suites** | `frontend/lib/*.test.ts`, `package.json` `test: vitest run` |
| Java "thin/no tests" | **25 tests across common/qc/user** | commit `e22c9fb`, 5 `*Test.java` |
| Timeout/retry for Python calls "not tested/implemented" | **Fully implemented** | `PythonClientService` retry loop, dual timeout RestTemplates, 409 dedup, Celery async fallback, backoff; `OcrServiceConfig` `retryAttempts=2`, `timeoutSeconds=180` |
| "No monitoring / external error capture" | **Micrometer + Prometheus + OTel tracing wired**; Grafana dashboard + alert rules | `app/pom.xml`, `prometheus/` dir |
| XF "ghost rules" not in `rules_config` | **Obsolete** — new `app/qc/` engine uses `@rule` decorators + `applies_when`, **not** the DB `rules_config` table (`grep rules_config ocr-service/**/*.py` → 0 hits) | belongs to deprecated 146-rule `qc_processor` |
| CA-1/CA-2 `applicable_loan_types='USDA'` DB seed bug | **Obsolete** — same reason; CA-1/CA-2 now live in `app/qc/rules/reconciliation.py` with code-level `applies_when` (FHA/USDA/VA) | `reconciliation.py:249,375` |

**Net:** the engine (~135 `@rule` across 14 files), the Java↔Python contract, BLOCKED
decision, WebSocket progress, retry/timeout, and a metrics/tracing stack are all in place.
What's genuinely missing is the **UAT logistics layer**: a shared environment, scripted
scenarios, a rollback plan, and a few hardening/observability finishes.

---

## 1. Done in this `uat` branch

- [x] **Admin credential de-hardcoded to `harshal@eaglexinfo.com`** across the active
      login defaults: `app/src/main/resources/application.yml` (`ADMIN_EMAIL` default,
      consumed by `AdminSeeder`), `brain/src/runners/demo-e2e.spec.ts`,
      `scripts/loadtest/test_all_apis.py` (now env-overridable via `LOGIN_USER`/`LOGIN_PASS`).
      `ADMIN_PASSWORD` remains env-overridable and `AdminSeeder.warnOnInsecureDefaults()`
      already escalates to ERROR under a prod profile if the default password/JWT is left in place.
- [x] `uat` branch created off `demo`.
- [x] **Shared UAT environment (Phase B) built** — `docker-compose.uat.yml` (postgres, redis,
      ocr-service, celery-worker, java-backend, frontend, prometheus, grafana), `docker/Dockerfile.{java,ocr,frontend}`,
      `docker/ocr-entrypoint.sh`, `.dockerignore`, `.env.uat.example`, `prometheus/prometheus.uat.yml`.
- [x] **One-command lifecycle (Phase B)** — `scripts/uat/up.sh` (build + health-gate),
      `down.sh` (`--wipe`), `reset-data.sh` (mirrors `reset_db.sh` inside compose).
- [x] **UAT Spring profile (Phase A)** — `application-uat.yml` (cookie-secure toggle, env-driven
      ddl-auto, actuator on internal mgmt port 9091).
- [x] **Rollback plan** — `readme/UAT_ROLLBACK.md` (release tagging, additive-schema rollback
      safety, snapshot/restore, `ddl-auto=validate` adoption, known caveats).

> Historical references to the old email in `readme/*.md` audit docs and
> `frontend/lib/displayName*.ts` (a display-formatting unit test fixture) are intentionally
> left as-is — they are not credentials.

---

## 2. Remaining gaps → phased plan

### Phase A — Config & data hygiene (hours)
- [ ] **Seed/reference data for UAT**: a deterministic `clients` + `users` (1 admin, 2
      reviewers) seed so testers don't start from an empty system. Extend `AdminSeeder` or
      add a `UatSeeder` gated behind `spring.profiles.active=uat`.
- [x] **Per-environment config profile** `application-uat.yml` + `.env.uat.example`: cookie-secure
      toggle, env-driven `JPA_DDL_AUTO`, secrets (`JWT_SECRET`/`ADMIN_PASSWORD`/`INTERNAL_API_KEY`/
      Groq keys) from env, `OCR_SERVICE_URL` wired to the in-network ocr-service.
- [ ] Document the canonical UAT credentials in a secrets store (not in git) — `.env.uat` is
      git-ignored; populate it from your secrets manager.

### Phase B — Shared UAT environment — ✅ DONE (verify on a Docker host)
UAT assumes testers reach a stable environment independently. Delivered:
- [x] **`docker-compose.uat.yml`**: postgres, redis, ocr-service (uvicorn), celery-worker,
      java-backend (jar), frontend (next start), prometheus, grafana.
- [x] **One-command bring-up** `scripts/uat/up.sh` (build + health-gate on `/live`, java `:8080`, `:3000`).
- [x] **DB lifecycle** `scripts/uat/reset-data.sh` (DROP SCHEMA → ocr-service recreates Python
      tables via idempotent `manage_db.py create`; java-backend recreates Java tables via JPA).
- [x] **Rollback plan** `readme/UAT_ROLLBACK.md` (tagged releases, additive-schema safety,
      snapshot/restore, one-way hazards, `validate` adoption).
- [x] **No-Docker local runner (active path)** — `scripts/uat/run-local.sh` + `stop-local.sh`
      start each service natively on its port (java :8080, ocr :5001, celery, next :3000) against
      local Postgres + Redis, using a real detailed `.env.uat` (git-ignored, merged from `./.env`
      + `ocr-service/.env`). Activate the Python env first (`conda activate apprisal`).
- [x] **Live stack verified (2026-06-22):** Postgres ✓, Redis ✓; Python `/health` 200 (db
      connected, 134 rules via `/qc/rules` with API key, 401 without ✓); Java `/login` 302 +
      `/actuator/health` 200; frontend `/login` 200. The `uat` Spring profile boots clean on a
      spare port (Tomcat 8085 + mgmt 9095, `/actuator/health` 200, admin `harshal@eaglexinfo.com`
      seeded, no errors). Note: Celery worker was not running → Java sync fallback (P-6) active.
- [ ] Docker host (optional/later): `cp .env.uat.example .env.uat` → `bash scripts/uat/up.sh`.
      Reconcile the OCR Python-deps caveat (requirements.txt minimal vs conda extras) if a
      scanned-PDF test diverges.

### Phase C — Functional confidence: mass-VERIFY (the perception blocker) (days, measured)
A tester seeing most rules land VERIFY will conclude the system is broken. It isn't — VERIFY
is the extraction-gated fallback. Per the established working method (baseline → fix →
re-measure on corpus → unit test → commit; never soften a rule to hide an extraction gap):
- [ ] Run `ocr-service/scripts/run_qc_corpus.py` to get the **current** PASS/FAIL/VERIFY split
      (memory's "209/796" is stale — measure fresh).
- [ ] Rank VERIFY drivers by rule_id (prior top drivers: SCA-5 comp data source, N-1
      neighborhood checkboxes, R-2/ST-7/CA-1/N-5, SIG-2). Each is an **extraction** target,
      not a rule-leniency target.
- [ ] Close the never-extracted fields the engine needs: `effective_age`, `flood_zone`,
      `days_on_market`, reliable `gla`.
- [ ] Acceptance gate: VERIFY rate on the corpus down to a level where remaining VERIFYs are
      genuine "human should look" cases, not extraction misses. Re-measure and record the
      number in `TASK_HISTORY.txt`.

### Phase D — Test depth & end-to-end (1–2 days)
- [ ] **Live full-stack E2E**: bring up the stack, run `brain/src/runners/demo-e2e.spec.ts`
      against it; confirm `QCProcessingService` persists rows under the **new** rule_ids
      (S-1/SCA-5/N-6/FHA-2…) and the reviewer verify page groups all rules by section.
- [ ] **Java integration test** for `/qc/process` round-trip (WireMock the Python service or
      hit a live one) — currently only unit-level DTO/util tests exist.
- [ ] **Frontend**: extend beyond `lib/*` unit tests to the reviewer verify-page render
      (empty / loading / error states — see Phase E).

### Phase E — UI states & cross-browser (TODO, 0.5 day)
- [ ] Systematically verify empty / loading / error states on: reviewer queue, verify page,
      admin batches/users/clients/audit. Add component tests for each state.
- [ ] Cross-browser smoke (Chrome, Edge, Safari, Firefox) of the reviewer + admin flows.

### Phase F — Observability finish (analysis below) (0.5–1 day)
- [ ] **Error capture** (Sentry) — see §3.
- [ ] **PII-in-logs** audit + masking — see §4.

### Phase G — UAT artifacts (TODO, 0.5 day)
- [ ] `readme/UAT_TEST_SCENARIOS.md` — scripted scenarios for testers (see §5 starter set).
- [ ] Release notes (what's new / fixed / changed since last cut).
- [ ] Known-limitations sheet (deferred items, the corpus VERIFY caveats).
- [ ] UAT access pack (URL, credentials location, role matrix).

---

## 3. Error capture (Sentry) — analysis & recommendation

**Current:** Micrometer → Prometheus (metrics), OTel tracing bridge (`micrometer-tracing-bridge-otel`),
Grafana dashboard + `alert.rules.yml`. Structured `TimelineLog` events. **No exception
aggregator** — a stack trace today only lives in `java-backend.log` / `python-service.log`.

**Recommendation: add Sentry** (or self-hosted GlitchTip — Sentry-API compatible, no per-event cost,
fits the "single host" scalability decision). Minimal, low-risk wiring:

- **Java**: add `sentry-spring-boot-starter-jakarta`; configure `sentry.dsn` (env), `sentry.traces-sample-rate`
  low (e.g. 0.05) to avoid overhead, `sentry.environment=uat`. It hooks Logback `ERROR` automatically;
  no code changes beyond config. Reuse the existing OTel trace id for correlation.
- **Python (FastAPI)**: `sentry-sdk[fastapi]`, `sentry_sdk.init(dsn=..., traces_sample_rate=0.05,
  environment="uat")` in `main.py` before app creation. Captures unhandled exceptions in routes
  and Celery tasks (`CeleryIntegration`).
- **Cost/perf guardrails**: sample traces low; **scrub PII before send** via `before_send`
  (drop request bodies / file contents / extracted_fields). DSN from env only — never in git.
- **Gate it**: `SENTRY_ENABLED` flag; off by default in dev, on in `uat`/`prod`.

Effort: ~half a day, mostly config. Defer only if a shared UAT host with outbound network isn't ready.

---

## 4. PII in logs — optimized (performance-safe) approach

**Constraint (user):** must not hurt performance. So: **no regex scrubbing on the hot path.**

PII surface = borrower/owner names, property addresses, lender names, emails, parcel/loan numbers —
present in `extracted_fields`, rule `evidence`, and the Python multipart filenames.

Recommended, in cost order (cheapest first):
1. **Don't log it in the first place (free, fastest).** Audit log statements in the QC path; ensure
   `extracted_fields`, full `evidence` strings, and raw values are logged at `DEBUG` only, never
   `INFO`. `INFO`/timeline events should carry IDs (batch_id, file_hash, rule_id), not values.
   Pure removal — zero runtime cost.
2. **Mask at the sink, not per-statement.** Add one Logback masking converter (Java) / logging
   `Filter` (Python) that redacts known PII *keys* (`borrower`, `owner`, `address`, `email`,
   `lender_name`) when they appear in structured fields. Key-based, not content-regex → O(1) per field,
   negligible overhead, and only runs on records that actually reach an enabled appender.
3. **Keep production at `INFO`.** Masking/DEBUG paths never execute under normal load, so the
   performance cost in UAT/prod is ~zero.
4. **Sentry `before_send`** (from §3) is the second sink — scrub the same keys there.

Deliverable: `readme/PII_LOGGING_AUDIT.md` listing each log site that emits a value today + the
fix (downgrade to DEBUG or mask), plus the one masking converter per service.

---

## 5. UAT test scenarios — starter set (to expand in `UAT_TEST_SCENARIOS.md`)

1. **Happy-path purchase**: upload appraisal + engagement + TREC contract → Run QC → all
   sections render → reviewer passes/fails findings → submit → rejection language renders + "Copy all".
2. **Refinance (no contract)**: contract absent → contract-dependent rules go N/A (not FAIL),
   G-0 gate behaves, no false HOLD.
3. **FHA overlay**: engagement letter = FHA → FHA-specific rules (and CA-2 economic-life) fire;
   non-FHA rules stay N/A.
4. **1004D update / completion report**: no SCA grid → all SCA rules collapse to one N/A row
   (doc-type gating), not 35 false VERIFYs.
5. **Missing engagement letter**: `engagement_status` drives HOLD vs N/A correctly (BLOCKED decision).
6. **Reviewer override flow**: reviewer requests override → admin approves → audit log entry.
7. **Rerun / supersede**: re-run QC on the same batch_file → prior result superseded, not duplicated.
8. **Malformed input**: corrupt/empty PDF → Python returns 400 (not 500), Java surfaces a clean error.
9. **Role enforcement**: reviewer cannot reach admin routes; expired JWT redirects to login.
10. **Concurrency**: two reviewers open the same file → review-session lock prevents double edit.

---

## 6. Go / No-Go gate (target for handoff)

| Check | Now | Target |
|---|---|---|
| Zero P1/P2 open bugs | ⚠️ measure corpus VERIFY; live E2E unverified | ✅ |
| Integration tests green | Python ✅ / Java unit ✅(25) / live E2E ❌ | ✅ all |
| UAT environment stable | ❌ none | ✅ compose + one-command up |
| Test scenarios shared | ❌ | ✅ `UAT_TEST_SCENARIOS.md` |
| Rollback plan exists | ❌ | ✅ `UAT_ROLLBACK.md` |
| Error capture | ⚠️ metrics/traces only | ✅ Sentry/GlitchTip gated |
| PII not in INFO logs | ⚠️ unaudited | ✅ audited + masked at sink |

**Critical path to "UAT ready": Phase A → B → (D live E2E) → G.** Phases C/E/F raise quality
and should land before sign-off but don't block testers from starting.
