package com.apprisal.common.dto.python;

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
        Boolean success,
        @JsonProperty("processing_time_ms") Integer processingTimeMs,
        @JsonProperty("total_pages")         Integer totalPages,
        @JsonProperty("extraction_method")   String extractionMethod,
        @JsonProperty("extracted_fields")    Map<String, Object> extractedFields,
        @JsonProperty("field_confidence")    Map<String, Double> fieldConfidence,
        @JsonProperty("total_rules")         Integer totalRules,
        Integer passed,
        Integer failed,
        Integer verify,
        @JsonProperty("document_id")         String documentId,
        @JsonProperty("cache_hit")           Boolean cacheHit,
        @JsonProperty("file_hash")           String fileHash,
        @JsonProperty("model_provider")      String modelProvider,
        @JsonProperty("model_name")          String modelName,
        @JsonProperty("vision_model")        String visionModel,
        @JsonProperty("rule_results")        List<PythonRuleResult> ruleResults,
        @JsonProperty("action_items")        List<String> actionItems,
        List<String> suggestions,
        @JsonProperty("processing_notices") List<String> processingNotices
) {}
