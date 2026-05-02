-- V20: Structured RuleOutcome fields for confidence-based PASS / VERIFY / FAIL.

ALTER TABLE qc_rule_result
    ADD COLUMN IF NOT EXISTS confidence_score DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS extracted_value TEXT,
    ADD COLUMN IF NOT EXISTS expected_value TEXT,
    ADD COLUMN IF NOT EXISTS verify_question TEXT,
    ADD COLUMN IF NOT EXISTS rejection_text TEXT,
    ADD COLUMN IF NOT EXISTS evidence TEXT;

ALTER TABLE qc_rule_result_AUD
    ADD COLUMN IF NOT EXISTS confidence_score DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS extracted_value TEXT,
    ADD COLUMN IF NOT EXISTS expected_value TEXT,
    ADD COLUMN IF NOT EXISTS verify_question TEXT,
    ADD COLUMN IF NOT EXISTS rejection_text TEXT,
    ADD COLUMN IF NOT EXISTS evidence TEXT;
