package com.shal.common.entity;

/**
 * Lifecycle states for an AppraisalTransaction — one AMC order that may span
 * multiple SHAL batches (original submission + any revisions).
 *
 * RECEIVED          → SUBMITTED
 * SUBMITTED         → AWAITING_REVISION | RESOLVED
 * AWAITING_REVISION → SUBMITTED (revision comes back) | ABANDONED
 */
public enum TransactionStatus {
    RECEIVED,          // intake manifest created, not yet uploaded to SHAL
    SUBMITTED,         // at least one batch exists under this transaction
    AWAITING_REVISION, // latest batch rejected; waiting for AMC to resubmit
    RESOLVED,          // a batch completed clean; order is done
    ABANDONED          // AMC went quiet past the SLA deadline
}
