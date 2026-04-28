-- V12: Performance indexes for production queries
-- All CREATE INDEX CONCURRENTLY cannot run in a transaction — using IF NOT EXISTS

-- batch_file: OCR hash lookups and file-type filtering
CREATE INDEX IF NOT EXISTS idx_batch_file_order_type ON batch_file (batch_id, order_id, file_type);
CREATE INDEX IF NOT EXISTS idx_batch_file_status     ON batch_file (status);

-- batch: common dashboard queries
CREATE INDEX IF NOT EXISTS idx_batch_client_status   ON batch (client_id, status);
CREATE INDEX IF NOT EXISTS idx_batch_reviewer_status ON batch (assigned_reviewer_id, status);
CREATE INDEX IF NOT EXISTS idx_batch_created_at      ON batch (created_at DESC);

-- qc_result: reviewer queue + decision lookup
CREATE INDEX IF NOT EXISTS idx_qc_result_decision    ON qc_result (qc_decision);
CREATE INDEX IF NOT EXISTS idx_qc_result_final       ON qc_result (final_decision);
CREATE INDEX IF NOT EXISTS idx_qc_result_batchfile   ON qc_result (batch_file_id);

-- qc_rule_result: per-QC rule lookups
CREATE INDEX IF NOT EXISTS idx_qc_rule_qcresult_id   ON qc_rule_result (qc_result_id);
CREATE INDEX IF NOT EXISTS idx_qc_rule_needs_verif   ON qc_rule_result (qc_result_id, needs_verification)
    WHERE needs_verification = TRUE;

-- audit_log: dashboard recent activity
CREATE INDEX IF NOT EXISTS idx_audit_log_created     ON audit_log (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_user        ON audit_log (user_id, created_at DESC);
