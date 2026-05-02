package com.apprisal.common.dto.python;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.Map;

/**
 * Maps a single rule result from the Python /qc/process response.
 * Each rule (S-1, C-2, COM-1, etc.) produces one of these.
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record PythonRuleResult(
        @JsonProperty("rule_id")       String ruleId,
        @JsonProperty("rule_name")     String ruleName,
        String status,
        String message,
        @JsonProperty("severity")      String severity,
        @JsonProperty("action_item")   String actionItem,
        Map<String, Object> details,
        @JsonProperty("appraisal_value")  String appraisalValue,
        @JsonProperty("engagement_value") String engagementValue,
        Double confidence,
        @JsonProperty("extracted_value")  Object extractedValue,
        @JsonProperty("expected_value")   Object expectedValue,
        @JsonProperty("verify_question")  String verifyQuestion,
        @JsonProperty("rejection_text")   String rejectionText,
        @JsonProperty("evidence")         java.util.List<String> evidence,
        @JsonProperty("review_required")  boolean reviewRequired,
        @JsonProperty("source_page")      Integer sourcePage,
        @JsonProperty("bbox_x")           Float bboxX,
        @JsonProperty("bbox_y")           Float bboxY,
        @JsonProperty("bbox_w")           Float bboxW,
        @JsonProperty("bbox_h")           Float bboxH
) {
    /** True when this rule result requires a human reviewer to make a decision. */
    public boolean needsVerification() {
        String normalizedStatus = status == null ? "" : status.trim().toLowerCase();
        return reviewRequired
                || "fail".equals(normalizedStatus)
                || "verify".equals(normalizedStatus)
                || "system_error".equals(normalizedStatus);
    }
}
