package com.shal.common.dto.python;

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
        // Normalized [0,1] field box (top-left origin) for this specific piece of
        // evidence, when the locator could place it: {"x","y","w","h"}. Null when
        // the value couldn't be located precisely (page-level reference only).
        // Kept so a multi-field rule can make each side independently clickable.
        @JsonProperty("bbox")       java.util.Map<String, Double> bbox,
        @JsonProperty("method")     String method
) {
}
