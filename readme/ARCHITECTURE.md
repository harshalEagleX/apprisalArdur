# SHAL Platform — Architecture (UAT Branch)
> Full-stack Appraisal QC system · Docker Compose · Single-host UAT

---

## Legend

| Tag | Layer |
|---|---|
| 🔵 Blue | Frontend |
| 🟣 Purple | Java Backend |
| 🟢 Green | Python / AI |
| 🟡 Yellow | External AI |
| 🔴 Red | Data / Cache |
| ⚪ Gray | Observability / Testing |

---

## 👤 User / Browser

```
Browser
  ├── Opens :3000  →  Next.js frontend
  ├── REST calls   →  :8080 (Java backend)
  └── WebSocket    →  :8080/ws/qc (real-time QC updates)
```

**Protocols:** HTTP · WebSocket

---

## 🖥 Frontend Layer

### Next.js `v16.2.4` · Port `:3000`

| Property | Value |
|---|---|
| Runtime | React `19.2.4` |
| Language | TypeScript `5` |
| Styling | Tailwind CSS `v4` |
| Components | Radix UI (label, progress, tabs, separator, slot) |
| Charts | Recharts `3.8.1` |
| Network viz | react-force-graph `1.48.2` |
| PDF preview | react-pdf `10.4.1` · @react-pdf-viewer/core `3.12.0` |
| HTTP client | Axios `1.15.2` |
| File upload | react-dropzone `15.0.0` |
| Mode | SSR / CSR hybrid |

### Testing Brain *(Dev / CI only)*

| Property | Value |
|---|---|
| Framework | Playwright `≥1.57` |
| AI orchestration | LangChain `@langchain/core ^1.1.44` + OpenAI `^6.9.1` |
| Language | TypeScript `5` |
| Purpose | Multi-agent E2E simulation harness — drives the frontend via Playwright, uses OpenAI GPT models for intelligent test orchestration |

---

↕ `REST API + WebSocket /ws/qc`

---

## ☕ Java Backend Layer

### Spring Boot `4.0.1` · Port `:8080`

| Property | Value |
|---|---|
| Language | Java `21` |
| Server | Tomcat (embedded) |
| Auth | JWT via jjwt `0.12.6` |
| DB schema | JPA / Hibernate (`ddl-auto=update`) |
| Build | Maven (multi-module) |
| WebSocket | Raw WS (non-STOMP) at `/ws/qc` — JWT auth at handshake |

#### Maven Modules

| Module | Responsibility |
|---|---|
| `app` | Main entry point · controllers · services · realtime WS |
| `common` | Shared models, utils, DTOs |
| `user` | Auth, JWT issuance, role management |
| `batch` | Scheduled batch jobs |
| `qc` | QC domain logic and orchestration |

#### Key Java Components

- `WebSocketConfig` — registers `/ws/qc` handler, CORS wildcard for UAT
- `WebSocketAuthHandshakeInterceptor` — validates JWT at WS handshake
- `QcWebSocketHandler` — pushes live QC progress to browser
- `WebSocketRealtimeEventPublisher` — publishes realtime events
- `RedisClusterCoordinator` — Redis-backed coordination
- `QCProgressStore` — Redis-backed QC progress state
- `CacheConfig` — Spring Cache abstraction over Redis
- `AnalyticsService` — analytics with Redis caching

---

↕ `HTTP REST (internal) + Redis pub/sub`

---

## 🐍 Python / AI Layer

### OCR Service (FastAPI) · Port `:5001`

| Property | Value |
|---|---|
| Language | Python `3.11` |
| Framework | FastAPI `≥0.111.0` |
| ASGI server | Uvicorn `≥0.29.0` |
| Rate limiting | slowapi `≥0.1.9` |
| Observability | OpenTelemetry SDK `≥1.24.0` |

**PDF → Text Pipeline:**

```
PDF input
  ├── PyMuPDF (fitz) ≥1.24.0     → text + layout extraction
  ├── pdfplumber ≥0.11.0          → whitespace-separated tables
  ├── camelot-py ≥0.11.0          → bordered table extraction (needs ghostscript + OpenCV)
  ├── pytesseract ≥0.3.13          → OCR on image-based pages (needs tesseract binary)
  ├── OpenCV ≥4.9.0                → image preprocessing (grayscale / threshold / deskew)
  └── Pillow ≥10.3.0               → image handling
```

**Data / ML stack:**

```
numpy ≥1.26 · pandas ≥2.2 · scipy ≥1.13 · scikit-learn ≥1.5
SQLAlchemy ≥2.0 + psycopg2-binary ≥2.9   → PostgreSQL access
```

---

### Celery Worker *(Background, concurrency=2)*

| Property | Value |
|---|---|
| Task queue | Celery `≥5.3.0` |
| Broker | Redis `≥5.0.0` (via Kombu `≥5.3.0`) |
| Concurrency | 2 workers |
| Docker image | Same as `ocr-service` — different `CMD` |
| Writes results to | PostgreSQL |
| Schema ownership | `manage_db.py recreate` (SQLAlchemy) |

**Celery task flow:**

```
OCR Service  →  enqueue task  →  Redis broker
                                      ↓
                              Celery Worker
                                      ↓
                         PDF → Groq LLM → structured JSON
                                      ↓
                                 PostgreSQL
```

---

### Groq LLM API *(External · HTTPS)*

| Property | Value |
|---|---|
| Provider | Groq Cloud |
| API style | OpenAI-compatible REST |
| Role | Structured field extraction from OCR'd text |
| Rate limiting | Distributed Redis token bucket (key: `groq:tpm:extraction`) |
| Fallback | In-process throttle if Redis is unavailable |

