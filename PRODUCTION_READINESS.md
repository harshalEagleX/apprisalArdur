# Production Readiness — Go-Live Runbook

Status of the order-keyed QC work: **code-complete, tested, and pushed to `origin/demo`.**
Java test suite is green (107 tests); the frontend `next build` passes; end-to-end order
QC (single + concurrent) is verified on a single node.

This runbook covers the three things that are **not** code changes and therefore could not be
closed from a dev machine: **(1) ship `demo` → `main`**, **(2) verify multi-instance / cluster
behavior**, and **(3) load-test**. It complements [`DEPLOYMENT.md`](./DEPLOYMENT.md) (env vars,
secrets, preflight) — do not duplicate that; do the checklist at the end here.

---

## 1. Ship `demo` → `main` (PR + CI)

The default branch is `main`; all work is on `demo`. **There is no CI yet** (`.github/workflows/`
does not exist), so step 1a is to add it — otherwise "PR + CI" is just a manual merge with no gate.

### 1a. Add a CI workflow (one-time)
Create `.github/workflows/ci.yml` so every PR runs the same checks we ran by hand:

```yaml
name: CI
on:
  pull_request:
    branches: [main]
  push:
    branches: [demo, main]
jobs:
  java:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env: { POSTGRES_USER: shal, POSTGRES_PASSWORD: shal, POSTGRES_DB: shal_qc }
        ports: ["5432:5432"]
        options: >-
          --health-cmd pg_isready --health-interval 10s --health-timeout 5s --health-retries 5
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with: { distribution: temurin, java-version: "21", cache: maven }
      - run: mvn -B test           # 107 tests; integration tests need the Postgres service above
  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "20", cache: npm, cache-dependency-path: frontend/package-lock.json }
      - run: npm ci
        working-directory: frontend
      - run: npm run build
        working-directory: frontend
```

> Note: some `@SpringBootTest` integration tests hit Postgres (and a few reference the OCR service).
> The Postgres service above covers the DB. Tests that need the Python OCR service are already
> written to mock `PythonClientService`, so no OCR container is required for `mvn test`.

### 1b. Open the PR and merge
```bash
# from the repo root, on demo, in sync with origin/demo
gh pr create --base main --head demo \
  --title "Order-keyed QC: Order is the QC unit (Phases 1–5) + dead-code cleanup + fixes" \
  --body-file PR_BODY.md            # see the summary block below

# wait for CI to go green, get a review, then:
gh pr merge --squash --delete-branch=false   # keep demo; do NOT auto-delete
git checkout main && git pull                 # main now has the work
git tag -a v-order-keyed-qc -m "Order-keyed QC go-live" && git push origin --tags
```

**PR summary (paste into `PR_BODY.md`):** Order (`AppraisalTransaction`) is the sole QC unit;
batch-grain QC removed (endpoints 404, batch = upload-only); order-keyed engine + live order
progress/WS/cancel + order reconciler; reviewer queue and reviewer assignment are order-wise;
dead Java + Python code removed; stale-`INCOMPLETE` order-status bug fixed. Java suite green (107),
`next build` passes.

### 1c. Do NOT merge if
- CI is red, or
- the deploy target hasn't set the production secrets (see the checklist at the bottom — the app
  **refuses to start** in strict/prod mode with default `ADMIN_PASSWORD` / `JWT_SECRET` /
  `COOKIE_SECURE=false`, by design in `ProductionReadinessValidator`).

---

## 2. Multi-instance / cluster verification

Only single-node was exercised. Two things must be verified — and one **must be hardened** —
before running more than one Java instance.

