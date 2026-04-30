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
        @JsonProperty("review_required")  boolean reviewRequired
) {
    /** True when this rule result requires a human reviewer to make a decision. */
    public boolean needsVerification() {
        String normalizedStatus = status == null ? "" : status.trim().toLowerCase();
        return reviewRequired
                || "fail".equals(normalizedStatus)
                || "verify".equals(normalizedStatus)
                || "warning".equals(normalizedStatus)
                || "system_error".equals(normalizedStatus);
    }
}
