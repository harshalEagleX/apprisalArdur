# SHAL — Deployment & Pre-flight Validation

This is the checklist to run **before starting SHAL on any target** — a laptop, a
single server, a cloud VM/container, or a hybrid split (some services local, some
remote). Follow it top-to-bottom; the golden rule is: **run the preflight, get a
green result, then start.**

```bash
bash scripts/preflight.sh            # dev: insecure defaults are warnings
bash scripts/preflight.sh --strict   # production: warnings become hard failures
```

Exit code `0` = safe to start. Non-zero = fix the `✗` items first. It never starts
or mutates anything — it only reads config and probes connectivity.

---

## 1. The stack & its dependencies

| Service | Port (default) | Hard dependency | Optional (degrades) |
|---|---|---|---|
| **Java API** (`app`) | 8080 | **PostgreSQL** | Python OCR, Redis |
| **Python OCR/QC** (`ocr-service`) | 5001 | **PostgreSQL** | Redis, Groq, Google/Gemini Vision |
| **Frontend** (`frontend`, Next.js) | 3000 | Java API (at runtime, for data) | — |

**Resilience model — what actually blocks startup:**
- **PostgreSQL is the only hard dependency.** Both backends need it. Preflight verifies it is reachable *before* you start, so you never boot into a broken DB.
- **Everything else degrades, never crashes:**
  - Python OCR down → Java QC endpoints return **503 with a clear message**; the rest of the app is fully usable.
  - Redis down → Java and Python fall back to **local/in-process** state (cancel signals, QC progress, token bucket). Single-node runs don't need Redis at all.
  - Groq / Vision keys absent → extraction falls back to deterministic readers; QC still runs.
  - Frontend with Java down → pages render and show errors; the site still serves.

So a connection/service hiccup in an **optional** dependency can never stop the stack from *running*. The one **required** dependency (Postgres) is what preflight guards.

---

## 2. No secrets or URLs are hardcoded

All endpoints, keys and secrets come from the environment. Nothing sensitive is
baked into a source file:

- **Java** — `application.yml` uses `${VAR:-default}`; dev defaults exist only so a
  laptop run works. In production these are enforced (see below).
- **Python** — `app/config.py` reads everything via `os.getenv`; `CORS_ALLOWED_ORIGINS`
  is env-driven.
- **Frontend** — the backend base URL is `NEXT_PUBLIC_JAVA_URL` (`lib/config.ts`).

**Production enforcement:** the Java app runs `ProductionReadinessValidator` at
startup. When the deployment is production (an active Spring profile contains
`prod`/`production`, **or** `APP_DEPLOY_STRICT=true`), it **refuses to start** if any
secret is still the shipped default (`JWT_SECRET`, `DB_PASSWORD`, `ADMIN_PASSWORD`),
if `INTERNAL_API_KEY` is missing, or if `COOKIE_SECURE=false`. In a plain local run it
only warns, so nothing local breaks.

---

## 3. Environment variables

Set these via the environment (or `.env` files — see `.env.example`,
`ocr-service/.env.example`). Real environment values always win over `.env` files.

### Required everywhere
| Var | Used by | Purpose |
|---|---|---|
| `INTERNAL_API_KEY` | Java, Python | Shared secret; Java sends `X-API-Key` to Python. Python refuses to start without it (unless `SHAL_REQUIRE_API_KEY=false`). |
| `DB_URL` | Java | JDBC URL, e.g. `jdbc:postgresql://HOST:5432/shal_qc`. |
| `DB_USERNAME`, `DB_PASSWORD` | Java | DB credentials. |
| `DATABASE_URL` | Python | SQLAlchemy URL, e.g. `postgresql://USER:PASS@HOST:5432/shal_qc`. |

### Required for production (must NOT be the shipped defaults)
| Var | Purpose | Notes |
|---|---|---|
| `JWT_SECRET` | Signs auth tokens | Long random string; default is refused in prod. |
| `ADMIN_PASSWORD` | Seed admin password | Default `Admin123!` refused in prod. |
| `ADMIN_EMAIL` | Seed admin username | This is the login username (not "admin"). |
| `COOKIE_SECURE` | `true` behind HTTPS | Refused as `false` in strict/prod. |

