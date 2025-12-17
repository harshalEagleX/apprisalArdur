package com.apprisal.entity;

import jakarta.persistence.*;
import java.time.LocalDateTime;

/**
 * QCRuleResult entity storing individual rule outcomes from Python QC
 * processing.
 * 
 * Each rule (S-1, S-2, C-1, etc.) produces one QCRuleResult with:
 * - status: PASS, FAIL, WARNING, ERROR, SKIPPED
 * - message: Detailed message from Python
 * - needsVerification: true for WARNING/ERROR items
 * - reviewerVerified: null=pending, true=OK, false=rejected
 */
@Entity
@Table(name = "qc_rule_result")
public class QCRuleResult {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

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

    @Column(name = "created_at")
    private LocalDateTime createdAt;

    // Comparison fields for reviewer UI
    @Column(name = "appraisal_value", columnDefinition = "TEXT")
    private String appraisalValue;

    @Column(name = "engagement_value", columnDefinition = "TEXT")
    private String engagementValue;

    @Column(name = "review_required")
    private Boolean reviewRequired = false;

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

    public Boolean getReviewRequired() {
        return reviewRequired;
    }

    public void setReviewRequired(Boolean reviewRequired) {
        this.reviewRequired = reviewRequired;
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
        private Boolean reviewRequired = false;

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

        public QCRuleResultBuilder reviewRequired(Boolean reviewRequired) {
            this.reviewRequired = reviewRequired;
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
            result.reviewRequired = this.reviewRequired;
            return result;
        }
    }
}
