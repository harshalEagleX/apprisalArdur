-- ─────────────────────────────────────────────────────────────────────────────
-- QC RESULT EXTRACTION QUERIES
-- These queries retrieve QC result data in the format needed for report generation
-- ─────────────────────────────────────────────────────────────────────────────

-- ═════════════════════════════════════════════════════════════════════════════
-- 1. GET SINGLE QC RESULT WITH ALL RULE DETAILS (Main Report Query)
-- ═════════════════════════════════════════════════════════════════════════════

SELECT 
    qr.id AS qc_result_id,
    qr.batch_file_id,
    bf.file_name,
    bf.external_order_id,
    qr.qc_decision,
    qr.final_decision,
    qr.created_at AS qc_run_date,
    -- Stats
    COUNT(CASE WHEN rul.status = 'PASS' THEN 1 END) AS rules_passed,
    COUNT(CASE WHEN rul.status = 'FAIL' THEN 1 END) AS rules_failed,
    COUNT(CASE WHEN rul.status = 'VERIFY' THEN 1 END) AS rules_verify,
    COUNT(CASE WHEN rul.status = 'N/A' THEN 1 END) AS rules_na,
    COUNT(*) AS total_rules
FROM 
    qc_result qr
    JOIN batch_file bf ON qr.batch_file_id = bf.id
    LEFT JOIN qc_rule_result rul ON qr.id = rul.qc_result_id
WHERE 
    qr.id = :qc_result_id  -- Replace with actual QC result ID
    AND qr.superseded_at IS NULL  -- Get the active/latest result
GROUP BY 
    qr.id, qr.batch_file_id, bf.file_name, bf.external_order_id, 
    qr.qc_decision, qr.final_decision, qr.created_at;


-- ═════════════════════════════════════════════════════════════════════════════
-- 2. GET ALL RULE RESULTS FOR A QC RESULT (Detailed Rules)
-- ═════════════════════════════════════════════════════════════════════════════

SELECT 
    rul.id,
    rul.rule_id,
    rul.rule_name,
    rul.section,
    rul.status,
    rul.message,
    rul.details,
    rul.action_item,
    rul.needs_verification,
    rul.reviewer_verified,
    rul.reviewer_comment,
    rul.verified_at,
    rul.created_at
FROM 
    qc_rule_result rul
WHERE 
    rul.qc_result_id = :qc_result_id
ORDER BY 
    rul.section ASC,
    rul.rule_id ASC;


-- ═════════════════════════════════════════════════════════════════════════════
-- 3. GET QC RESULTS BY BATCH (For listing/reconciliation)
-- ═════════════════════════════════════════════════════════════════════════════

SELECT 
    qr.id,
    qr.batch_file_id,
    bf.file_name,
    bf.external_order_id,
    qr.qc_decision,
    qr.final_decision,
    qr.created_at,
    COUNT(CASE WHEN rul.status = 'PASS' THEN 1 END) AS passed,
    COUNT(CASE WHEN rul.status = 'FAIL' THEN 1 END) AS failed,
    COUNT(CASE WHEN rul.status = 'VERIFY' THEN 1 END) AS verify_needed,
    COUNT(*) AS total
FROM 
    qc_result qr
    JOIN batch_file bf ON qr.batch_file_id = bf.id
    LEFT JOIN qc_rule_result rul ON qr.id = rul.qc_result_id
WHERE 
    bf.batch_id = :batch_id
    AND qr.superseded_at IS NULL  -- Only active results
GROUP BY 
    qr.id, qr.batch_file_id, bf.file_name, bf.external_order_id,
    qr.qc_decision, qr.final_decision, qr.created_at
ORDER BY 
    qr.created_at DESC;


-- ═════════════════════════════════════════════════════════════════════════════
-- 4. STATS BREAKDOWN BY SECTION (For summary view)
-- ═════════════════════════════════════════════════════════════════════════════

SELECT 
    rul.section,
    rul.status,
    COUNT(*) AS count
FROM 
    qc_rule_result rul
WHERE 
    rul.qc_result_id = :qc_result_id
GROUP BY 
    rul.section,
    rul.status
ORDER BY 
    rul.section ASC,
    rul.status ASC;


-- ═════════════════════════════════════════════════════════════════════════════
-- 5. GET RULES NEEDING VERIFICATION (For reviewer queue)
-- ═════════════════════════════════════════════════════════════════════════════

SELECT 
    rul.id,
    rul.qc_result_id,
    qr.batch_file_id,
    bf.file_name,
    bf.external_order_id,
    rul.rule_id,
    rul.rule_name,
    rul.section,
    rul.message,
    rul.action_item,
    rul.reviewer_verified,
    rul.verified_at
FROM 
    qc_rule_result rul
    JOIN qc_result qr ON rul.qc_result_id = qr.id
    JOIN batch_file bf ON qr.batch_file_id = bf.id
WHERE 
    rul.status = 'VERIFY'
    AND rul.reviewer_verified IS NULL  -- Still pending review
    AND qr.superseded_at IS NULL
ORDER BY 
    rul.qc_result_id ASC,
    rul.rule_id ASC;


-- ═════════════════════════════════════════════════════════════════════════════
-- 6. GET VERIFICATIONS BY REVIEWER (For audit trail)
-- ═════════════════════════════════════════════════════════════════════════════

SELECT 
    rul.id,
    rul.rule_id,
    rul.status,
    rul.reviewer_verified,
    rul.reviewer_comment,
    rul.verified_at,
    COUNT(*) OVER (PARTITION BY rul.qc_result_id) AS total_rules_in_result
FROM 
    qc_rule_result rul
WHERE 
    rul.qc_result_id = :qc_result_id
    AND rul.reviewer_verified IS NOT NULL  -- Only reviewed items
ORDER BY 
    rul.verified_at DESC;


-- ═════════════════════════════════════════════════════════════════════════════
-- 7. FIND QC RESULTS BY STATUS (High-level summary for dashboard)
-- ═════════════════════════════════════════════════════════════════════════════

SELECT 
    qr.qc_decision,
    qr.final_decision,
    COUNT(*) AS count
FROM 
    qc_result qr
WHERE 
    qr.superseded_at IS NULL
    AND qr.created_at >= NOW() - INTERVAL '7 days'  -- Last 7 days
GROUP BY 
    qr.qc_decision,
    qr.final_decision
ORDER BY 
    count DESC;


-- ═════════════════════════════════════════════════════════════════════════════
-- USAGE EXAMPLES:
-- ═════════════════════════════════════════════════════════════════════════════

-- Replace placeholders when running:
--   :qc_result_id  → actual QC result ID (e.g., 1, 2, 3, 4)
--   :batch_id      → actual batch ID

-- Example 1: Get QC Result #1 details
-- EXEC this query with parameter: qc_result_id = 1

-- Example 2: Get all rules for QC #1, by section
-- EXEC query 2 with parameter: qc_result_id = 1

-- Example 3: Summary of batch 12
-- EXEC query 3 with parameter: batch_id = 12

-- CONNECTING FROM PSQL:
-- psql "postgresql://harshalsmac:12345678@localhost:5432/shal"
-- Then paste any query above and use \set qc_result_id 1 first
