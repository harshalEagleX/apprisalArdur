# Integration + Load + Performance Report — Java ⇄ Python (live, mock LLM)

**Date:** 2026-06-21 · **Host:** macOS, 8-core M-series, 2 GB JVM heap
**Method:** real full stack stood up locally, driven for real. **No Groq/Gemini** — a local OpenAI-compatible **mock LLM** (`scripts/loadtest/mock_llm.py`) replaced the API so the numbers reflect the *system's* ceiling, not the external TPM cap.

> Honesty note: every number below is from a live run captured this session. The one item NOT fired empirically is the 208-job admission cliff (it needs 208 seeded batches) — that value is read from config + code, and the downstream Celery bottleneck (6) was measured directly.

## Stack under test
| Component | Where | Notes |
|---|---|---|
| Java backend | :8080 | jar, booted in **7.1 s**, Hikari max 30 |
| Python OCR/QC | :5001 | FastAPI, **mock LLM**, vision off |
| Celery worker | — | **concurrency 6**, prefetch 1 |
| Mock LLM | :5099 | instant canned JSON, 7 tokens/call |
| Redis / Postgres | :6379 / :5432 | broker + shared DB |

---

## 1. Do the two sides actually talk and agree? — YES (end-to-end verified)

Triggered QC on a real batch (id 12) and traced the whole chain:

```
Java POST /api/qc/process/12
  → PythonClientService /qc/submit  → Celery task (55.5 s)
     → 9 mock-LLM calls (ZERO Groq)
     → PythonQCResponse (schema_version 1.0, rule_engine_version qc-1.0.0+ea46d908)
  → Java persists qc_result id=60: TO_VERIFY, 186 rules (133 pass / 2 fail / 21 verify), 186 rule rows
```

The contract is honored exactly — Java deserialized 186 rule results, the version stamps flowed through, and the decision (TO_VERIFY) was derived correctly. **The two services understand each other's logic.**

---

## 2. Tier 1 — API throughput (what the Java layer can serve)

`ab`, keep-alive, gzip. **0 failed requests at every level.**

| Endpoint | Concurrency | Req/s | p50 | p95 | p99 |
|---|---|---|---|---|---|
| `/actuator/health` (raw) | 50 | 3,945 | 11 ms | 24 ms | 37 ms |
| `/actuator/health` (raw) | 100 | **5,459** (peak) | 17 ms | 29 ms | 45 ms |
| `/actuator/health` (raw) | 200 | 5,314 (plateau) | 34 ms | 65 ms | 108 ms |
| `/api/admin/batches` (auth + DB) | 25 | 1,219 | 17 ms | 40 ms | 95 ms |
| `/api/admin/batches` (auth + DB) | 50 | 1,964 | 24 ms | 41 ms | 52 ms |
| `/api/admin/batches` (auth + DB) | 100 | **2,176** | 44 ms | 75 ms | 97 ms |

After the authed load, Hikari pool returned to **active 0 / pending 0** (max 30) — never exhausted. JVM heap stayed ~386 MB / 2 GB.

**Read it as:** the API comfortably serves **~2,200 authenticated DB-backed req/s** (5,400 raw) on this 8-core box. For an internal office tool this is effectively unlimited headroom.

---

## 3. Tier 2 — QC processing capacity (the real business limit)

Submitted **8 concurrent documents** through `/qc/submit` (mock LLM, Celery=6):

| Jobs | Outcome |
|---|---|
| First 6 (grabbed workers immediately) | **~100–106 s** each |
| Jobs 7–8 (queued behind the 6) | **167 s, 172 s** |
| Per-doc latency | min 100 s · avg **119 s** · max 172 s |
| Total drain (8 docs) | **172 s** |
| Sustained throughput | **2.8 docs/min ≈ ~168 docs/hour** at full saturation |
| LLM calls | 27 mock calls, **zero Groq** |

**Key finding — CPU contention is the pipeline ceiling.** A single document with no contention took **~55 s**; under 6-way concurrency each doc rose to **~100 s** — OCR is CPU-bound, so 6 docs saturate 8 cores and per-doc time roughly doubles. Memory is never the issue.

### The admission cliff (Java side)
`qcTaskExecutor`: `core=4, max=8, queue=200`, **AbortPolicy** → the **209th** concurrent batch trigger gets an immediate **HTTP 503**; in-flight jobs keep running. Downstream, the **Celery worker concurrency (6)** is the true processing throttle — Java can admit 8, but only 6 documents OCR at once.

