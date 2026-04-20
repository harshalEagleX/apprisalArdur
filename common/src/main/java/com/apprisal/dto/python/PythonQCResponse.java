package com.apprisal.dto.python;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.List;
import java.util.Map;

/**
 * DTO mapping Python /qc/process response (QCResults model).
 * Maps the complete QC processing result from Python OCR service.
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public class PythonQCResponse {

    private boolean success;

    @JsonProperty("processing_time_ms")
    private int processingTimeMs;

    @JsonProperty("total_pages")
    private int totalPages;

    @JsonProperty("extraction_method")
    private String extractionMethod;

    @JsonProperty("extracted_fields")
    private Map<String, Object> extractedFields;

    @JsonProperty("field_confidence")
    private Map<String, Double> fieldConfidence;

    @JsonProperty("total_rules")
    private int totalRules;

    private int passed;
    private int failed;
    private int verify; // Items needing human verification (OCR uncertain)
    private int warnings;
    private int skipped;
    @JsonProperty("system_errors")
    private int systemErrors; // Only actual engine crashes

    @JsonProperty("rule_results")
    private List<PythonRuleResult> ruleResults;

    @JsonProperty("action_items")
    private List<String> actionItems;

    private List<String> suggestions;

    @JsonProperty("processing_warnings")
    private List<String> processingWarnings;

    // Getters and Setters
    public boolean isSuccess() {
        return success;
    }

    public void setSuccess(boolean success) {
        this.success = success;
    }

    public int getProcessingTimeMs() {
        return processingTimeMs;
    }

    public void setProcessingTimeMs(int processingTimeMs) {
        this.processingTimeMs = processingTimeMs;
    }

    public int getTotalPages() {
        return totalPages;
    }

    public void setTotalPages(int totalPages) {
        this.totalPages = totalPages;
    }

    public String getExtractionMethod() {
        return extractionMethod;
    }

    public void setExtractionMethod(String extractionMethod) {
        this.extractionMethod = extractionMethod;
    }

    public Map<String, Object> getExtractedFields() {
        return extractedFields;
    }

    public void setExtractedFields(Map<String, Object> extractedFields) {
        this.extractedFields = extractedFields;
    }

    public Map<String, Double> getFieldConfidence() {
        return fieldConfidence;
    }

    public void setFieldConfidence(Map<String, Double> fieldConfidence) {
        this.fieldConfidence = fieldConfidence;
    }

    public int getTotalRules() {
        return totalRules;
    }

    public void setTotalRules(int totalRules) {
        this.totalRules = totalRules;
    }

    public int getPassed() {
        return passed;
    }

    public void setPassed(int passed) {
        this.passed = passed;
    }

    public int getFailed() {
        return failed;
    }

    public void setFailed(int failed) {
        this.failed = failed;
    }

    public int getVerify() {
        return verify;
    }

    public void setVerify(int verify) {
        this.verify = verify;
    }

    public int getWarnings() {
        return warnings;
    }

    public void setWarnings(int warnings) {
        this.warnings = warnings;
    }

    public int getSkipped() {
        return skipped;
    }

    public void setSkipped(int skipped) {
        this.skipped = skipped;
    }

    public int getSystemErrors() {
        return systemErrors;
    }

    public void setSystemErrors(int systemErrors) {
        this.systemErrors = systemErrors;
    }

    public List<PythonRuleResult> getRuleResults() {
        return ruleResults;
    }

    public void setRuleResults(List<PythonRuleResult> ruleResults) {
        this.ruleResults = ruleResults;
    }

    public List<String> getActionItems() {
        return actionItems;
    }

    public void setActionItems(List<String> actionItems) {
        this.actionItems = actionItems;
    }

    public List<String> getSuggestions() {
        return suggestions;
    }

    public void setSuggestions(List<String> suggestions) {
        this.suggestions = suggestions;
    }

    public List<String> getProcessingWarnings() {
        return processingWarnings;
    }

    public void setProcessingWarnings(List<String> processingWarnings) {
        this.processingWarnings = processingWarnings;
    }
}
