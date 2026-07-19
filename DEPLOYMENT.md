# Deployment — Environment, Secrets, Preflight

The two runtime services and the config each needs to go live. Both fail **closed** in a
hardened deployment (Java `ProductionReadinessValidator`, Python `settings.production_problems()`),
so a missing secret stops the boot instead of silently running insecure.

Topology: **Java backend** (Spring Boot) ⇄ **SHALqc** (Python FastAPI QC service, Together AI
judge) sharing **one Postgres** (`shal_qc`) + **Redis**. There is no separate OCR service (retired).

---

## 1. SHALqc (Python) — `shalqc/.env`

| Var | Required | Purpose |
|---|---|---|
| `APP_DEPLOY_STRICT` | prod | `true` → fail-closed posture (or set `APP_ENV=prod`). |
| `INTERNAL_API_KEY` | **prod** | X-API-Key shared with Java. Unset under strict posture → **app refuses to start**. |
| `JUDGE_MODE` | no | Defaults to `language` (the product). Only set to `legacy` for debugging. |
| `QC_REQUIRE_SIGNED_BUNDLE` | no | Defaults to `true` in prod → only an `active` (approved) AMC bundle can run. |
| `TOGETHER_API_KEY_1` / `_2` | **yes** | The judge provider keys. None → the judge can't run (fail-closed in prod). |
| `TOGETHER_MODEL` | no | Defaults `openai/gpt-oss-120b`. |
| `TOGETHER_TPM_BUDGET_PER_KEY` | tune | Per-key token/min budget (TogetherPool governor). Set from your tier. Setting it too LOW starves the judge: batches that can't get budget become REVIEW `llm_unavailable` cards. |
| `TOGETHER_MAX_INFLIGHT_PER_KEY` | tune | Default 2. Concurrency is `keys × this`; the judge sizes its worker lanes from it. |
| `TOGETHER_TIMEOUT_S` | no | Default 120 — a per-call **floor**; the client scales the real budget by the tokens requested. Was 45, which clipped the latency tail and lost whole batches. |
| `SHALQC_POOL_ACQUIRE_TIMEOUT_S` | no | Default 90 — how long a batch may queue for local token budget. A full order legitimately queues ~70s. |
| `DATABASE_URL` | yes | Postgres (`shal_qc`) — Python-owned tables. |
| `REDIS_URL` / `REDIS_LLM_CACHE_URL` | rec | LLM response cache + async Celery. Absent → file-cache + sync fallback. |
| `LLM_MAX_CALLS_PER_ORDER` | no | Default 28 — cost guard per order. |
| `LOG_LEVEL` | no | Default INFO. |

**Bundle sign-off (one-time per AMC checklist version):**
```bash
cd shalqc
PYTHONPATH=. python tools/compile_amc.py EQUITYSOLUTIONS            # compile + validate
PYTHONPATH=. python tools/compile_amc.py EQUITYSOLUTIONS --approve --by <you>   # → status: active
```
Under `QC_REQUIRE_SIGNED_BUNDLE=true` a non-`active` bundle hard-stops (never runs degraded).

**Observability:** Prometheus metrics at `GET /metrics` (`shalqc_http_*`, `shalqc_llm_*`,
`shalqc_qc_orders_total`). Liveness `GET /live`, readiness `GET /health`. All three are open
(no API key) for scrapers/load balancers.

---

## 2. Java backend — env / `application.yml`

The `ProductionReadinessValidator` refuses to start under a `prod` profile or
`APP_DEPLOY_STRICT=true` if any of these still carry the built-in dev defaults:

| Var | Purpose |
|---|---|
| `JWT_SECRET` | Token signing — unique/real (default is a token-forgery risk). |
| `ADMIN_PASSWORD` | Admin login — strong. |
| `DB_PASSWORD` | Postgres — real. |
| `COOKIE_SECURE` | `true` behind HTTPS. |
| `INTERNAL_API_KEY` | Must equal SHALqc's — sent as X-API-Key on `/qc/process`. |
| `SPRING_DATA_REDIS_*` | Redis for cross-node cancel/coordination (multi-instance). |
| `DB_POOL_MAX` | Hikari max (default 30) — tune to load. |

**Observability:** actuator + micrometer-prometheus at `/actuator/prometheus`, OTel tracing.

---

## 3. Preflight checklist

- [ ] SHALqc: `APP_DEPLOY_STRICT=true`, `INTERNAL_API_KEY` + `TOGETHER_API_KEY_*` set; boot succeeds (fail-closed passes).
- [ ] SHALqc: AMC bundle `--approve`d to `active`; `QC_REQUIRE_SIGNED_BUNDLE` on.
- [ ] Java: `JWT_SECRET` / `ADMIN_PASSWORD` / `DB_PASSWORD` unique; `COOKIE_SECURE=true`; same `INTERNAL_API_KEY` as SHALqc.
- [ ] One `shal_qc` Postgres reachable by both; `ddl-auto=update` applied on **staging** first (no destructive diff) — JPA-managed, no migration runner (project DB policy).
- [ ] Redis reachable by both (LLM cache + cross-node coordination).
- [ ] `/metrics` (Python) and `/actuator/prometheus` (Java) scraped; dashboards/alerts wired.
- [ ] **Before >1 Java instance:** order claim is atomic (`claimForQcIfNotProcessing`) ✅ done; verify cross-node cancel + reconciler live (see `PRODUCTION_READINESS.md §2`).
- [ ] Load test to the target concurrency; tune `TOGETHER_TPM_BUDGET_PER_KEY`, `DB_POOL_MAX`.

See `PRODUCTION_GAPS.md` for the full gap ledger and which items remain product/ops decisions.
