-- V16: Add optimistic locking version column to Batch to prevent concurrent assignment race.
--
-- Hibernate @Version uses this column for optimistic locking:
-- if two transactions both read version=5, both try to update version 5→6,
-- the second one sees a stale row and throws OptimisticLockingFailureException.

ALTER TABLE batch
    ADD COLUMN IF NOT EXISTS version BIGINT NOT NULL DEFAULT 0;