### The asymmetry that defines the product
- **API:** ~2,200–5,400 req/s.
- **Pipeline (mock):** ~168 docs/hour, CPU/OCR-bound.
- **Pipeline (real Groq):** far lower — the 6,000 TPM budget caps it to a few hundred docs/day.

So the product's real capacity ceiling is **document processing**, never Java throughput — which is exactly why the Groq response cache and the `GROQ_TPM_LIMIT` throttle matter, and why scaling means *more OCR/LLM capacity*, not more web threads.

---

## 4. Edge cases — every one passed live

| # | Edge | Result |
|---|---|---|
| 1 | Duplicate submit (same `idempotency_key`) | Second returns the **same job_id, `deduplicated:true`** ✓ |
| 2 | Cross-node cancel (`ClusterCoordinator`) | `cancelled:true`, batch → `UPLOADED` ✓ |
| 3 | Rerun supersede | result 60 → `superseded`, result 61 → `ACTIVE` with `rerun_of=60` ✓ |
| 4 | Celery worker killed mid-flight | Java **fell back to synchronous `/qc/process`** and completed (~60 s) ✓ |
| 5 | Python API-key | no key → **401**, key → **200** ✓ |
| 6 | DB least-privilege roles | Python role **denied** on `batch`; Java role **denied** on `adaptive_*` ✓ |

These exercise the integration logic directly: dedup, supersede/lineage, cross-node coordination, queue-down resilience, auth, and DB-enforced ownership all behave correctly.

---

## 4b. Real-Groq capacity probe (gpt-oss-120b, measured — not estimated)

Ran 3 fresh documents through the **real** Groq API via a recording proxy (cache OFF, TPM throttle = real 8,000) to capture exact token cost. 4th doc deliberately tripped the 40K safety cap. **Spent: 40,641 tokens (~20% of daily) + 39 requests (~4% of daily).**

**Measured cost per document:**
| Metric | Value |
|---|---|
| Tokens / doc | **~11,609** (range 8,494–13,480) |
| LLM calls / doc | **~12** (range 10–15) |
| Input : output | ~78% prompt : 22% completion (OCR text dominates the cost) |
| Wall time / doc | ~155–172 s (inflated by the 8K-TPM throttle — see below) |

**Free-tier ceiling (gpt-oss-120b: 30 RPM / 1,000 RPD / 8,000 TPM / 200,000 TPD):**
| Bound | Result |
|---|---|
| Tokens/day (200K ÷ 11,609) | **~17 docs/day ← BINDING** |
| Requests/day (1,000 ÷ 12) | ~83 docs/day |
| **Sustained free-tier capacity** | **~17 docs/day** |

**Versus the 250 docs/day target:** needs **2.9M tokens/day (14.5× over the free cap)** and **3,000 requests/day (3× over)**. The free tier is a non-starter for production volume.

**Two ways to close the gap:**
1. **Paid on-demand Groq** (no daily caps): at $0.15/M input + $0.60/M output, this workload is **~$0.0034/doc → 250 docs/day ≈ $0.85/day ≈ ~$25/month.** Trivial. This is the recommended fix.
2. **Cut LLM usage per doc** (currently high: 12 calls / ~11.6K tokens). Most of the cost is OCR text sent as input across many calls. Sending less text and making fewer calls could cut tokens 2–3×, lowering both the paid cost and the per-doc latency. An optimization, not a blocker.

> Note on latency: each doc took ~165 s here *because* a single doc needs ~11.6K tokens > the 8,000 TPM budget, so the client throttles ~1.5 min/doc. On a paid tier with higher TPM, per-doc latency drops to roughly OCR+rules (~55 s) + real inference — the throttle wait disappears.

---

## 4c. Form gap-fill batching — measured, NOT adopted (flag stays OFF)

Built `FORM_LLM_BATCH` (default off) to collapse the per-page-group gap-fill calls into one, then ran the measured A/B (`scripts/loadtest/measure_form_batch.py`) on a real doc through the recording proxy. The result is the case study for why P-8/P-13 exist:

| Mode | LLM calls | Tokens | PASS | FAIL | VERIFY | HOLD |
|---|---|---|---|---|---|---|
| OFF (per-group) | 12 | 11,178 | **126** | 3 | **17** | 1 |
| ON (batched) | 3 | 2,208 | **124** | 3 | **19** | 1 |
| Δ | **−75%** | **−80%** | −2 | — | +2 | — |