### 2a. ⚠ Hardening required: make the order claim atomic across nodes
The batch path claimed work with a **conditional UPDATE** (`BatchRepository.markQcProcessingIfTriggerable`
— one node's UPDATE wins, returns rows-affected). The order path's claim
(`OrderStatusService.markProcessing`) is a **read-then-write**:

```java
if (order.getDocumentStatus() == QC_PROCESSING) return false;   // read
order.setDocumentStatus(QC_PROCESSING); save(order);            // write  ← not atomic
```

On a single node the in-memory `activeOrders` set is the real guard, so this is safe today.
Across nodes, two instances can both read a non-processing status and both claim the same order
(double QC run). **Before going multi-instance, convert `markProcessing` to a conditional UPDATE**,
mirroring the batch path:

```java
// AppraisalTransactionRepository
@Modifying
@Query("""
  UPDATE AppraisalTransaction t SET t.documentStatus = com.shal.common.entity.OrderDocumentStatus.QC_PROCESSING,
         t.updatedAt = :now
  WHERE t.id = :id AND t.documentStatus <> com.shal.common.entity.OrderDocumentStatus.QC_PROCESSING
  """)
int claimForQcIfNotProcessing(@Param("id") Long id, @Param("now") LocalDateTime now);
```

`claimOrderForProcessing` then treats `rows == 1` as "won the claim" (like the batch code). This is
a small, well-scoped change; add a test alongside `RerunGuardIntegrationTests`.

### 2b. Verify cross-node cancel (Redis)
Cross-node cancel already works by design: `RedisClusterCoordinator` broadcasts cancel via Redis,
and cancel keys are namespaced (`order:{id}` / `batch:{id}`) so a same-numbered batch/order can't
collide. Verify it live:

1. Stand up **two** Java instances (A, B) behind a load balancer, both pointing at the **same
   Redis** (`SPRING_DATA_REDIS_*`) and Postgres.
2. Trigger `POST /api/qc/process/order/{id}` and confirm (via logs) the worker runs on **node A**.
3. Call `POST /api/qc/cancel/order/{id}` routed to **node B**.
4. **Expected:** node A's worker stops (interrupt + `clusterCoordinator.isCancelSignalled("order:"+id)`),
   the order falls back to its pre-run status, and no result is persisted from the cancelled run.
5. Repeat with Redis **down** — cancel must degrade gracefully to node-local only (no crash); the
   `RedisClusterCoordinator` local-fallback path covers this.

### 2c. Verify the stuck-order reconciler under multi-node
`StuckBatchReconciler` runs on every instance (`@Scheduled`). Confirm two instances don't both
re-trigger the same stuck order: `isOrderActive` is per-node, so the atomic claim from 2a is what
prevents a double re-trigger. Force an order to `QC_PROCESSING` with no live worker and confirm
exactly one instance retries it.

---

## 3. Load testing

`locust` is already in `ocr-service/requirements.txt`. The **real throughput ceiling is the shared
Groq TPM budget** (`GROQ_TPM_LIMIT`, enforced by a Redis token bucket), **not** the Java pool — the
QC executor is I/O-bound (`core=4 / max=8 / queue=200` via `application.yml`; it submits to the OCR
service and polls).

### What to drive
- **Order QC throughput:** loop `POST /api/qc/process/order/{id}` (or `/process/orders` bulk) across
  a pool of complete orders, at increasing concurrency.
- **Reviewer read path:** `GET /api/reviewer/qc/results/pending` under concurrent reviewers.

### What to watch (must stay healthy)
| Signal | Where | Concern |
|---|---|---|
| QC executor saturation | `qc-worker-*` threads / queue depth | queue → 200 then `AbortPolicy` returns HTTP 503 |
| Groq TPM throttling | OCR service logs / Groq token-bucket waits | the actual ceiling — expect backpressure, not errors |
| Hikari DB pool | `DB_POOL_MAX` (default 30) | pool exhaustion = request timeouts |
| OCR service latency | `/qc/progress/{token}`, per-file timing | slow pages block workers |
| JVM + OCR memory | host metrics | OCR is off-process; watch the Python host, not the JVM |

### Success criteria (define the target first — P-8)
- Sustained target order-throughput with **p95 end-to-end latency within SLA** and **zero 5xx**
  below the target; graceful 503 (not errors) only above it.
- No OOM on the OCR host; no Hikari pool exhaustion; Groq throttling manifests as queueing, not failures.
- Tune `QC_EXECUTOR_*`, `DB_POOL_MAX`, and `GROQ_TPM_LIMIT` per the observed bottleneck — **measure
  before changing** (P-13).

---

## Pre-go-live checklist

- [ ] **CI added** (`.github/workflows/ci.yml`) and green on the PR.
- [ ] PR `demo` → `main` reviewed and merged; tag cut.
- [ ] **Order-claim hardened** to a conditional UPDATE (§2a) — required before >1 Java instance.
- [ ] Cross-node cancel verified with real Redis (§2b); graceful degradation with Redis down.
- [ ] Load test run against the target concurrency; bottleneck identified and tuned (§3).
- [ ] Production secrets set — `JWT_SECRET`, `ADMIN_PASSWORD`, `DB_PASSWORD`, `INTERNAL_API_KEY`
      unique/real; `COOKIE_SECURE=true` behind HTTPS; `preflight.sh --strict` green (see `DEPLOYMENT.md`).
- [ ] OCR service deps installed from the frozen `requirements.txt`; Groq creds + `GROQ_TPM_LIMIT` set.
- [ ] `spring.jpa.hibernate.ddl-auto=update` has applied the order-keying schema on a **staging** DB
      first (verify no destructive diff), per the project DB policy (JPA-managed, no migration runner).

---

*Companion docs: [`DEPLOYMENT.md`](./DEPLOYMENT.md) (env/secrets/preflight),
`readme/SCALABILITY_PLAN.md` (Celery/Redis scaling), `.claude` memory `project_order_keyed_qc`
(what changed and the known reviewer-queue history).*
