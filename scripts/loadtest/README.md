# Load-test harness — Scaling Phase 6

These are the tests that **prove** the targets in `readme/SCALABILITY_PLAN.md` §1. They are
the operational gates for Phases 1–4 (every mechanism is already verified in isolation; these
confirm it under real load on the full running stack).

## Prerequisites (the full stack up)

```bash
# 1. Redis (broker + result backend + distributed Groq limiter + idempotency)
redis-server            # or: brew services start redis   (redis-cli ping -> PONG)

# 2. Postgres up, schema present, ideally seeded to ~5,000 docs (see "Seeding" below)

# 3. Python OCR/QC API + at least one Celery worker (the durable queue)
cd ocr-service
conda run -n shal python -m uvicorn main:app --host 0.0.0.0 --port 5001 &
conda run -n shal celery -A celery_app.celery_app worker \
    --concurrency=6 --prefetch-multiplier=1 --loglevel=info &

# 4. Java backend (reads qc.executor.* / Hikari from application.yml)
./mvnw -pl app spring-boot:run &
```

## T-1 / T-4 — 50 concurrent users, read latency  (`read_50vu.js`, needs [k6](https://k6.io))

```bash
BASE_URL=http://localhost:8080 \
LOGIN_USER=dhoteharshal16@gmail.com LOGIN_PASS='Admin123!' \
k6 run scripts/loadtest/read_50vu.js
```
**Pass:** `http_req_failed rate<0.01` and `http_req_duration p(95)<400`. Record the p95s into
plan §9. Cache hit-rate is visible at `/actuator/metrics/cache.gets` while it runs.
Auth note: assumes `/api/auth/authenticate` returns a JWT in the body; if your build is
cookie-only, the per-VU cookie jar still carries the session.

## T-3 — 250+ docs/day processing soak  (`process_soak.py`)

```bash
OCR_URL=http://127.0.0.1:5001 INTERNAL_API_KEY=$INTERNAL_API_KEY \
python scripts/loadtest/process_soak.py --corpus uploads/ --count 250 --inflight 6
```
**Pass:** `LOST = 0` and `docs/day` projection ≥ 250 with margin. Exits non-zero if any job is
lost (usable as a CI/soak gate). Record docs/min + per-doc p50/p95 into plan §9, then
**re-assess Risk R-1** (Groq tier) from the measured throttle-bound throughput.

## T-3 — no-job-lost-on-restart (manual)

Start the soak above, and mid-run kill + restart the Celery worker (and separately the Java
app). With `acks_late` + `task_reject_on_worker_lost`, in-flight jobs requeue; the soak should
still finish with `LOST = 0`.

## Seeding ~5,000 docs (for T-2 / read latency at scale)

The read endpoints need data to page through. Two options:
- **Realistic:** run `process_soak.py --count 5000` through the real pipeline (slow but exact).
- **Fast (read-path only):** bulk-insert synthetic `qc_result` / `qc_rule_result` rows via SQL.
  Generate against the live JPA schema (column sets are owned by Hibernate) — keep it in a
  throwaway DB, never the production one.
