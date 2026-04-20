package com.apprisal.dto.python;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.Map;

/**
 * DTO mapping individual rule result from Python QC response.
 * Each rule (S-1, C-2, etc.) produces one of these.
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public class PythonRuleResult {

    @JsonProperty("rule_id")
    private String ruleId;

    @JsonProperty("rule_name")
    private String ruleName;

    private String status; // PASS, FAIL, VERIFY, WARNING, SYSTEM_ERROR, SKIPPED

    private String message;

    @JsonProperty("action_item")
    private String actionItem;

    private Map<String, Object> details;

    // Fields for reviewer UI comparison
    @JsonProperty("appraisal_value")
    private String appraisalValue;

    @JsonProperty("engagement_value")
    private String engagementValue;

    @JsonProperty("review_required")
    private boolean reviewRequired;

    // Getters and Setters
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

    public String getActionItem() {
        return actionItem;
    }

    public void setActionItem(String actionItem) {
        this.actionItem = actionItem;
    }

    public Map<String, Object> getDetails() {
        return details;
    }

    public void setDetails(Map<String, Object> details) {
        this.details = details;
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

    public boolean isReviewRequired() {
        return reviewRequired;
    }

    public void setReviewRequired(boolean reviewRequired) {
        this.reviewRequired = reviewRequired;
    }

    /**
     * Check if this rule requires human verification.
     * Uses Python's explicit flag OR infers from status.
     */
    public boolean needsVerification() {
        return reviewRequired || "VERIFY".equals(status) || "WARNING".equals(status) || "SYSTEM_ERROR".equals(status);
    }
}
