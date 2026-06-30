package com.shal.common.entity;

/**
 * File processing status enum.
 *
 * Terminal states: COMPLETED, ERROR, DISMISSED.
 * DISMISSED is set by an admin when a file has permanently failed processing
 * (corrupt scan, unreadable PDF) and retrying will never succeed. It lets the
 * rest of the batch complete without that file blocking REVIEW_PENDING forever.
 */
public enum FileStatus {
    PENDING,     // Awaiting processing
    PROCESSING,  // Currently being processed
    COMPLETED,   // Processing completed successfully
    ERROR,       // Processing failed — admin can retry or dismiss
    DISMISSED    // Admin accepted that this file cannot be processed; excluded from completion gate
}
