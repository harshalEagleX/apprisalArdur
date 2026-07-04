package com.shal.common.entity;

import com.shal.common.util.AppTime;
import jakarta.persistence.*;
import org.hibernate.envers.Audited;

import java.time.LocalDateTime;

/**
 * One AMC appraisal order — a transaction that may span multiple SHAL batches
 * (original submission + revisions).  The transaction exists one layer above
 * the Batch: a batch belongs to a transaction; a transaction survives across
 * multiple submission rounds.
 *
 * Key invariants:
 *  - transaction_id is the stable reference shared across intake email, SHAL
 *    batches, rejection letters, and revision submissions.
 *  - revised_from_id links a revision transaction back to the original.
 *  - received_at / submitted_at / revision_sent_at / closed_at form the
 *    three-timestamp tuple from which turnaround metrics are computed.
 */
@Audited
@Entity
@Table(name = "appraisal_transaction",
       indexes = {
           @Index(name = "idx_txn_amc_order", columnList = "amc_code, order_number"),
           @Index(name = "idx_txn_status", columnList = "status"),
           @Index(name = "idx_txn_revised_from", columnList = "revised_from_id")
       })
public class AppraisalTransaction {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    /**
     * Human-readable stable ID assigned at intake (e.g. "AMC001-LN20240601-001").
     * Appears in rejection emails and revision zips so the AMC can reference it.
     */
    @Column(name = "transaction_ref", length = 100, nullable = false, unique = true)
    private String transactionRef;

    @Column(name = "amc_code", length = 100)
    private String amcCode;

    @Column(name = "order_number", length = 100)
    private String orderNumber;

    @Column(name = "property_address", length = 500)
    private String propertyAddress;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "client_id")
    private Client client;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private TransactionStatus status = TransactionStatus.RECEIVED;

    /**
     * Computed document/QC lifecycle state — written only by OrderStatusService,
     * never set directly. See {@link OrderDocumentStatus}.
     */
    @Enumerated(EnumType.STRING)
    @Column(name = "document_status", nullable = false)
    private OrderDocumentStatus documentStatus = OrderDocumentStatus.INCOMPLETE;

    /** When this is a revision, points to the original (or previous) transaction. */
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "revised_from_id")
    private AppraisalTransaction revisedFrom;

    /** Revision round number — 0 = original submission. */
    @Column(name = "revision_number", nullable = false)
    private Integer revisionNumber = 0;

    /** Timestamp of intake (email/manifest received). */
    @Column(name = "received_at")
    private LocalDateTime receivedAt;

    /** When the first batch under this transaction was uploaded. */
    @Column(name = "submitted_at")
    private LocalDateTime submittedAt;

    /** When a rejection letter was sent to the AMC for the latest batch. */
    @Column(name = "revision_sent_at")
    private LocalDateTime revisionSentAt;

    /** When the transaction reached RESOLVED or ABANDONED. */
    @Column(name = "closed_at")
    private LocalDateTime closedAt;

    /** SLA due date set at intake. */
    @Column(name = "sla_due_at")
    private LocalDateTime slaDueAt;

    /**
     * Reviewer this Order is allocated to. Assignment is per-Order (not per-batch): a
     * single ZIP can carry dozens of orders, so each order is allocated to a reviewer
     * independently rather than routing an entire batch to one person.
     */
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "assigned_reviewer_id")
    private User assignedReviewer;

    @Column(name = "reviewer_assigned_at")
    private LocalDateTime reviewerAssignedAt;

    @Column(name = "created_at")
    private LocalDateTime createdAt;

    @Column(name = "updated_at")
    private LocalDateTime updatedAt;

    @PrePersist
    protected void onCreate() {
        LocalDateTime now = AppTime.now();
        createdAt = now;
        updatedAt = now;
        if (receivedAt == null) receivedAt = now;
    }

    @PreUpdate
    protected void onUpdate() {
        updatedAt = AppTime.now();
    }

    // ── Getters / Setters ────────────────────────────────────────────────────

    public Long getId() { return id; }

    public String getTransactionRef() { return transactionRef; }
    public void setTransactionRef(String transactionRef) { this.transactionRef = transactionRef; }

    public String getAmcCode() { return amcCode; }
    public void setAmcCode(String amcCode) { this.amcCode = amcCode; }

    public String getOrderNumber() { return orderNumber; }
    public void setOrderNumber(String orderNumber) { this.orderNumber = orderNumber; }

    public String getPropertyAddress() { return propertyAddress; }
    public void setPropertyAddress(String propertyAddress) { this.propertyAddress = propertyAddress; }

    public Client getClient() { return client; }
    public void setClient(Client client) { this.client = client; }

    public TransactionStatus getStatus() { return status; }
    public void setStatus(TransactionStatus status) { this.status = status; }

    public OrderDocumentStatus getDocumentStatus() { return documentStatus; }
    public void setDocumentStatus(OrderDocumentStatus documentStatus) { this.documentStatus = documentStatus; }

    public AppraisalTransaction getRevisedFrom() { return revisedFrom; }
    public void setRevisedFrom(AppraisalTransaction revisedFrom) { this.revisedFrom = revisedFrom; }

    public Integer getRevisionNumber() { return revisionNumber; }
    public void setRevisionNumber(Integer revisionNumber) { this.revisionNumber = revisionNumber; }

    public LocalDateTime getReceivedAt() { return receivedAt; }
    public void setReceivedAt(LocalDateTime receivedAt) { this.receivedAt = receivedAt; }

    public LocalDateTime getSubmittedAt() { return submittedAt; }
    public void setSubmittedAt(LocalDateTime submittedAt) { this.submittedAt = submittedAt; }

    public LocalDateTime getRevisionSentAt() { return revisionSentAt; }
    public void setRevisionSentAt(LocalDateTime revisionSentAt) { this.revisionSentAt = revisionSentAt; }

    public LocalDateTime getClosedAt() { return closedAt; }
    public void setClosedAt(LocalDateTime closedAt) { this.closedAt = closedAt; }

    public LocalDateTime getSlaDueAt() { return slaDueAt; }
    public void setSlaDueAt(LocalDateTime slaDueAt) { this.slaDueAt = slaDueAt; }

    public User getAssignedReviewer() { return assignedReviewer; }
    public void setAssignedReviewer(User assignedReviewer) { this.assignedReviewer = assignedReviewer; }

    public LocalDateTime getReviewerAssignedAt() { return reviewerAssignedAt; }
    public void setReviewerAssignedAt(LocalDateTime reviewerAssignedAt) { this.reviewerAssignedAt = reviewerAssignedAt; }

    public LocalDateTime getCreatedAt() { return createdAt; }
    public LocalDateTime getUpdatedAt() { return updatedAt; }
}
