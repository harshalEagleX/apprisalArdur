package com.apprisal.common.entity;

import jakarta.persistence.*;
import org.hibernate.envers.Audited;
import java.time.LocalDateTime;

/**
 * QCRuleResult entity storing individual rule outcomes from Python QC
 * processing.
 * 
 * Each rule (S-1, S-2, C-1, etc.) produces one QCRuleResult with:
 * - status: PASS, FAIL, VERIFY, ERROR, SKIPPED
 * - message: Detailed message from Python
 * - needsVerification: true for VERIFY/ERROR items
 * - reviewerVerified: null=pending, true=pass, false=fail
 */
@Audited
@Entity
@Table(name = "qc_rule_result")
public class QCRuleResult {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    @Column(name = "version")
    private Long version = 0L;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "qc_result_id", nullable = false)
    private QCResult qcResult;

    @Column(name = "rule_id", nullable = false)
    private String ruleId;

    @Column(name = "rule_name")
    private String ruleName;

    @Column(nullable = false)
    private String status;

    @Column(columnDefinition = "TEXT")
    private String message;

    @Column(columnDefinition = "TEXT")
    private String details;

    @Column(name = "action_item", columnDefinition = "TEXT")
    private String actionItem;

    @Column(name = "needs_verification")
    private Boolean needsVerification = false;

    @Column(name = "reviewer_verified")
    private Boolean reviewerVerified;

    @Column(name = "reviewer_comment", columnDefinition = "TEXT")
    private String reviewerComment;

    @Column(name = "verified_at")
    private LocalDateTime verifiedAt;

    @Column(name = "review_session_token", length = 128)
    private String reviewSessionToken;

    @Column(name = "first_presented_at")
    private LocalDateTime firstPresentedAt;

    @Column(name = "decision_latency_ms")
    private Long decisionLatencyMs;

    @Column(name = "acknowledged_references")
    private Boolean acknowledgedReferences = false;

    @Column(name = "override_pending")
    private Boolean overridePending = false;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "override_requested_by")
    private User overrideRequestedBy;

    @Column(name = "override_requested_at")
    private LocalDateTime overrideRequestedAt;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "override_approved_by")
    private User overrideApprovedBy;

    @Column(name = "override_approved_at")
    private LocalDateTime overrideApprovedAt;

    @Column(name = "created_at")
    private LocalDateTime createdAt;

    // Comparison fields for reviewer UI
    @Column(name = "appraisal_value", columnDefinition = "TEXT")
    private String appraisalValue;

    @Column(name = "engagement_value", columnDefinition = "TEXT")
    private String engagementValue;

    @Column(name = "confidence_score")
    private Double confidenceScore;

    @Column(name = "extracted_value", columnDefinition = "TEXT")
    private String extractedValue;

    @Column(name = "expected_value", columnDefinition = "TEXT")
    private String expectedValue;

    @Column(name = "verify_question", columnDefinition = "TEXT")
    private String verifyQuestion;

    @Column(name = "rejection_text", columnDefinition = "TEXT")
    private String rejectionText;

    @Column(name = "evidence", columnDefinition = "TEXT")
    private String evidence;

    @Column(name = "review_required")
    private Boolean reviewRequired = false;

    @Column(name = "severity")
    private String severity = "STANDARD"; // BLOCKING | STANDARD | ADVISORY

    @Column(name = "pdf_page")
    private Integer pdfPage;

    @Column(name = "bbox_x")
    private Float bboxX;

    @Column(name = "bbox_y")
    private Float bboxY;

    @Column(name = "bbox_w")
    private Float bboxW;

    @Column(name = "bbox_h")
    private Float bboxH;

    public QCRuleResult() {
    }

    @PrePersist
    protected void onCreate() {
        createdAt = LocalDateTime.now();
    }

    // Getters and Setters
    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public Long getVersion() {
        return version;
    }

    public void setVersion(Long version) {
        this.version = version;
    }

    public QCResult getQcResult() {
        return qcResult;
    }

    public void setQcResult(QCResult qcResult) {
        this.qcResult = qcResult;
    }

    public String getRuleId() {
        return ruleId;
    }

    public void setRuleId(String ruleId) {
        this.ruleId = ruleId;
    }

    public String getRuleName() {
        return ruleName;
    }

    public void setRuleName(String ruleName) {
        this.ruleName = ruleName;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public String getMessage() {
        return message;
    }

    public void setMessage(String message) {
        this.message = message;
    }

    public String getDetails() {
        return details;
    }

    public void setDetails(String details) {
        this.details = details;
    }

    public String getActionItem() {
        return actionItem;
    }

    public void setActionItem(String actionItem) {
        this.actionItem = actionItem;
    }

    public Boolean getNeedsVerification() {
        return needsVerification;
    }

    public void setNeedsVerification(Boolean needsVerification) {
        this.needsVerification = needsVerification;
    }

    public Boolean getReviewerVerified() {
        return reviewerVerified;
    }

    public void setReviewerVerified(Boolean reviewerVerified) {
        this.reviewerVerified = reviewerVerified;
    }

    public String getReviewerComment() {
        return reviewerComment;
    }

    public void setReviewerComment(String reviewerComment) {
        this.reviewerComment = reviewerComment;
    }

    public LocalDateTime getVerifiedAt() {
        return verifiedAt;
    }

    public void setVerifiedAt(LocalDateTime verifiedAt) {
        this.verifiedAt = verifiedAt;
    }

    public String getReviewSessionToken() {
        return reviewSessionToken;
    }

    public void setReviewSessionToken(String reviewSessionToken) {
        this.reviewSessionToken = reviewSessionToken;
    }

    public LocalDateTime getFirstPresentedAt() {
        return firstPresentedAt;
    }

    public void setFirstPresentedAt(LocalDateTime firstPresentedAt) {
        this.firstPresentedAt = firstPresentedAt;
    }

    public Long getDecisionLatencyMs() {
        return decisionLatencyMs;
    }

    public void setDecisionLatencyMs(Long decisionLatencyMs) {
        this.decisionLatencyMs = decisionLatencyMs;
    }

    public Boolean getAcknowledgedReferences() {
        return acknowledgedReferences;
    }

    public void setAcknowledgedReferences(Boolean acknowledgedReferences) {
        this.acknowledgedReferences = acknowledgedReferences;
    }

    public Boolean getOverridePending() {
        return overridePending;
    }

    public void setOverridePending(Boolean overridePending) {
        this.overridePending = overridePending;
    }

    public User getOverrideRequestedBy() {
        return overrideRequestedBy;
    }

    public void setOverrideRequestedBy(User overrideRequestedBy) {
        this.overrideRequestedBy = overrideRequestedBy;
    }

    public LocalDateTime getOverrideRequestedAt() {
        return overrideRequestedAt;
    }

    public void setOverrideRequestedAt(LocalDateTime overrideRequestedAt) {
        this.overrideRequestedAt = overrideRequestedAt;
    }

    public User getOverrideApprovedBy() {
        return overrideApprovedBy;
    }

    public void setOverrideApprovedBy(User overrideApprovedBy) {
        this.overrideApprovedBy = overrideApprovedBy;
    }

    public LocalDateTime getOverrideApprovedAt() {
        return overrideApprovedAt;
    }

    public void setOverrideApprovedAt(LocalDateTime overrideApprovedAt) {
        this.overrideApprovedAt = overrideApprovedAt;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public String getAppraisalValue() {
        return appraisalValue;
    }

    public void setAppraisalValue(String appraisalValue) {
        this.appraisalValue = appraisalValue;
    }

    public String getEngagementValue() {
        return engagementValue;
    }

    public void setEngagementValue(String engagementValue) {
        this.engagementValue = engagementValue;
    }

    public Double getConfidenceScore() {
        return confidenceScore;
    }

    public void setConfidenceScore(Double confidenceScore) {
        this.confidenceScore = confidenceScore;
    }

    public String getExtractedValue() {
        return extractedValue;
    }

    public void setExtractedValue(String extractedValue) {
        this.extractedValue = extractedValue;
    }

    public String getExpectedValue() {
        return expectedValue;
    }

    public void setExpectedValue(String expectedValue) {
        this.expectedValue = expectedValue;
    }

    public String getVerifyQuestion() {
        return verifyQuestion;
    }

    public void setVerifyQuestion(String verifyQuestion) {
        this.verifyQuestion = verifyQuestion;
    }

    public String getRejectionText() {
        return rejectionText;
    }

    public void setRejectionText(String rejectionText) {
        this.rejectionText = rejectionText;
    }

    public String getEvidence() {
        return evidence;
    }

    public void setEvidence(String evidence) {
        this.evidence = evidence;
    }

    public Boolean getReviewRequired() {
        return reviewRequired;
    }

    public void setReviewRequired(Boolean reviewRequired) {
        this.reviewRequired = reviewRequired;
    }

    public String getSeverity() {
        return severity;
    }

    public void setSeverity(String severity) {
        this.severity = severity;
    }

    public Integer getPdfPage() {
        return pdfPage;
    }

    public void setPdfPage(Integer pdfPage) {
        this.pdfPage = pdfPage;
    }

    public Float getBboxX() {
        return bboxX;
    }

    public void setBboxX(Float bboxX) {
        this.bboxX = bboxX;
    }

    public Float getBboxY() {
        return bboxY;
    }

    public void setBboxY(Float bboxY) {
        this.bboxY = bboxY;
    }

    public Float getBboxW() {
        return bboxW;
    }

    public void setBboxW(Float bboxW) {
        this.bboxW = bboxW;
    }

    public Float getBboxH() {
        return bboxH;
    }

    public void setBboxH(Float bboxH) {
        this.bboxH = bboxH;
    }

    // Builder pattern
    public static QCRuleResultBuilder builder() {
        return new QCRuleResultBuilder();
    }

    public static class QCRuleResultBuilder {
        private QCResult qcResult;
        private String ruleId;
        private String ruleName;
        private String status;
        private String message;
        private String details;
        private String actionItem;
        private Boolean needsVerification = false;
        private String appraisalValue;
        private String engagementValue;
        private Double confidenceScore;
        private String extractedValue;
        private String expectedValue;
        private String verifyQuestion;
        private String rejectionText;
        private String evidence;
        private Boolean reviewRequired = false;
        private String severity = "STANDARD";
        private Integer pdfPage;
        private Float bboxX;
        private Float bboxY;
        private Float bboxW;
        private Float bboxH;

        public QCRuleResultBuilder qcResult(QCResult qcResult) {
            this.qcResult = qcResult;
            return this;
        }

        public QCRuleResultBuilder ruleId(String ruleId) {
            this.ruleId = ruleId;
            return this;
        }

        public QCRuleResultBuilder ruleName(String ruleName) {
            this.ruleName = ruleName;
            return this;
        }

        public QCRuleResultBuilder status(String status) {
            this.status = status;
            return this;
        }

        public QCRuleResultBuilder message(String message) {
            this.message = message;
            return this;
        }

        public QCRuleResultBuilder details(String details) {
            this.details = details;
            return this;
        }

        public QCRuleResultBuilder actionItem(String actionItem) {
            this.actionItem = actionItem;
            return this;
        }

        public QCRuleResultBuilder needsVerification(Boolean needsVerification) {
            this.needsVerification = needsVerification;
            return this;
        }

        public QCRuleResultBuilder appraisalValue(String appraisalValue) {
            this.appraisalValue = appraisalValue;
            return this;
        }

        public QCRuleResultBuilder engagementValue(String engagementValue) {
            this.engagementValue = engagementValue;
            return this;
        }

        public QCRuleResultBuilder confidenceScore(Double confidenceScore) {
            this.confidenceScore = confidenceScore;
            return this;
        }

        public QCRuleResultBuilder extractedValue(String extractedValue) {
            this.extractedValue = extractedValue;
            return this;
        }

        public QCRuleResultBuilder expectedValue(String expectedValue) {
            this.expectedValue = expectedValue;
            return this;
        }

        public QCRuleResultBuilder verifyQuestion(String verifyQuestion) {
            this.verifyQuestion = verifyQuestion;
            return this;
        }

        public QCRuleResultBuilder rejectionText(String rejectionText) {
            this.rejectionText = rejectionText;
            return this;
        }

        public QCRuleResultBuilder evidence(String evidence) {
            this.evidence = evidence;
            return this;
        }

        public QCRuleResultBuilder reviewRequired(Boolean reviewRequired) {
            this.reviewRequired = reviewRequired;
            return this;
        }

        public QCRuleResultBuilder severity(String severity) {
            this.severity = severity;
            return this;
        }

        public QCRuleResultBuilder pdfPage(Integer pdfPage) {
            this.pdfPage = pdfPage;
            return this;
        }

        public QCRuleResultBuilder bboxX(Float bboxX) {
            this.bboxX = bboxX;
            return this;
        }

        public QCRuleResultBuilder bboxY(Float bboxY) {
            this.bboxY = bboxY;
            return this;
        }

        public QCRuleResultBuilder bboxW(Float bboxW) {
            this.bboxW = bboxW;
            return this;
        }

        public QCRuleResultBuilder bboxH(Float bboxH) {
            this.bboxH = bboxH;
            return this;
        }

        public QCRuleResult build() {
            QCRuleResult result = new QCRuleResult();
            result.qcResult = this.qcResult;
            result.ruleId = this.ruleId;
            result.ruleName = this.ruleName;
            result.status = this.status;
            result.message = this.message;
            result.details = this.details;
            result.actionItem = this.actionItem;
            result.needsVerification = this.needsVerification;
            result.appraisalValue = this.appraisalValue;
            result.engagementValue = this.engagementValue;
            result.confidenceScore = this.confidenceScore;
            result.extractedValue = this.extractedValue;
            result.expectedValue = this.expectedValue;
            result.verifyQuestion = this.verifyQuestion;
            result.rejectionText = this.rejectionText;
            result.evidence = this.evidence;
            result.reviewRequired = this.reviewRequired;
            result.severity = this.severity;
            result.pdfPage = this.pdfPage;
            result.bboxX = this.bboxX;
            result.bboxY = this.bboxY;
            result.bboxW = this.bboxW;
            result.bboxH = this.bboxH;
            return result;
        }
    }
}
