# Production Deployment — Gap Analysis (Python SHALqc + Java)

What a fully-deployed production app *should* have that this codebase is **missing today**.
Scope: the SHALqc Python QC service and the Java backend (+ their integration and the reviewer
frontend). Each gap has a **severity**, the **evidence** (file), and **what "done" looks like**.

Severity: **BLOCKER** (prod will misbehave / not be SHALqc at all) · **HIGH** (real risk: security,
data, silent wrong results) · **MEDIUM** (operability / correctness edge) · **LOW** (polish / debt).

> This is a *gap list*, not a to-do to run now. It complements the (now partly stale)
> `PRODUCTION_READINESS.md`.

---

## Resolution status (2026-07-16) — code gaps FIXED

Product-level fixes landed this round (183 Python tests + full Java build green):

| Gap                                   | Status                | What changed                                                                                                                                                                                                                                       |
| ------------------------------------- | --------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **P1** bundle draft             | ✅ fixed              | Bundle`--approve`d → `active`; `require_signed_bundle` now defaults to `is_production` ([config.py]).                                                                                                                                     |
| **P2** judge_mode=legacy        | ✅ fixed              | Default flipped to`language` (the product); `production_problems()` asserts it.                                                                                                                                                                |
| **P3** auth fail-open           | ✅ fixed              | One`is_production` switch; startup **fail-closed** in prod, warn in dev (`main._validate_startup`).                                                                                                                                      |
| **P4** no observability         | ✅ fixed              | New`app/observability.py` — Prometheus `/metrics` (http + LLM + per-order), wired via a DRY `_record` choke point + one middleware.                                                                                                         |
| **P5** no tests                 | ✅ fixed              | `tests/test_production/test_production_gaps.py` (12) + Java `OrderStatusServiceMarkProcessingTest` (3).                                                                                                                                        |
| **P8** gap noise                | ✅ fixed              | `_extraction_gap` now flags an engine gap only when the **XML** carried the value (aligns with the documented S-1 intent).                                                                                                                 |
| **J1** non-atomic claim         | ✅ fixed              | `claimForQcIfNotProcessing` conditional UPDATE; `markProcessing` is now atomic (no read-then-write).                                                                                                                                           |
| **J2** no CI                    | ✅ fixed              | `.github/workflows/ci.yml` — Java + Python + frontend gates.                                                                                                                                                                                    |
| **J6** stale/missing docs       | ✅ fixed              | `DEPLOYMENT.md` written; `PRODUCTION_READINESS.md` banner-corrected.                                                                                                                                                                           |
| **J4** loan_program passthrough | ✅ resolved-by-design | Java has no loan-program field; the**Python engagement extraction** already supplies it (ESTX→FHA, ESCA→Conventional). A Java passthrough needs loan data to enter the Java domain first (LOS/order-form) — new plumbing, not a code gap. |

**Genuinely NOT code — remain product/ops decisions (unchanged):** P6 judge-determinism SLA · P7 second-AMC onboarding · P9 cost governance · P10 DB migration procedure · J3 reviewer third action (UX decision) · J5 enabling AUTO_PASS · plus the ops verifications (multi-node cancel/reconciler live check, load test). The rows below are kept for the full record.

---

## 0. Executive summary

**Solid already:** deterministic extraction + XML-authoritative fusion; the language judge with a
single generic doctrine; the severity gate; Java's fail-closed secret validator
(`ProductionReadinessValidator`); Java observability (actuator + micrometer-prometheus + OTel);
Celery async path with sync fallback; safe-zip handling; 171 Python tests + green Java suite.

**The five that actually block a clean go-live:**

1. The runtime AMC bundle is **`draft`**, and `QC_REQUIRE_SIGNED_BUNDLE` defaults **false** → prod
   silently runs an **unapproved** checklist "degraded".
2. `JUDGE_MODE` defaults to **`legacy`** → without setting it, prod runs the *old rule engine*, not SHALqc.
3. Python API auth is **fail-open** (disables itself if the key is unset) — opposite of Java's fail-closed.
4. Multi-node order claim is **not atomic** (double QC runs across instances).
5. **No CI** and **no tests** for any of the recent gap-fixes → regressions ship silently.

---

## 1. Python (SHALqc) gaps

