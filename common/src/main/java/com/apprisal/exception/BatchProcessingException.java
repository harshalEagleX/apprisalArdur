package com.apprisal.exception;

/**
 * Exception thrown when batch processing fails.
 */
public class BatchProcessingException extends RuntimeException {
    private static final long serialVersionUID = 1L;

    private final Long batchId;

    public BatchProcessingException(String message) {
        super(message);
        this.batchId = null;
    }

    public BatchProcessingException(Long batchId, String message) {
        super(message);
        this.batchId = batchId;
    }

    public BatchProcessingException(Long batchId, String message, Throwable cause) {
        super(message, cause);
        this.batchId = batchId;
    }

    public Long getBatchId() {
        return batchId;
    }
}
