package com.shal.common.entity;

/**
 * Computed document/QC lifecycle state for an AppraisalTransaction (Order).
 * Unlike {@link TransactionStatus} (the AMC-facing SLA state), this reflects
 * "is this order's paperwork actually ready/done" and is written exclusively
 * by OrderStatusService — never set directly by a controller.
 */
public enum OrderDocumentStatus {
    INCOMPLETE,    // required document slots (appraisal + engagement) not all filled
    UNMATCHED,     // has a supporting file that couldn't be linked to a slot
    READY_FOR_QC,  // all required slots filled, no active QC run yet
    QC_PROCESSING, // QC currently running for this order's appraisal
    NEEDS_REVIEW,  // QC finished with items requiring reviewer decision
    COMPLETED,     // reviewer finalized, or QC auto-passed everything
    ERROR          // active document or QC result is in an error state
}
