package com.shal.common.entity;

/**
 * File processing status enum.
 *
 * Terminal states: COMPLETED, ERROR, DISMISSED.
 * DISMISSED is set by an admin when a file has permanently failed processing
 * (corrupt scan, unreadable PDF) and retrying will never succeed. It lets the
 * rest of the batch complete without that file blocking REVIEW_PENDING forever.
 *
 * NEEDS_ASSIGNMENT is set at intake when a supporting file (engagement, contract)
 * cannot be automatically linked to any appraisal in a multi-order batch — the
 * filenames carry no shared signal (e.g. "EngagementLetter 2.pdf" vs "ESCA-0019573.pdf").
 * The admin must manually assign it via the batch detail UI before Re-QC picks it up.
 */
public enum FileStatus {
    PENDING,           // Awaiting processing
    PROCESSING,        // Currently being processed
    COMPLETED,         // Processing completed successfully
    ERROR,             // Processing failed — admin can retry or dismiss
    DISMISSED,         // Admin accepted that this file cannot be processed; excluded from completion gate
    NEEDS_ASSIGNMENT   // Multi-order batch: no appraisal match found; admin must assign manually
}
