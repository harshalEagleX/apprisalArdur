-- V15: Migrate old BatchStatus values and CLIENT role to the simplified two-role model.
--
-- IMPORTANT: Run this migration BEFORE removing CLIENT from Role.java enum and
--            before removing old BatchStatus values from BatchStatus.java.
--            This migration is safe to run multiple times (idempotent WHERE clauses).

-- ── Role migration ────────────────────────────────────────────────────────────
-- If any CLIENT users exist, convert them to REVIEWER.
-- DBA: verify this list before applying to production and manually decide ADMIN vs REVIEWER.
UPDATE _user SET role = 'REVIEWER' WHERE role = 'CLIENT';

-- ── BatchStatus migration ─────────────────────────────────────────────────────
-- Collapse the 6 OCR/QC intermediate states into QC_PROCESSING.
UPDATE batch
    SET status = 'QC_PROCESSING'
WHERE status IN ('OCR_PENDING', 'OCR_PROCESSING', 'OCR_COMPLETED', 'QC_PENDING', 'QC_COMPLETED');

-- Map REJECTED to ERROR (reviewer rejection now sets batch to ERROR for re-inspection).
UPDATE batch SET status = 'ERROR' WHERE status = 'REJECTED';

-- Verify no unexpected states remain (run manually to confirm):
-- SELECT status, COUNT(*) FROM batch GROUP BY status ORDER BY status;
