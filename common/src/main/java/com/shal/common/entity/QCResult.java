package com.shal.common.entity;

import com.shal.common.util.AppTime;
import jakarta.persistence.*;
import org.hibernate.envers.Audited;
import org.hibernate.envers.NotAudited;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;

/**
 * QCResult entity storing the outcome of Python QC processing for a BatchFile.
 *
 * Each appraisal file gets one QCResult with:
 * - qcDecision: AUTO_PASS, TO_VERIFY, or AUTO_FAIL (from Python rules)
 * - finalDecision: PASS or FAIL (after reviewer verification, if needed)
 * - Collection of QCRuleResults for individual rule outcomes
 *
 * @Audited: Envers writes ~4 revision rows per QC run (ADD on persist, MOD on each
 * status transition) inside the REQUIRES_NEW transaction in QCProcessingService.
 * The synchronous write cost (~5-10ms) is accepted because EnversAuditService now
 * actively reads these revisions for the audit graph's QC_RUN node drawer and the
 * getQCResultDiff() endpoint's auditTrail field — so the overhead has full return.
 * If the write latency ever becomes a problem, move to @AuditTable + async flush
 * rather than removing @Audited — the revision trail is operational data now.
 */
@Audited
@Entity
@Table(name = "qc_result",
       indexes = {
           @Index(name = "idx_qc_result_batchfile", columnList = "batch_file_id"),
           @Index(name = "idx_qc_result_decision", columnList = "qc_decision"),
           @Index(name = "idx_qc_result_final", columnList = "final_decision")
       })
