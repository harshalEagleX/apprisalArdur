package com.apprisal.entity;

import jakarta.persistence.*;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;

import org.hibernate.envers.Audited;

/**
 * QCResult entity storing the outcome of Python QC processing for a BatchFile.
 * 
 * Each appraisal file gets one QCResult with:
 * - qcDecision: AUTO_PASS, TO_VERIFY, or AUTO_FAIL (from Python rules)
 * - finalDecision: PASS or FAIL (after reviewer verification, if needed)
 * - Collection of QCRuleResults for individual rule outcomes
 */
@Entity
@Audited
@Table(name = "qc_result")
public class QCResult extends BaseEntity {

    @OneToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "batch_file_id", nullable = false)
    private BatchFile batchFile;

    @Enumerated(EnumType.STRING)
    @Column(name = "qc_decision", nullable = false)
    private QCDecision qcDecision;

    @Enumerated(EnumType.STRING)
    @Column(name = "final_decision")
    private FinalDecision finalDecision;

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

    @Column(name = "warning_count")
    private Integer warningCount = 0;

    @Column(name = "error_count")
    private Integer errorCount = 0;

    @Column(name = "skipped_count")
    private Integer skippedCount = 0;

    @Column(name = "processing_time_ms")
    private Integer processingTimeMs;

    @Column(name = "extraction_method")
    private String extractionMethod;

    @Column(name = "processed_at")
    private LocalDateTime processedAt;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "reviewed_by")
    private User reviewedBy;

    @Column(name = "reviewed_at")
    private LocalDateTime reviewedAt;

    @Column(name = "reviewer_notes", columnDefinition = "TEXT")
    private String reviewerNotes;

    @OneToMany(mappedBy = "qcResult", cascade = CascadeType.ALL, orphanRemoval = true)
    private List<QCRuleResult> ruleResults = new ArrayList<>();

    public QCResult() {
    }

    @PrePersist
    @Override
    protected void onCreate() {
        super.onCreate();
        if (processedAt == null) {
            processedAt = LocalDateTime.now();
        }
    }

    // Helper method to add rule results
    public void addRuleResult(QCRuleResult ruleResult) {
        ruleResults.add(ruleResult);
        ruleResult.setQcResult(this);
    }

    // Getters and Setters
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

    public Integer getWarningCount() {
        return warningCount;
    }

    public void setWarningCount(Integer warningCount) {
        this.warningCount = warningCount;
    }

    public Integer getErrorCount() {
        return errorCount;
    }

    public void setErrorCount(Integer errorCount) {
        this.errorCount = errorCount;
    }

    public Integer getSkippedCount() {
        return skippedCount;
    }

    public void setSkippedCount(Integer skippedCount) {
        this.skippedCount = skippedCount;
    }

    public Integer getProcessingTimeMs() {
        return processingTimeMs;
    }

    public void setProcessingTimeMs(Integer processingTimeMs) {
        this.processingTimeMs = processingTimeMs;
    }

    public String getExtractionMethod() {
        return extractionMethod;
    }

    public void setExtractionMethod(String extractionMethod) {
        this.extractionMethod = extractionMethod;
    }

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
        private Integer warningCount = 0;
        private Integer errorCount = 0;
        private Integer skippedCount = 0;
        private Integer processingTimeMs;
        private String extractionMethod;

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

        public QCResultBuilder warningCount(Integer warningCount) {
            this.warningCount = warningCount;
            return this;
        }

        public QCResultBuilder errorCount(Integer errorCount) {
            this.errorCount = errorCount;
            return this;
        }

        public QCResultBuilder skippedCount(Integer skippedCount) {
            this.skippedCount = skippedCount;
            return this;
        }

        public QCResultBuilder processingTimeMs(Integer processingTimeMs) {
            this.processingTimeMs = processingTimeMs;
            return this;
        }

        public QCResultBuilder extractionMethod(String extractionMethod) {
            this.extractionMethod = extractionMethod;
            return this;
        }

        public QCResult build() {
            QCResult result = new QCResult();
            result.batchFile = this.batchFile;
            result.qcDecision = this.qcDecision;
            result.pythonResponse = this.pythonResponse;
            result.totalRules = this.totalRules;
            result.passedCount = this.passedCount;
            result.failedCount = this.failedCount;
            result.verifyCount = this.verifyCount;
            result.manualPassCount = this.manualPassCount;
            result.warningCount = this.warningCount;
            result.errorCount = this.errorCount;
            result.skippedCount = this.skippedCount;
            result.processingTimeMs = this.processingTimeMs;
            result.extractionMethod = this.extractionMethod;
            return result;
        }
    }
}
