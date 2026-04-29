-- V17: No schema change required.
-- The @Formula field (fileCount) on Batch is a computed SQL expression,
-- not a physical column. No ALTER TABLE needed.
-- This migration exists as a checkpoint after the V14-V16 changes.
SELECT 1;
