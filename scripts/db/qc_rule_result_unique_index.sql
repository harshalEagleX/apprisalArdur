-- ─────────────────────────────────────────────────────────────────────────────
-- Make duplicate-rule-row prevention STRUCTURAL (DB-008 / RR-003)
--
-- Today "one row per (qc_result_id, rule_id)" is guaranteed only by the single
-- Java write path (QCProcessingService.persistPythonResult). This adds a DB-level
-- guarantee so a future bug or a concurrent writer cannot create duplicates.
--
-- SAFE ROLLOUT — this is NOT auto-applied by ddl-auto on purpose, because adding a
-- UNIQUE index to a table that already holds duplicates would FAIL the build and
-- could disrupt the running app. Run it deliberately, in two steps:
--
--   STEP 1 — find existing duplicates (must return ZERO rows before step 2):
--     psql "$DB_URL" -f scripts/db/qc_rule_result_unique_index.sql -v step=check
--   STEP 2 — once clean, create the index CONCURRENTLY (no table lock):
--     psql "$DB_URL" -c "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS \
--       uq_qc_rule_result_result_rule ON qc_rule_result (qc_result_id, rule_id);"
--
-- If STEP 1 returns rows, dedupe first (keep the newest per group):
--     DELETE FROM qc_rule_result a
--      USING qc_rule_result b
--      WHERE a.qc_result_id = b.qc_result_id
--        AND a.rule_id      = b.rule_id
--        AND a.id < b.id;          -- keep the highest id (latest insert)
-- Re-run STEP 1 to confirm zero, then STEP 2.
-- ─────────────────────────────────────────────────────────────────────────────

-- STEP 1: duplicate report. Any row here blocks the unique index.
SELECT qc_result_id,
       rule_id,
       COUNT(*) AS copies,
       MIN(id)  AS keep_lowest_id,
       MAX(id)  AS keep_highest_id
FROM   qc_rule_result
GROUP BY qc_result_id, rule_id
HAVING COUNT(*) > 1
ORDER BY copies DESC, qc_result_id;
