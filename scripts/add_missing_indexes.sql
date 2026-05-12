-- =============================================================================
-- Missing indexes identified in the May 2026 enterprise audit.
-- Run this ONCE against the Neon production database.
--
-- All statements use IF NOT EXISTS so the script is idempotent — safe to
-- re-run without causing errors if any index already exists.
--
-- Usage:
--   psql "$DB_URL" -f scripts/add_missing_indexes.sql
-- =============================================================================

-- ── qc_rule_result ────────────────────────────────────────────────────────────

-- Reviewer queue filtering by decision status within a QC result.
-- Without this index the reviewer-queue page loads trigger a full table scan
-- on qc_rule_result for every row in the queue — catastrophic at 10 k+ rows.
CREATE INDEX IF NOT EXISTS idx_qc_rule_qcresult_status
    ON qc_rule_result (qc_result_id, status);

-- Compound index for the common "find all FAILs/VERIFYs for a result" pattern.
CREATE INDEX IF NOT EXISTS idx_qc_rule_result_needs_review
    ON qc_rule_result (qc_result_id, review_required)
    WHERE review_required = true;

-- ── audit_log ─────────────────────────────────────────────────────────────────

-- Admin audit timeline queries (most recent actions for a user).
-- Without this, ordering by created_at requires a full scan on audit_log.
CREATE INDEX IF NOT EXISTS idx_audit_log_user_created
    ON audit_log (user_id, created_at DESC);

-- Entity-level audit lookup (e.g. "all changes to batch 42").
-- The (entity_type, entity_id) composite already exists from V2.
-- Adding created_at so timeline queries can skip the sort step.
CREATE INDEX IF NOT EXISTS idx_audit_log_entity_created
    ON audit_log (entity_type, entity_id, created_at DESC);

-- ── feedback_events (Python schema) ───────────────────────────────────────────

-- Training-loop query: find all corrections not yet used in retraining.
-- Without this, retrain.py scans the entire feedback_events table every run.
CREATE INDEX IF NOT EXISTS idx_feedback_untrained
    ON feedback_events (used_for_training)
    WHERE used_for_training = false;

-- ── qc_result ─────────────────────────────────────────────────────────────────

-- Dashboard query: count results by final decision status per client.
CREATE INDEX IF NOT EXISTS idx_qc_result_final_decision
    ON qc_result (final_decision)
    WHERE final_decision IS NOT NULL;

-- ── batch ─────────────────────────────────────────────────────────────────────

-- Admin batch search by client.
CREATE INDEX IF NOT EXISTS idx_batch_client_status
    ON batch (client_id, status);

-- ── Remove duplicate indexes introduced by V12 + V13 ─────────────────────────

-- V12 created idx_qc_rule_qcresult_id ON qc_rule_result(qc_result_id).
-- V13 created idx_qc_rule_result_qc  ON qc_rule_result(qc_result_id).
-- They are identical; drop the V12 one (keep the shorter name from V13).
DROP INDEX IF EXISTS idx_qc_rule_qcresult_id;

-- Verify (optional — uncomment to inspect):
-- SELECT indexname, indexdef FROM pg_indexes WHERE tablename IN
--   ('qc_rule_result','audit_log','feedback_events','qc_result','batch')
-- ORDER BY tablename, indexname;
