-- ─────────────────────────────────────────────────────────────────────────────
-- Drop the reviewer FAIL→Pass "override" feature columns from qc_rule_result
--
-- The override / second-approval workflow was removed: a reviewer PASS on a failed
-- rule now becomes a direct MANUAL_PASS with no admin Override Queue. The five
-- backing columns are therefore dead. Hibernate ddl-auto=update NEVER drops
-- columns, so this is a deliberate manual step (per the project DB policy).
--
-- Safe to run once the override-removal build is deployed (nothing reads/writes
-- these columns anymore). Run:
--     psql "$DB_URL" -f scripts/db/drop_override_columns.sql
--
-- Reversible only by restoring from backup — take one first if this is production.
-- The FK columns are dropped before the table columns they reference nothing else.
-- ─────────────────────────────────────────────────────────────────────────────

BEGIN;

ALTER TABLE qc_rule_result
    DROP COLUMN IF EXISTS override_pending,
    DROP COLUMN IF EXISTS override_requested_by,
    DROP COLUMN IF EXISTS override_requested_at,
    DROP COLUMN IF EXISTS override_approved_by,
    DROP COLUMN IF EXISTS override_approved_at;

COMMIT;
