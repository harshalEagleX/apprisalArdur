-- V18: Review workflow safeguards for PASS / VERIFY / FAIL operations.

ALTER TABLE qc_result
    ADD COLUMN IF NOT EXISTS review_locked_by BIGINT REFERENCES _user(id),
    ADD COLUMN IF NOT EXISTS review_session_token VARCHAR(128),
    ADD COLUMN IF NOT EXISTS review_started_at TIMESTAMP,
    ADD COLUMN IF NOT EXISTS review_last_active_at TIMESTAMP,
    ADD COLUMN IF NOT EXISTS review_lock_expires_at TIMESTAMP,
    ADD COLUMN IF NOT EXISTS review_lock_acknowledged BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_qc_result_review_lock
    ON qc_result (review_locked_by, review_lock_expires_at);

ALTER TABLE qc_rule_result
    ADD COLUMN IF NOT EXISTS version BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS review_session_token VARCHAR(128),
    ADD COLUMN IF NOT EXISTS first_presented_at TIMESTAMP,
    ADD COLUMN IF NOT EXISTS decision_latency_ms BIGINT,
    ADD COLUMN IF NOT EXISTS acknowledged_references BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS override_pending BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS override_requested_by BIGINT REFERENCES _user(id),
    ADD COLUMN IF NOT EXISTS override_requested_at TIMESTAMP,
    ADD COLUMN IF NOT EXISTS override_approved_by BIGINT REFERENCES _user(id),
    ADD COLUMN IF NOT EXISTS override_approved_at TIMESTAMP;

CREATE INDEX IF NOT EXISTS idx_qc_rule_review_session
    ON qc_rule_result (review_session_token);

CREATE INDEX IF NOT EXISTS idx_qc_rule_override_pending
    ON qc_rule_result (override_pending);

ALTER TABLE qc_result_AUD
    ADD COLUMN IF NOT EXISTS review_locked_by BIGINT,
    ADD COLUMN IF NOT EXISTS review_locked_by_id BIGINT,
    ADD COLUMN IF NOT EXISTS review_session_token VARCHAR(128),
    ADD COLUMN IF NOT EXISTS review_started_at TIMESTAMP,
    ADD COLUMN IF NOT EXISTS review_last_active_at TIMESTAMP,
    ADD COLUMN IF NOT EXISTS review_lock_expires_at TIMESTAMP,
    ADD COLUMN IF NOT EXISTS review_lock_acknowledged BOOLEAN;

ALTER TABLE qc_rule_result_AUD
    ADD COLUMN IF NOT EXISTS review_session_token VARCHAR(128),
    ADD COLUMN IF NOT EXISTS first_presented_at TIMESTAMP,
    ADD COLUMN IF NOT EXISTS decision_latency_ms BIGINT,
    ADD COLUMN IF NOT EXISTS acknowledged_references BOOLEAN,
    ADD COLUMN IF NOT EXISTS override_pending BOOLEAN,
    ADD COLUMN IF NOT EXISTS override_requested_by BIGINT,
    ADD COLUMN IF NOT EXISTS override_requested_by_id BIGINT,
    ADD COLUMN IF NOT EXISTS override_requested_at TIMESTAMP,
    ADD COLUMN IF NOT EXISTS override_approved_by BIGINT,
    ADD COLUMN IF NOT EXISTS override_approved_by_id BIGINT,
    ADD COLUMN IF NOT EXISTS override_approved_at TIMESTAMP;
