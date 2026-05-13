package com.apprisal.common.dto;

import com.apprisal.common.entity.BatchStatus;
import java.time.LocalDateTime;

/**
 * Projection used by the status polling endpoint — fetches batch + two counts in one query
 * instead of three separate DB round trips.
 */
public interface BatchStatusView {
    Long getBatchId();
    BatchStatus getStatus();
    String getErrorMessage();
    LocalDateTime getUpdatedAt();
    Long getTotalFiles();
    Long getProcessingTotalFiles();
    Long getCompletedFiles();
}
