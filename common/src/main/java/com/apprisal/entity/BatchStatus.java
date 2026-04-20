package com.apprisal.entity;

/**
 * Batch processing status enum tracking the lifecycle of a batch.
 */
public enum BatchStatus {
    UPLOADED, // Just uploaded, awaiting validation
    VALIDATING, // Structure validation in progress
    VALIDATION_FAILED, // Structure validation failed
    OCR_PENDING, // Awaiting OCR processing
    OCR_PROCESSING, // OCR extraction in progress
    OCR_COMPLETED, // OCR completed
    QC_PENDING, // Awaiting QC processing (NEW)
    QC_PROCESSING, // QC validation in progress (NEW)
    QC_COMPLETED, // QC completed, decision made (NEW)
    REVIEW_PENDING, // Has TO_VERIFY items, assigned to reviewer
    IN_REVIEW, // Reviewer actively reviewing
    COMPLETED, // Review completed, approved
    REJECTED, // Review completed, rejected
    ERROR // System error occurred
}