| #   | Sev               | Gap                                                                                                                                                                                                                                                                                             | Evidence                                                                                                              | Done =                                                                                                                                                                      |
| --- | ----------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| P1  | **BLOCKER** | Compiled bundle`EQUITYSOLUTIONS/3f9eafa82a7849f2.yaml` is **`status: draft`**, and `require_signed_bundle` defaults **false**, so `_run_language` runs it with only a log warning ("running an unsigned bundle (degraded)").                                                | `compiled/…/3f9eafa82a7849f2.yaml` (`status: draft`); `app/config.py:70`; `app/pipeline/orchestrator.py:214` | `compile_amc.py EQUITYSOLUTIONS --approve --by <you>` → `active`, **and** `QC_REQUIRE_SIGNED_BUNDLE=true` so an unsigned bundle hard-stops instead of running. |
| P2  | **BLOCKER** | `judge_mode` default is **`legacy`** — the SHALqc language judge only runs when `JUDGE_MODE=language`. A prod box without that env var runs the retired rule engine.                                                                                                               | `app/config.py:64`                                                                                                  | `JUDGE_MODE=language` set in the deploy env (and asserted at startup).                                                                                                    |
| P3  | **HIGH**    | API-key auth is**fail-open**: the `X-API-Key` middleware *disables itself* with a warning when `INTERNAL_API_KEY` is unset. Anyone who can reach `/qc/process` can run (and bill) the LLM.                                                                                        | `app/main.py:34-46`                                                                                                 | Fail-**closed** in prod (mirror Java's `ProductionReadinessValidator`: refuse to start if the key is unset under a prod profile).                                   |
| P4  | **HIGH**    | **No observability**: no `/metrics`, no tracing, no structured request logging on the Python service. Java has actuator+prometheus+OTel; the QC service that does the real work has nothing → throughput, p95 latency, error rate, and **LLM token/cost** are invisible in prod. | (absence)`app/main.py`, `app/api/health.py` (only `/live`, `/health`)                                         | prometheus-fastapi-instrumentator (or equivalent) + request/latency/LLM-call counters; per-order LLM cost metric.                                                           |
| P5  | **HIGH**    | **No automated tests** for any recent gap-fix: WO/WU basement extraction, the `loan_program`/`fha_case_number` gate, `auto_pass_enabled`, `rejectable_satisfied_low_conf`. All verified by hand only → silent regressions.                                                       | `grep` of `tests/` finds none                                                                                     | Unit tests: engagement`loan_program` → EQ-93/113/114/115 NA-vs-judge; basement extraction on ESNV/ESCA/ESTX; the confidence-floor count; the summary flag surfacing.     |
| P6  | MEDIUM            | **Judge non-determinism** (~5 verdict flips on identical packets, documented). Mitigated only by `auto_pass_enabled=false` (everything → TO_VERIFY), which means AUTO_PASS is effectively unreachable → 100% manual-review load.                                                      | memory`project_verify_paydown`; `tools/replay_harness.py` exists but isn't a gate                                 | A self-consistency / caching-by-packet-hash strategy, or a determinism SLA measured via the replay harness before enabling AUTO_PASS.                                       |
| P7  | MEDIUM            | **Single hard-wired AMC**: `amc_code → yml` selection and the one `EQUITYSOLUTIONS` bundle are pinned (intentional for now). Onboarding a 2nd AMC has never been exercised end-to-end; profile/wording/base are still separate per-AMC files.                                        | `compiler.py` (bundle by hash), `config/amc_profiles/`                                                            | The compile→validate→approve flow run for a second real AMC; the "dynamic AMC" path proven.                                                                               |
| P8  | MEDIUM            | **extraction-gap noise**: absent basement/fireplace labels (e.g. `basement_outside_entry`) surface as `source=engine` CANNOT_EVALUATE (Ops) on properties that legitimately have no basement — "NOT_PRESENT" is being reported as "engine failed to read".                           | full-run aggregate (top gap tags),`app/language/run.py` gap classification                                          | Distinguish "field absent because the feature doesn't exist" from "engine missed a value the XML has" so no-basement homes don't generate Ops gaps.                         |
| P9  | LOW               | **LLM cost governance** is coarse: `LLM_MAX_CALLS_PER_ORDER=28` + Together TPM budget, but no per-tenant budget, no spend alerting, no circuit-breaker on cost.                                                                                                                         | `app/config.py:58`                                                                                                  | Per-tenant/day budget + alert; kill-switch on runaway cost.                                                                                                                 |
| P10 | LOW               | **DB init has no migration/rollback story** (by policy: `Base.metadata.create_all`, no Alembic). A bad schema change on a live DB has no forward/rollback path.                                                                                                                         | `app/persistence/repo.py`; `CLAUDE.md` DB policy                                                                  | Documented, tested "apply on staging first" + backup/restore runbook (policy forbids a runner, so this is procedural).                                                      |

---

## 2. Java (backend) gaps

| #  | Sev                             | Gap                                                                                                                                                                                                                                                                                                               | Evidence                                                                                    | Done =                                                                                                                                                                                                     |
| -- | ------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| J1 | **BLOCKER** (for >1 node) | **Order claim is not atomic across nodes**: `OrderStatusService.markProcessing` is read-then-write; the in-memory `activeOrders` set is the only guard, so two instances can both claim the same order → **double QC run**.                                                                      | `PRODUCTION_READINESS.md §2a`; `OrderStatusService`                                    | Conditional`UPDATE … WHERE documentStatus <> QC_PROCESSING` (mirror `BatchRepository.markQcProcessingIfTriggerable`); treat `rows==1` as the winner. Test alongside `RerunGuardIntegrationTests`. |
| J2 | **HIGH**                  | **No CI**: `.github/workflows/` doesn't exist, so "PR + CI" is a manual merge with no gate — the 171 Python tests / green Java suite / `next build` run only by hand.                                                                                                                                  | `PRODUCTION_READINESS.md §1a`; no `.github/`                                           | A CI workflow running Java`mvn test` (with a Postgres service), Python `pytest`, and `next build` on every PR to `main`.                                                                           |
| J3 | MEDIUM                          | **Reviewer decision is binary PASS/FAIL** — no "escalate / return to Ops / request document" third action. A reviewer facing an undecidable card must *guess*, polluting the ground truth you'll want for measuring judge accuracy.                                                                      | `frontend/app/reviewer/verify/[id]/page.tsx` (only `PASS`/`FAIL` decisions, keys p/f) | A third reviewer action that routes to Ops / requests a document without forcing a PASS/FAIL.                                                                                                              |
| J4 | MEDIUM                          | **`loan_program` not sent to SHALqc**: `PythonClientService.buildShalqcBody` posts `amc_code` but not the ordered loan program, so the FHA/VA gate relies entirely on the **engagement-letter OCR** extracting it (works today, but no corroboration from the order Java already knows).        | `qc/src/main/java/com/shal/qc/service/PythonClientService.java:239` (amc_code only)       | Pass`loan_program` on `/qc/process` from Java order intake; Python prefers it, falls back to engagement extraction.                                                                                    |
| J5 | MEDIUM                          | **AUTO_PASS effectively disabled**: the safe default (`auto_pass_enabled=false`) + 17 constant visual REVIEW cards/order mean **every order is TO_VERIFY** — no order auto-completes, so reviewer load is 100%. The confidence-floor is built but never exercised because auto-pass never runs.    | `ShalqcResponseMapper.decisionFrom`; full-run (all 10 → TO_VERIFY)                       | A decision (product) on when to enable AUTO_PASS + a lighter review mode for visual-only orders; then validate the confidence-floor live.                                                                  |
| J6 | LOW                             | **Stale runbook**: `PRODUCTION_READINESS.md` still describes the **retired** `ocr-service`, **Groq**, `PythonClientService`→OCR flow, and "107 tests" — it predates the SHALqc rebuild. `DEPLOYMENT.md`, referenced as the source of env/secrets/preflight, **does not exist**. | `PRODUCTION_READINESS.md`; `DEPLOYMENT.md` missing                                      | Refresh the runbook to the SHALqc/Together topology; write the missing`DEPLOYMENT.md`.                                                                                                                   |

---

## 3. Cross-cutting / integration

| Sev            | Gap                                                                            | Note                                                                                                                                                                                         |
| -------------- | ------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **HIGH** | **No CI/CD pipeline, no load test executed, no multi-node run verified** | The three items`PRODUCTION_READINESS.md` itself says "could not be closed from a dev machine".                                                                                             |
| MEDIUM         | **Auth asymmetry**                                                       | Java is fail-closed on default secrets (`ProductionReadinessValidator`); Python is fail-open (P3). Standardize on fail-closed.                                                             |
| MEDIUM         | **Dual persistence**                                                     | Both Java (`QCResult`) and Python (`save_run` → `item_verdicts`/`llm_interactions`) store results. Confirm which is authoritative and that they can't diverge on a partial failure. |
| MEDIUM         | **DB schema evolution**                                                  | JPA`ddl-auto=update` (Java) + `create_all` (Python) share one DB; must be applied on **staging first**, no rollback runner by policy.                                              |
| LOW            | **Frontend e2e**                                                         | `next build` passes but there's no automated e2e for the reviewer flow (the "108" count fix, informational expansion, auto-scroll) — only manual.                                         |

---

## 4. Prioritized path to production

**Must fix before any prod traffic**

1. P1 — approve the bundle (`--approve`) + `QC_REQUIRE_SIGNED_BUNDLE=true`.
2. P2 — `JUDGE_MODE=language` in the deploy env.
3. P3 — Python auth fail-closed; set `INTERNAL_API_KEY`.
4. J2 — add CI (gate the merge).
5. P5 — tests for the new gap-fixes (WO/WU, loan_program gate, confidence-floor, 108 count).

**Must fix before >1 Java instance**
6. J1 — atomic order claim (conditional UPDATE).
7. Verify cross-node cancel + reconciler (readiness §2b/§2c).

**Before trusting the numbers / reducing reviewer load**
8. P4 — Python observability (metrics + LLM cost).
9. P6 — judge determinism SLA via the replay harness, *then* consider enabling AUTO_PASS (J5) with the confidence-floor.
10. J3 — reviewer third action (protect ground-truth quality).

**Debt / polish**
11. J4 loan_program passthrough · J6 refresh runbook + write `DEPLOYMENT.md` · P8 gap-noise · P9 cost governance · P7 second-AMC onboarding.

---

*Verified against the working tree on branch `demo` (2026-07-16). File references are `path:line`
where a single line anchors the gap.*
