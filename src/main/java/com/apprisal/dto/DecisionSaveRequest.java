package com.apprisal.dto;

/**
 * Request DTO for saving a reviewer decision via AJAX auto-save.
 */
public class DecisionSaveRequest {

    private Long ruleResultId;
    private String decision; // "ACCEPT" or "REJECT"
    private String comment;

    public DecisionSaveRequest() {
    }

    public DecisionSaveRequest(Long ruleResultId, String decision, String comment) {
        this.ruleResultId = ruleResultId;
        this.decision = decision;
        this.comment = comment;
    }

    public Long getRuleResultId() {
        return ruleResultId;
    }

    public void setRuleResultId(Long ruleResultId) {
        this.ruleResultId = ruleResultId;
    }

    public String getDecision() {
        return decision;
    }

    public void setDecision(String decision) {
        this.decision = decision;
    }

    public String getComment() {
        return comment;
    }

    public void setComment(String comment) {
        this.comment = comment;
    }
}
