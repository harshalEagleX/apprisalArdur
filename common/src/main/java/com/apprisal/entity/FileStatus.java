package com.apprisal.entity;

/**
 * File processing status enum.
 */
public enum FileStatus {
    PENDING, // Awaiting processing
    PROCESSING, // Currently being processed
    COMPLETED, // Processing completed successfully
    ERROR // Processing failed
}
