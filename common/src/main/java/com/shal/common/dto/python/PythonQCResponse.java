package com.shal.common.dto.python;

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
        // Version of the Python response CONTRACT shape (not the ruleset). Lets the
        // backend detect a wire-format change instead of silently misreading drift.
        // Null on legacy/older Python builds that predate the field.
        @JsonProperty("schema_version") String schemaVersion,
        Boolean success,
        @JsonProperty("processing_time_ms") Integer processingTimeMs,
        @JsonProperty("total_pages")         Integer totalPages,
        @JsonProperty("extraction_method")   String extractionMethod,
        @JsonProperty("extracted_fields")    Map<String, Object> extractedFields,
        @JsonProperty("field_confidence")    Map<String, Double> fieldConfidence,
        @JsonProperty("total_rules")         Integer totalRules,
        // Version of the QC ruleset that produced this result ("qc-1.0.0+<fp>").
        // Stamped on the QCResult so two runs are comparable and a flag delta is
        // attributable to a rule change vs a report change.
        @JsonProperty("rule_engine_version") String ruleEngineVersion,
        Integer passed,
        Integer failed,
        Integer verify,
        @JsonProperty("document_id")         String documentId,
        @JsonProperty("processing_job_id")   String processingJobId,
        @JsonProperty("cache_hit")           Boolean cacheHit,
        @JsonProperty("file_hash")           String fileHash,
        @JsonProperty("model_provider")      String modelProvider,
        @JsonProperty("model_name")          String modelName,
        @JsonProperty("vision_model")        String visionModel,
        @JsonProperty("supporting_document_missing") Boolean supportingDocumentMissing,
        @JsonProperty("missing_supporting_documents") List<String> missingSupportingDocuments,
        // Explicit blocking signal computed by the engine from HOLD rules — the
        // source of truth for the BLOCKED decision (remediation E1).
        @JsonProperty("blocking")            Boolean blocking,
        @JsonProperty("blocking_rules")      List<String> blockingRules,
        @JsonProperty("rule_results")        List<PythonRuleResult> ruleResults,
        @JsonProperty("action_items")        List<String> actionItems,
        List<String> suggestions,
        @JsonProperty("processing_notices") List<String> processingNotices,
        @JsonProperty("timings") PythonTimings timings
) {}
