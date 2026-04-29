package com.apprisal.common.entity;

/**
 * Batch lifecycle states — 8 states, strict forward-only transitions.
 *
 * UPLOADED         → VALIDATING
 * VALIDATING       → VALIDATION_FAILED | QC_PROCESSING
 * QC_PROCESSING    → REVIEW_PENDING | COMPLETED | ERROR
 * REVIEW_PENDING   → IN_REVIEW
 * IN_REVIEW        → COMPLETED | ERROR
 */
public enum BatchStatus {
    UPLOADED,          // ZIP received, awaiting validation
    VALIDATING,        // Folder/file structure check running
    VALIDATION_FAILED, // Bad structure, no PDFs found, path traversal detected
    QC_PROCESSING,     // Python OCR + 136 rules running
    REVIEW_PENDING,    // Has FAIL/VERIFY items, waiting for reviewer assignment
    IN_REVIEW,         // Reviewer actively working on it
    COMPLETED,         // All rules pass or reviewer accepted all items
    ERROR              // System error, needs manual investigation
}
