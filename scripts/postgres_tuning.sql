-- =============================================================================
-- Scaling Phase 5 §4.1 — PostgreSQL server tuning for a single 8–16c / 32–64GB host.
--
-- Values below are STARTING POINTS sized for a ~48GB host. Adjust to the actual RAM
-- of the deployment box. Apply as a superuser, then RESTART Postgres:
--   psql -d ardurApprisal -f scripts/postgres_tuning.sql
--   brew services restart postgresql@16   # or: pg_ctl restart
--
-- shared_buffers and max_connections require a RESTART; the rest are reloadable.
-- Revert any line with: ALTER SYSTEM RESET <name>;  then SELECT pg_reload_conf();
-- (log_min_duration_statement / log_lock_waits were already set in Phase 0.)
-- =============================================================================

-- Connections: Java Hikari 30 + (7 Celery workers × 5) ≈ 65 + headroom. If worker
-- count grows, prefer PgBouncer (transaction pooling) over raising this further.
ALTER SYSTEM SET max_connections = 200;

-- Memory (sized for ~48GB RAM — scale with the host):
ALTER SYSTEM SET shared_buffers = '8GB';            -- ~25% RAM
ALTER SYSTEM SET effective_cache_size = '24GB';     -- ~50% RAM (planner hint, not an allocation)
ALTER SYSTEM SET work_mem = '32MB';                 -- per sort/hash node; modest because many connections
ALTER SYSTEM SET maintenance_work_mem = '1GB';      -- VACUUM / index builds

-- Write / checkpoint behaviour:
ALTER SYSTEM SET wal_compression = on;
ALTER SYSTEM SET checkpoint_completion_target = 0.9;
ALTER SYSTEM SET max_wal_size = '4GB';

-- SSD-oriented planner costs:
ALTER SYSTEM SET random_page_cost = 1.1;
ALTER SYSTEM SET effective_io_concurrency = 200;

-- Autovacuum a bit more aggressive for the high-churn business_event / audit_log /
-- qc_rule_result tables (≈70k rows/day at 250 docs — see QL-10).
ALTER SYSTEM SET autovacuum_vacuum_scale_factor = 0.05;
ALTER SYSTEM SET autovacuum_analyze_scale_factor = 0.02;

SELECT pg_reload_conf();
-- RESTART required for shared_buffers + max_connections to take effect.
