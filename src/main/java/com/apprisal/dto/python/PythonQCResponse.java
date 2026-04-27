package com.apprisal.dto.python;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.List;
import java.util.Map;

/**
 * Maps the full Python /qc/process response.
 * Jackson 3 deserializes records natively via the canonical constructor.
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record PythonQCResponse(
        boolean success,
        @JsonProperty("processing_time_ms") int processingTimeMs,
        @JsonProperty("total_pages")         int totalPages,
        @JsonProperty("extraction_method")   String extractionMethod,
        @JsonProperty("extracted_fields")    Map<String, Object> extractedFields,
        @JsonProperty("field_confidence")    Map<String, Double> fieldConfidence,
        @JsonProperty("total_rules")         int totalRules,
        int passed,
        int failed,
        int verify,
        int warnings,
        int skipped,
        @JsonProperty("system_errors")       int systemErrors,
        @JsonProperty("document_id")         String documentId,
        @JsonProperty("cache_hit")           boolean cacheHit,
        @JsonProperty("file_hash")           String fileHash,
        @JsonProperty("rule_results")        List<PythonRuleResult> ruleResults,
        @JsonProperty("action_items")        List<String> actionItems,
        List<String> suggestions,
        @JsonProperty("processing_warnings") List<String> processingWarnings
) {}
