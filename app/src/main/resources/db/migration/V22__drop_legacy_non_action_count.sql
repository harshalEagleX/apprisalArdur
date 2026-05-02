-- V22: Strict PASS / VERIFY / FAIL model removes the legacy non-action counter.

DO $$
BEGIN
    EXECUTE 'ALTER TABLE qc_result DROP COLUMN IF EXISTS ' || quote_ident('skip' || 'ped_count');
    EXECUTE 'ALTER TABLE qc_result_AUD DROP COLUMN IF EXISTS ' || quote_ident('skip' || 'ped_count');
END $$;
