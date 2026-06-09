package com.apprisal.common.dto.python;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * One document-tagged piece of evidence for a rule result, from the Python
 * /qc/process response. {@code document} identifies the source the value was
 * read from (appraisal | engagement | contract | ...), which is what lets the
 * reviewer UI label each value with the document it actually came from instead
 * of guessing. Persisted (as part of a JSON list) in the
 * {@code qc_rule_result.evidence} TEXT column.
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record PythonEvidence(
        @JsonProperty("document")   String document,
        @JsonProperty("value")      String value,
        @JsonProperty("confidence") Double confidence,
        @JsonProperty("page")       Integer page,
        @JsonProperty("method")     String method
) {
}
