-- V19: PASS / VERIFY / FAIL rule model removes the legacy warning counter.

ALTER TABLE qc_result
    DROP COLUMN IF EXISTS warning_count;