public class QCResult {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    // A file accumulates MANY results over its lifetime (one per QC run); only the
    // newest is active. Must be @ManyToOne — @OneToOne makes Hibernate emit a plain
    // UNIQUE(batch_file_id) that blocks every rerun. DB uniqueness is instead a
    // PARTIAL index (uq_qc_result_batch_file_active WHERE superseded_at IS NULL) so
    // a new active result coexists with historical superseded ones.
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "batch_file_id", nullable = false)
    private BatchFile batchFile;

    @Enumerated(EnumType.STRING)
    @Column(name = "qc_decision", nullable = false)
    private QCDecision qcDecision;

    @Enumerated(EnumType.STRING)
    @Column(name = "final_decision")
    private FinalDecision finalDecision;

    // Full JSON blob from Python — excluded from Envers revision history (@NotAudited) because:
    //  1. It is large (1–20 KB per run) and write-once — auditing it would triple aud table size.
    //  2. The granular outcomes are already tracked in QCRuleResult rows.
    //  3. The raw blob is always recoverable from the live qc_result row (superseded runs are
    //     retained, not deleted) so no audit gap exists for dispute resolution.
    // If raw engine output auditing is ever required, write it to BusinessEvent payloadJson
    // (event type RAW_ENGINE_RESPONSE) rather than removing this @NotAudited annotation.
    @NotAudited
    @Column(name = "python_response", columnDefinition = "TEXT")
    private String pythonResponse;

    @Column(name = "total_rules")
    private Integer totalRules = 0;

    @Column(name = "passed_count")
    private Integer passedCount = 0;

    @Column(name = "failed_count")
    private Integer failedCount = 0;

    @Column(name = "verify_count")
    private Integer verifyCount = 0; // Items needing human verification

    @Column(name = "manual_pass_count")
    private Integer manualPassCount = 0; // Items manually accepted by reviewer

    @Column(name = "error_count")
    private Integer errorCount = 0;

    @Column(name = "processing_time_ms")
    private Integer processingTimeMs;

    @Column(name = "extraction_method")
    private String extractionMethod;

    // Version of the QC ruleset that produced this result ("qc-1.0.0+<fp>"). Lets
    // two runs be compared validly and attributes a flag delta to a rule change
    // vs a report change. Nullable for legacy rows.
    @Column(name = "rule_engine_version")
    private String ruleEngineVersion;

    @Column(name = "python_document_id")
    private String pythonDocumentId;

    @Column(name = "python_processing_job_id")
    private String pythonProcessingJobId;

    @Column(name = "cache_hit")
    private Boolean cacheHit = false;

    @Column(name = "missing_documents", columnDefinition = "TEXT")
    private String missingDocuments;

    // The subject property's address as EXTRACTED FROM THE DOCUMENT CONTENT (not
    // the filename), so the audit can anchor identity on what the appraisal is
    // actually about and search by it. Nullable for legacy rows / failed extraction.
    @Column(name = "subject_address")
    private String subjectAddress;

    @Column(name = "source_document_hash", length = 64)
    private String sourceDocumentHash;

    @Column(name = "source_document_version")
    private Long sourceDocumentVersion;

    /**
     * Points to the QCResult this run replaced.
     * Null for the first QC run on a file. Non-null when admin triggered a rerun.
     * The referenced result has supersededAt set to indicate it is historical.
     */
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "rerun_of")
    private QCResult rerunOf;

    /**
     * Non-null when this result has been superseded by a newer rerun.
     * Historical results are kept for audit purposes and are never deleted.
     */
    @Column(name = "superseded_at")
    private LocalDateTime supersededAt;

    @Column(name = "processed_at")
    private LocalDateTime processedAt;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "reviewed_by")
    private User reviewedBy;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "review_locked_by")
    private User reviewLockedBy;

    @Column(name = "review_session_token", length = 128)
    private String reviewSessionToken;

    @Column(name = "review_started_at")
    private LocalDateTime reviewStartedAt;

    @Column(name = "review_last_active_at")
    private LocalDateTime reviewLastActiveAt;

    @Column(name = "review_lock_expires_at")
    private LocalDateTime reviewLockExpiresAt;

    @Column(name = "review_lock_acknowledged")
    private Boolean reviewLockAcknowledged = false;

    @Column(name = "reviewed_at")
    private LocalDateTime reviewedAt;

    @Column(name = "reviewer_notes", columnDefinition = "TEXT")
    private String reviewerNotes;

    // QCRuleResult is @NotAudited (removed to avoid 137 Envers rows per QC run).
    // Envers requires @NotAudited on the owning side's collection when the target
    // entity is not audited. Rule outcome history is tracked via BusinessEvent instead.
    @NotAudited
    @OneToMany(mappedBy = "qcResult", cascade = CascadeType.ALL, orphanRemoval = true)
    private List<QCRuleResult> ruleResults = new ArrayList<>();

    @Column(name = "created_at")
    private LocalDateTime createdAt;

    @Column(name = "updated_at")
    private LocalDateTime updatedAt;

    public QCResult() {
    }

    @PrePersist
    protected void onCreate() {
        LocalDateTime now = AppTime.now();
        createdAt = now;
        updatedAt = now;
        if (processedAt == null) {
            processedAt = now;
        }
    }

    @PreUpdate
    protected void onUpdate() {
        updatedAt = AppTime.now();
    }

    // Helper method to add rule results
    public void addRuleResult(QCRuleResult ruleResult) {
        ruleResults.add(ruleResult);
        ruleResult.setQcResult(this);
    }

    /** True when this result has been replaced by a newer rerun. */
    public boolean isSuperseded() {
        return supersededAt != null;
    }

    public QCResult getRerunOf() { return rerunOf; }
    public void setRerunOf(QCResult rerunOf) { this.rerunOf = rerunOf; }

    public LocalDateTime getSupersededAt() { return supersededAt; }
    public void setSupersededAt(LocalDateTime supersededAt) { this.supersededAt = supersededAt; }

    // Getters and Setters
    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public BatchFile getBatchFile() {
        return batchFile;
    }

    public void setBatchFile(BatchFile batchFile) {
        this.batchFile = batchFile;
    }

    public QCDecision getQcDecision() {
        return qcDecision;
    }

    public void setQcDecision(QCDecision qcDecision) {
        this.qcDecision = qcDecision;
    }

    public FinalDecision getFinalDecision() {
        return finalDecision;
    }

    public void setFinalDecision(FinalDecision finalDecision) {
        this.finalDecision = finalDecision;
    }

    public String getPythonResponse() {
        return pythonResponse;
    }

    public void setPythonResponse(String pythonResponse) {
        this.pythonResponse = pythonResponse;
    }

    public Integer getTotalRules() {
        return totalRules;
    }

    public void setTotalRules(Integer totalRules) {
        this.totalRules = totalRules;
    }

    public Integer getPassedCount() {
        return passedCount;
    }

    public void setPassedCount(Integer passedCount) {
        this.passedCount = passedCount;
    }

    public Integer getFailedCount() {
        return failedCount;
    }

    public void setFailedCount(Integer failedCount) {
        this.failedCount = failedCount;
    }

    public Integer getVerifyCount() {
        return verifyCount;
    }

    public void setVerifyCount(Integer verifyCount) {
        this.verifyCount = verifyCount;
    }

    public Integer getManualPassCount() {
        return manualPassCount;
    }

    public void setManualPassCount(Integer manualPassCount) {
        this.manualPassCount = manualPassCount;
    }

    public Integer getErrorCount() {
        return errorCount;
    }

    public void setErrorCount(Integer errorCount) {
        this.errorCount = errorCount;
    }

    public Integer getProcessingTimeMs() {
        return processingTimeMs;
    }

    public void setProcessingTimeMs(Integer processingTimeMs) {
        this.processingTimeMs = processingTimeMs;
    }

    public String getExtractionMethod() { return extractionMethod; }
    public void setExtractionMethod(String extractionMethod) { this.extractionMethod = extractionMethod; }

    public String getRuleEngineVersion() { return ruleEngineVersion; }
    public void setRuleEngineVersion(String ruleEngineVersion) { this.ruleEngineVersion = ruleEngineVersion; }

    public String getPythonDocumentId() { return pythonDocumentId; }
    public void setPythonDocumentId(String pythonDocumentId) { this.pythonDocumentId = pythonDocumentId; }

    public String getPythonProcessingJobId() { return pythonProcessingJobId; }
    public void setPythonProcessingJobId(String pythonProcessingJobId) { this.pythonProcessingJobId = pythonProcessingJobId; }

    public Boolean getCacheHit() { return cacheHit; }
    public void setCacheHit(Boolean cacheHit) { this.cacheHit = cacheHit; }

    public String getMissingDocuments() { return missingDocuments; }
    public void setMissingDocuments(String missingDocuments) { this.missingDocuments = missingDocuments; }

    public String getSubjectAddress() { return subjectAddress; }
    public void setSubjectAddress(String subjectAddress) { this.subjectAddress = subjectAddress; }

    public String getSourceDocumentHash() { return sourceDocumentHash; }
    public void setSourceDocumentHash(String sourceDocumentHash) { this.sourceDocumentHash = sourceDocumentHash; }

    public Long getSourceDocumentVersion() { return sourceDocumentVersion; }
    public void setSourceDocumentVersion(Long sourceDocumentVersion) { this.sourceDocumentVersion = sourceDocumentVersion; }

    public LocalDateTime getProcessedAt() {
        return processedAt;
    }

    public void setProcessedAt(LocalDateTime processedAt) {
        this.processedAt = processedAt;
    }

    public User getReviewedBy() {
        return reviewedBy;
    }

    public void setReviewedBy(User reviewedBy) {
        this.reviewedBy = reviewedBy;
    }

    public User getReviewLockedBy() {
        return reviewLockedBy;
    }

    public void setReviewLockedBy(User reviewLockedBy) {
        this.reviewLockedBy = reviewLockedBy;
    }

    public String getReviewSessionToken() {
        return reviewSessionToken;
    }

    public void setReviewSessionToken(String reviewSessionToken) {
        this.reviewSessionToken = reviewSessionToken;
    }

    public LocalDateTime getReviewStartedAt() {
        return reviewStartedAt;
    }

    public void setReviewStartedAt(LocalDateTime reviewStartedAt) {
        this.reviewStartedAt = reviewStartedAt;
    }

    public LocalDateTime getReviewLastActiveAt() {
        return reviewLastActiveAt;
    }

    public void setReviewLastActiveAt(LocalDateTime reviewLastActiveAt) {
        this.reviewLastActiveAt = reviewLastActiveAt;
    }

    public LocalDateTime getReviewLockExpiresAt() {
        return reviewLockExpiresAt;
    }

    public void setReviewLockExpiresAt(LocalDateTime reviewLockExpiresAt) {
        this.reviewLockExpiresAt = reviewLockExpiresAt;
    }

    public Boolean getReviewLockAcknowledged() {
        return reviewLockAcknowledged;
    }

    public void setReviewLockAcknowledged(Boolean reviewLockAcknowledged) {
        this.reviewLockAcknowledged = reviewLockAcknowledged;
    }

    public LocalDateTime getReviewedAt() {
        return reviewedAt;
    }

    public void setReviewedAt(LocalDateTime reviewedAt) {
        this.reviewedAt = reviewedAt;
    }

    public String getReviewerNotes() {
        return reviewerNotes;
    }

    public void setReviewerNotes(String reviewerNotes) {
        this.reviewerNotes = reviewerNotes;
    }

    public List<QCRuleResult> getRuleResults() {
        return ruleResults;
    }

    public void setRuleResults(List<QCRuleResult> ruleResults) {
        this.ruleResults = ruleResults;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public LocalDateTime getUpdatedAt() {
        return updatedAt;
    }

    // Builder pattern
    public static QCResultBuilder builder() {
        return new QCResultBuilder();
    }

    public static class QCResultBuilder {
        private BatchFile batchFile;
        private QCDecision qcDecision;
        private String pythonResponse;
        private Integer totalRules = 0;
        private Integer passedCount = 0;
        private Integer failedCount = 0;
        private Integer verifyCount = 0;
        private Integer manualPassCount = 0;
        private Integer errorCount = 0;
        private Integer processingTimeMs;
        private String  extractionMethod;
        private String  ruleEngineVersion;
        private String  pythonDocumentId;      // IMPL FIX: was missing from builder
        private String  pythonProcessingJobId;
        private Boolean cacheHit = false;      // IMPL FIX: was missing from builder
        private String missingDocuments;
        private String subjectAddress;
        private String sourceDocumentHash;
        private Long sourceDocumentVersion;

        public QCResultBuilder batchFile(BatchFile batchFile) {
            this.batchFile = batchFile;
            return this;
        }

        public QCResultBuilder qcDecision(QCDecision qcDecision) {
            this.qcDecision = qcDecision;
            return this;
        }

        public QCResultBuilder pythonResponse(String pythonResponse) {
            this.pythonResponse = pythonResponse;
            return this;
        }

        public QCResultBuilder totalRules(Integer totalRules) {
            this.totalRules = totalRules;
            return this;
        }

        public QCResultBuilder passedCount(Integer passedCount) {
            this.passedCount = passedCount;
            return this;
        }

        public QCResultBuilder failedCount(Integer failedCount) {
            this.failedCount = failedCount;
            return this;
        }

        public QCResultBuilder verifyCount(Integer verifyCount) {
            this.verifyCount = verifyCount;
            return this;
        }

        public QCResultBuilder manualPassCount(Integer manualPassCount) {
            this.manualPassCount = manualPassCount;
            return this;
        }

        public QCResultBuilder errorCount(Integer errorCount) {
            this.errorCount = errorCount;
            return this;
        }

        public QCResultBuilder processingTimeMs(Integer processingTimeMs) {
            this.processingTimeMs = processingTimeMs;
            return this;
        }

        public QCResultBuilder extractionMethod(String v)   { this.extractionMethod = v; return this; }
        public QCResultBuilder ruleEngineVersion(String v)  { this.ruleEngineVersion = v; return this; }
        public QCResultBuilder pythonDocumentId(String v)   { this.pythonDocumentId = v; return this; }
        public QCResultBuilder pythonProcessingJobId(String v) { this.pythonProcessingJobId = v; return this; }
        public QCResultBuilder cacheHit(Boolean v)          { this.cacheHit = v;          return this; }
        public QCResultBuilder missingDocuments(String v)   { this.missingDocuments = v; return this; }
        public QCResultBuilder subjectAddress(String v)     { this.subjectAddress = v; return this; }
        public QCResultBuilder sourceDocumentHash(String v) { this.sourceDocumentHash = v; return this; }
        public QCResultBuilder sourceDocumentVersion(Long v){ this.sourceDocumentVersion = v; return this; }

        public QCResult build() {
            QCResult result = new QCResult();
            result.batchFile       = this.batchFile;
            result.qcDecision      = this.qcDecision;
            result.pythonResponse  = this.pythonResponse;
            result.totalRules      = this.totalRules;
            result.passedCount     = this.passedCount;
            result.failedCount     = this.failedCount;
            result.verifyCount     = this.verifyCount;
            result.manualPassCount = this.manualPassCount;
            result.errorCount      = this.errorCount;
            result.processingTimeMs = this.processingTimeMs;
            result.extractionMethod = this.extractionMethod;
            result.ruleEngineVersion = this.ruleEngineVersion;
            result.pythonDocumentId = this.pythonDocumentId;
            result.pythonProcessingJobId = this.pythonProcessingJobId;
            result.cacheHit         = this.cacheHit;
            result.missingDocuments = this.missingDocuments;
            result.subjectAddress = this.subjectAddress;
            result.sourceDocumentHash = this.sourceDocumentHash;
            result.sourceDocumentVersion = this.sourceDocumentVersion;
            return result;
        }
    }
}
