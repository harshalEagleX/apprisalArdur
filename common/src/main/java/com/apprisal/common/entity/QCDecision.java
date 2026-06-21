package com.apprisal.common.entity;

/**
 * QC Decision enum representing the automated decision from Python QC
 * processing.
 * 
 * AUTO_PASS: All rules passed - batch can proceed without reviewer
 * TO_VERIFY: Some VERIFY items need human review
 * AUTO_FAIL: Critical failures detected - automatic rejection
 * BLOCKED:   A HOLD rule blocks the report - cannot finalise until resolved
 */
public enum QCDecision {
    AUTO_PASS, // All rules passed - no reviewer needed
    TO_VERIFY, // Has VERIFY items - needs reviewer verification
    AUTO_FAIL, // Has failures - automatic rejection
    // Derived from the engine's blocking signal (any HOLD rule). Honoured by
    // every client — API/automation included — not just the reviewer UI.
    BLOCKED
}
