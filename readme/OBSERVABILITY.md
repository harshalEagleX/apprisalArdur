# Observability — Metrics, Alerts, Dashboards (OBS-008)

Wires monitoring on top of the metrics the app already exposes. Nothing here changes app behaviour — it is config you run alongside the services.

## What the app exposes

`/actuator/prometheus` (ADMIN-secured) serves:
- **Auto-bound** (Micrometer): `hikaricp_*` (DB pool), `jvm_*`/`process_*` (heap, CPU), `http_server_requests_*` (latency, status).
- **Custom** (`app/.../metrics/QcMetrics.java`): `shal_batches_qc_processing`, `shal_batches_review_pending`, `shal_batches_in_review`, `shal_batches_error`, `shal_batches_qc_stuck`. Sampled on scrape via cheap COUNT-by-status queries.

## Files

| File | Purpose |
|---|---|
| `prometheus/prometheus.yml.example` | Scrape config + the two access strategies for the ADMIN-secured endpoint |
| `prometheus/alert.rules.yml` | Alerts: backend down, pool saturation, heap, 5xx spike, stuck/error batches, review backlog |
| `prometheus/grafana-dashboard.json` | Import into Grafana for the platform overview |

## Setup (single internal host)

1. **Expose actuator to the scraper.** Recommended: a localhost-only management port —
   set `MANAGEMENT_SERVER_PORT=9091` and `MANAGEMENT_SERVER_ADDRESS=127.0.0.1` in the
   JVM env, then Prometheus scrapes `127.0.0.1:9091/actuator/prometheus`. (See the
   header of `prometheus.yml.example` for the trade-offs and the alternative
   admin-token approach if you keep it on the main port.)
2. **Run Prometheus** with `prometheus/prometheus.yml.example` (copy to `prometheus.yml`) and `alert.rules.yml` alongside it.
3. **Import the dashboard** `prometheus/grafana-dashboard.json` into Grafana and point it at the Prometheus datasource.
4. *(Optional)* point the alerts at Alertmanager for email/Slack.

## What each alert tells you

- **HikariPoolExhausted / NearMax** → DB pool is the bottleneck. Raise `DB_POOL_MAX` or find the slow query.
- **QcBatchesStuck** → a batch is wedged in `QC_PROCESSING`; check the Python OCR service + Celery worker. The `StuckBatchReconciler` will retry/abandon, but the alert surfaces it sooner.
- **QcErrorBatchesPresent** → batches in `ERROR` need an admin.
- **ReviewBacklogHigh** → staffing/throughput signal (info, not an error).
- **HttpServerErrorSpike / JvmHeapHigh / SHALBackendDown** → standard service-health alerts.

## Note on scale-out

The cross-node QC cancellation signal (`ClusterCoordinator`, Redis-backed with
in-memory fallback) means a "Stop QC" works even if multiple Java instances run.
Combined with the DB conditional-UPDATE claim guard, the backend is now safe to run
as more than one instance. On a single host nothing changes — the in-memory fallback
is used and behaviour is identical to before.
