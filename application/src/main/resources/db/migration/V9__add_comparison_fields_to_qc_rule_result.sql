-- V9: Add comparison fields for reviewer UI display
-- These fields store the extracted values for side-by-side comparison

ALTER TABLE qc_rule_result ADD COLUMN appraisal_value TEXT;
ALTER TABLE qc_rule_result ADD COLUMN engagement_value TEXT;
ALTER TABLE qc_rule_result ADD COLUMN review_required BOOLEAN DEFAULT FALSE;

-- Update existing records: set review_required based on needs_verification
UPDATE qc_rule_result SET review_required = needs_verification WHERE needs_verification IS NOT NULL;

-- Create index for filtering by review_required
CREATE INDEX idx_qc_rule_result_review_required ON qc_rule_result(review_required) WHERE review_required = TRUE;
