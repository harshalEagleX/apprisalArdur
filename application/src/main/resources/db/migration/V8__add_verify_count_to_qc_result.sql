-- Add verify_count column to qc_result table
-- This stores the count of items needing human verification (OCR uncertain)
ALTER TABLE qc_result ADD COLUMN IF NOT EXISTS verify_count INTEGER DEFAULT 0;