### Cross-service URLs (env, not hardcoded)
| Var | Used by | Default |
|---|---|---|
| `OCR_SERVICE_URL` | Java | `http://localhost:5001` |
| `NEXT_PUBLIC_JAVA_URL` | Frontend (build-time) | `http://localhost:8080` |
| `CORS_ALLOWED_ORIGINS` | Python | `http://localhost:3000,http://127.0.0.1:3000` |
| `app.cors.allowed-origins` (`APP_CORS_ALLOWED_ORIGINS`) | Java | `http://localhost:3000,http://localhost:8080` |

### Optional
| Var | Used by | Effect if absent |
|---|---|---|
| `REDIS_URL` | Java, Python | Local/sync fallback (fine single-node). |
| `GROQ_API_KEY`, `GROQ_MODEL`, `GROQ_VISION_MODEL` | Python | LLM grid/gap-fill extraction disabled → deterministic readers only. |
| `VISION_ENABLED`, `GEMINI_API_KEY` / `GOOGLE_APPLICATION_CREDENTIALS` | Python | Photo/vision analysis disabled. |
| `APP_DEPLOY_STRICT` | Java | `true` forces the production-readiness guard even without a prod profile. |
| `STORAGE_PATH`, `OCR_TIMEOUT`, `OCR_RETRIES` | Java | Sensible defaults. |

---

## 4. Pre-deploy checklist (every environment)

1. **Provision Postgres** and create the database. Both backends point at the *same* DB.
2. **Set the environment** — export the required vars, or fill `.env` / `ocr-service/.env` from the `.env.example` files.
3. **Run preflight** — `bash scripts/preflight.sh --strict` for production, plain for dev. Get a green result.
4. **Start in order** (`clean_run.sh` does this): Postgres → Java → Python OCR → Frontend. Java and Python each wait for their own health endpoint; Python may come up after Java (Java tolerates it).
5. **Log in** with `ADMIN_EMAIL` / `ADMIN_PASSWORD` (the seeded admin username is the email).

---

## 5. Per-environment notes

**Local (all on one machine)** — the shipped defaults let it run immediately; `clean_run.sh` builds fresh, stops any prior run, and starts everything. Preflight in dev mode is enough.

**Single external server** — set real `JWT_SECRET`, `ADMIN_PASSWORD`, DB creds, `INTERNAL_API_KEY`; `COOKIE_SECURE=true` behind a TLS reverse proxy; point `NEXT_PUBLIC_JAVA_URL` at the public API URL and `CORS_ALLOWED_ORIGINS` / `app.cors.allowed-origins` at the public frontend origin. Run `preflight.sh --strict`.

**Cloud (VMs / containers / managed DB)** — use the platform's secret manager for all secrets; point `DB_URL`/`DATABASE_URL` at the managed Postgres; provide `REDIS_URL` for multi-node. Because services may start concurrently, run `preflight.sh --strict` as an init/readiness step so a container that can't reach the DB fails loudly instead of half-running. `APP_DEPLOY_STRICT=true` guarantees the secret guard fires even without a `prod` profile.

**Hybrid (local + cloud)** — e.g. frontend local, API+DB in cloud, or OCR in cloud: every cross-service address is an env var, so just point them at the right hosts (`NEXT_PUBLIC_JAVA_URL`, `OCR_SERVICE_URL`, `DB_URL`/`DATABASE_URL`, `REDIS_URL`, CORS origins). Run preflight on each host that starts a service — it validates *that host's* reachability to its dependencies.

---

## 6. Production hardening quick list
- [ ] `JWT_SECRET`, `ADMIN_PASSWORD`, `DB_PASSWORD` are unique real values (preflight `--strict` green).
- [ ] `INTERNAL_API_KEY` set on both Java and Python (same value).
- [ ] `COOKIE_SECURE=true` and the app is served over HTTPS.
- [ ] `CORS_ALLOWED_ORIGINS` / `app.cors.allowed-origins` restricted to the real frontend origin(s).
- [ ] `DB_URL`/`DATABASE_URL` point at the managed/production DB; backups configured.
- [ ] `REDIS_URL` set if running more than one node.
- [ ] `SHAL_EXPOSE_DOCS` left `false` (Python API docs stay hidden).
- [ ] `preflight.sh --strict` exits `0` on every host before start.
