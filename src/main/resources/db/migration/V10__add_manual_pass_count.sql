-- Add manual_pass_count column to qc_result table
-- This tracks rules that were manually accepted by reviewers (VERIFY -> MANUAL_PASS)

ALTER TABLE qc_result ADD COLUMN manual_pass_count INTEGER DEFAULT 0;
