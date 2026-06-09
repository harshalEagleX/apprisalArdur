package com.apprisal.common.entity;

import com.apprisal.common.util.AppTime;
import jakarta.persistence.*;
import java.time.LocalDateTime;

/**
 * QCRuleResult entity storing individual rule outcomes from Python QC
 * processing.
 *
 * Each rule (S-1, S-2, C-1, etc.) produces one QCRuleResult with:
 * - status: PASS, FAIL, VERIFY
 * - message: Detailed message from Python
 * - needsVerification: true for VERIFY/ERROR items
 * - reviewerVerified: null=pending, true=pass, false=fail
 *
 * @Audited intentionally removed: 137 machine-generated rows per QC job × Envers = 274 inserts.
 * Audit trail for rule results is captured via BusinessEvent (QC_RULE_EVALUATED) instead.
 */
@Entity
@Table(name = "qc_rule_result",
       indexes = {
           @Index(name = "idx_qc_rule_qcresult_id", columnList = "qc_result_id"),
           @Index(name = "idx_qc_rule_needs_verif", columnList = "qc_result_id, needs_verification"),
           @Index(name = "idx_qc_rule_status", columnList = "status")
       })
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

    // Authoritative report section from the Python engine (SUBJECT, CONTRACT,
    // SALES_COMPARISON, ...). Nullable for legacy rows; the API falls back to
    // deriving it from the rule-id prefix when absent.
    @Column(name = "section")
    private String section;

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

    @Column(name = "updated_at")
    private LocalDateTime updatedAt;

    // Comparison fields for reviewer UI
    @Column(name = "appraisal_value", columnDefinition = "TEXT")
    private String appraisalValue;

    @Column(name = "engagement_value", columnDefinition = "TEXT")
    private String engagementValue;

    // confidence_score is always populated — 0.0 means "not computed", not null.
    // columnDefinition ensures the DB column has a default so legacy rows survive.
    @Column(name = "confidence_score", nullable = false, columnDefinition = "DOUBLE PRECISION DEFAULT 0.0")
    private Double confidenceScore = 0.0d;

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

    @Column(name = "target_field")
    private String targetField;

    // Location fields: always populated via fillProcessingDefaults().
    // Reviewer auto-scroll depends on pdfPage > 0; bbox fields default to 0.0
    // to indicate "page is known but exact field box is unavailable".
    @Column(name = "pdf_page", nullable = false, columnDefinition = "INTEGER DEFAULT 0")
    private Integer pdfPage = 0;

    @Column(name = "bbox_x", nullable = false, columnDefinition = "REAL DEFAULT 0.0")
    private Float bboxX = 0.0f;

    @Column(name = "bbox_y", nullable = false, columnDefinition = "REAL DEFAULT 0.0")
    private Float bboxY = 0.0f;

    @Column(name = "bbox_w", nullable = false, columnDefinition = "REAL DEFAULT 0.0")
    private Float bboxW = 0.0f;

    @Column(name = "bbox_h", nullable = false, columnDefinition = "REAL DEFAULT 0.0")
    private Float bboxH = 0.0f;

    public QCRuleResult() {
    }

    @PrePersist
    protected void onCreate() {
        createdAt = AppTime.now();
        updatedAt = createdAt;
        fillProcessingDefaults();
    }

    @PreUpdate
    protected void onUpdate() {
        updatedAt = AppTime.now();
        fillProcessingDefaults();
    }

    private void fillProcessingDefaults() {
        ruleName = textOr(ruleName, textOr(ruleId, "UNKNOWN_RULE"));
        status = textOr(status, "SYSTEM_ERROR");
        message = textOr(message, "No rule message provided.");
        details = textOr(details, "{}");
        actionItem = textOr(actionItem, "No reviewer action required.");
        appraisalValue = textOr(appraisalValue, "__NO_APPRAISAL_VALUE__");
        engagementValue = textOr(engagementValue, "__NO_ENGAGEMENT_VALUE__");
        confidenceScore = confidenceScore != null ? confidenceScore : 0.0d;
        extractedValue = textOr(extractedValue, "__NO_EXTRACTED_VALUE__");
        expectedValue = textOr(expectedValue, "__NO_EXPECTED_VALUE__");
        verifyQuestion = textOr(verifyQuestion, "");
        rejectionText = textOr(rejectionText, "");
        evidence = textOr(evidence, "[]");
        reviewRequired = reviewRequired != null ? reviewRequired : false;
        severity = textOr(severity, "STANDARD");
        targetField = textOr(targetField, "checklist_rule");
        pdfPage = pdfPage != null ? pdfPage : 0;
        bboxX = bboxX != null ? bboxX : 0.0f;
        bboxY = bboxY != null ? bboxY : 0.0f;
        bboxW = bboxW != null ? bboxW : 0.0f;
        bboxH = bboxH != null ? bboxH : 0.0f;
    }

    private String textOr(String value, String fallback) {
        if (value == null || value.isBlank()) {
            return fallback;
        }
        return value;
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

    public String getSection() {
        return section;
    }

    public void setSection(String section) {
        this.section = section;
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

    public LocalDateTime getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(LocalDateTime updatedAt) { this.updatedAt = updatedAt; }

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

    public String getTargetField() {
        return targetField;
    }

    public void setTargetField(String targetField) {
        this.targetField = targetField;
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
        private String section;
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
        private String targetField;
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

        public QCRuleResultBuilder section(String section) {
            this.section = section;
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

        public QCRuleResultBuilder targetField(String targetField) {
            this.targetField = targetField;
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
            result.section = this.section;
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
            result.targetField = this.targetField;
            result.pdfPage = this.pdfPage;
            result.bboxX = this.bboxX;
            result.bboxY = this.bboxY;
            result.bboxW = this.bboxW;
            result.bboxH = this.bboxH;
            return result;
        }
    }
}