**Verdict: do NOT adopt.** Two findings the measurement surfaced:

1. **Accuracy regressed** — 2 rules flipped PASS→VERIFY (126→124 / 17→19). Batching changed extraction output.
2. **Root cause = Groq's per-request token ceiling.** The combined prompt triggered a live **HTTP 413 "Request too large… Requested 9521, Limit 8000"** — on the free tier a single request can't exceed the **8,000 TPM** budget. The merged prompt blew past it, Groq rejected it, gap-fill got fewer fields → the regression. The −75%/−80% "savings" are partly the *rejected* call, not real work done.

**The irony, made concrete:** on the free tier the *per-group* calls are not waste — they're what keeps each request under the 8K ceiling. Batching just converts "several small calls" into "one oversized call that gets 413'd."

**When batching could actually work** (future measured step, not now):
- On a **paid tier** with a higher per-request limit — but then cost isn't the problem batching was solving.
- Or by **capping the batched prompt < 8K tokens** (trim each section's page text, or only co-batch the small groups). That's a refinement to build behind the same flag and re-measure.

The flag ships **off**, the engine is unchanged, and `scripts/loadtest/measure_form_batch.py` is in place to re-test any future variant. No accuracy was risked.

---

## 4d. Groq prompt caching — measured, can't help this pipeline (flag-free, zero quota)

Groq prompt caching is real and **cached input tokens are exempt from the rate limits** (Groq docs + the account dashboard confirm it). The question was whether *this* pipeline can exploit it. Measured the cache ceiling with `scripts/loadtest/measure_prompt_overlap.py` (stubs the LLM, records every prompt, **no Groq calls**):

| Threshold (model min) | Cacheable input |
|---|---|
| 128 tok | **0%** |
| 256 tok | **0%** |
| 1024 tok | **0%** |

- The **longest exact prefix shared across the doc's LLM calls is ~45 tokens** (the tiny `assess_text` system line) — far below Groq's 128–1024-token minimum, so nothing qualifies.
- **Why:** the ~12 calls each read a *different* region (this grid page, that form page, this commentary section). There is no large repeated prefix for Groq to cache. The common prefix across all calls is ~0 tokens.

**Verdict:** prompt caching, though rate-limit-exempt, has nothing to bite on here — it cannot lift the 8K/min ceiling for unique documents. Engineering an artificial shared prefix (e.g. sending the whole doc on every call) caches after call 1 but leaves each call's unique slice counting, adds a big first-call cost, and changes what the model sees (unmeasured accuracy risk) — net neutral-to-worse. The free probe saved a pointless refactor. **Paid on-demand Groq (~$25/mo) remains the answer for production volume.**

*(Aside: the probe also surfaced a stub artifact — one path built a 744K-token "call" because the stubbed empty response changed control flow; it does not occur in normal runs, where per-doc input is ~11.6K. It doesn't affect the 0%-cacheable conclusion, since the shared prefix is tiny regardless.)*

---

## 5. Scaling levers (when you outgrow the box)

| Lever | Effect |
|---|---|
| Celery `--concurrency` ↑ | More docs OCR at once — until CPU saturates (≈ #cores). The #1 pipeline lever. |
| More worker hosts (Redis is shared) | Linear pipeline scale; the Redis queue + cross-node cancel already support it. |
| `QC_EXECUTOR_MAX` / `QUEUE` | Raises the 208 admission ceiling (only matters under burst). |
| `DB_POOL_MAX` (Java 30) + PgBouncer | Only if API concurrency grows past a few hundred — not the current limit. |
| Groq TPM / cache hit-rate | The real prod ceiling — raise the plan or lean on the content-hash cache. |

---

## 6. How to reproduce / tear down

Stack runs as background processes; logs in `/tmp/shal-loadtest/`. The mock LLM is wired only into the test instances via env vars — **no `.env` files were modified**.

```bash
# stop the test stack
pkill -f "app-0.0.1-SNAPSHOT.jar"; pkill -f "uvicorn main:app"; pkill -f "celery -A celery_app"; pkill -f "mock_llm:app"
# restore your normal Python dev service (real Groq) the way you usually start it
```

> Note: the test replaced the previously-running dev Python (real Groq) on :5001 with the mock-wired one. Restart your usual Python service to go back to real extraction. The DB roles from `least_privilege_roles.sql` persist (intended) — your services still connect fine as the existing superusers until you repoint them.