---

↕ `SQL (PostgreSQL) + Redis (broker / cache)`

---

## 🗄 Data / Cache Layer

### PostgreSQL `16` · Port `:5432`

| Property | Value |
|---|---|
| Docker image | `postgres:16` |
| Database name | `shal` (default) |
| Volume | `pgdata` (persistent) |
| Java tables | Managed by JPA/Hibernate (`ddl-auto=update`) |
| Python tables | Managed by SQLAlchemy + `manage_db.py recreate` |
| Health check | `pg_isready` |

---

### Redis `7` · Port `:6379`

| Property | Value |
|---|---|
| Docker image | `redis:7` |
| Persistence | AOF (`--appendonly yes`) |
| Volume | `redisdata` (persistent) |
| Health check | `redis-cli ping` |

**Dual role — Redis is used by both layers:**

```
Redis 7
  ├── [Celery broker]     Task queue for OCR/LLM jobs (Python)
  ├── [Groq TPM bucket]   Distributed rate-limit counter across workers (Python)
  ├── [QCProgressStore]   Live QC progress state (Java)
  ├── [CacheConfig]       Spring Cache abstraction (Java)
  └── [RedisCluster]      Cluster coordination / pub-sub (Java)
```

---

↕ `Metrics scrape`

---

## 📊 Observability Layer

### Prometheus · Port `:9090`

| Property | Value |
|---|---|
| Docker image | `prom/prometheus:latest` |
| Source | Scrapes Java `/actuator/prometheus` (Micrometer) |
| Alerts | `alert.rules.yml` |
| Volume | `promdata` (persistent) |

### Grafana · Port `:3001`

| Property | Value |
|---|---|
| Docker image | `grafana/grafana:latest` |
| Datasource | Prometheus |
| Dashboard | `prometheus/grafana-dashboard.json` |
| Volume | `grafanadata` (persistent) |
| Auth | Admin password via `GRAFANA_PASSWORD` env var |

---

## 📋 Key Data Flows

| Flow | Path | Protocol / Notes |
|---|---|---|
| **Login / Auth** | Browser → Next.js → Java `:8080` → PostgreSQL | REST POST. JWT issued, stored as cookie. Role-based access. |
| **PDF Upload** | Browser → Java `:8080` (multipart) → OCR Service `:5001` | Java stores file in `/app/uploads` volume, calls OCR via internal HTTP. |
| **OCR / Extraction** | OCR Service → Celery Worker (via Redis broker) → PostgreSQL | Heavy OCR queued as Celery task. Worker processes PDF → Groq LLM → structured JSON → DB. |
| **Real-time QC Updates** | Java (`:8080/ws/qc`) → Browser WebSocket | Spring WebSocket (non-STOMP, raw WS). `QcWebSocketHandler` pushes live QC progress. JWT auth at handshake via interceptor. |
| **Groq TPM Rate-Limit** | OCR / Celery Workers → Redis token bucket | Distributed Redis counter enforces Groq tokens-per-minute across all worker instances. |
| **Analytics / Cache** | Java → Redis → Java (read-through) | `RedisClusterCoordinator` + `QCProgressStore` + Spring Cache abstraction. |
| **Metrics** | Java → Prometheus `:9090` → Grafana `:3001` | Spring Actuator exposes `/actuator/prometheus`. Prometheus scrapes on interval. Grafana visualises. |

---

## 🔖 Version Reference

| Technology | Version | Role | Language |
|---|---|---|---|
| Next.js | `16.2.4` | SSR/CSR Frontend | TypeScript 5 |
| React | `19.2.4` | UI library | TypeScript 5 |
| Tailwind CSS | `v4` | Styling | CSS |
| Spring Boot | `4.0.1` | Java API + WS server | Java 21 |
| JWT (jjwt) | `0.12.6` | Auth tokens | Java |
| FastAPI | `≥0.111.0` | Python OCR API | Python 3.11 |
| Uvicorn | `≥0.29.0` | ASGI server | Python |
| Celery | `≥5.3.0` | Async task queue | Python |
| Kombu | `≥5.3.0` | Celery message transport | Python |
| PyMuPDF | `≥1.24.0` | PDF text extraction | Python |
| pdfplumber | `≥0.11.0` | Table extraction | Python |
| camelot-py | `≥0.11.0` | Bordered table extraction | Python |
| pytesseract | `≥0.3.13` | OCR wrapper | Python |
| OpenCV | `≥4.9.0` | Image preprocessing | Python |
| SQLAlchemy | `≥2.0.0` | Python ORM | Python |
| PostgreSQL | `16` | Primary database | SQL |
| Redis | `7` | Broker + Cache | — |
| Groq LLM API | cloud | AI extraction | HTTP / OpenAI-compatible |
| Prometheus | latest | Metrics collection | — |
| Grafana | latest | Metrics dashboards | — |
| Playwright | `≥1.57` | E2E test harness (brain) | TypeScript |
| LangChain | `^1.1.44` | AI test orchestration | TypeScript |
| Docker Compose | — | UAT orchestration | YAML |

---

## 🐳 Docker Compose UAT — Service Dependency Order

```
postgres ──────────────────────────────────────────┐
redis ─────────────────────────────────────────────┤
                                                   ↓
                                          ocr-service (:5001)
                                          celery-worker
                                                   ↓
                                        java-backend (:8080)
                                                   ↓
                                          frontend (:3000)
                                          prometheus (:9090)
                                                   ↓
                                           grafana (:3001)
```

**Startup:** `bash scripts/uat/up.sh` (after copying `.env.uat.example` → `.env.uat`)

---

*Generated from UAT branch · 2026-06-23*
