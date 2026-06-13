package com.apprisal.common.dto.python;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.List;

/**
 * Maps the {@code timings} block of the Python /qc/process response.
 *
 * Every number here is a real {@code perf_counter} wall-clock measurement taken
 * by the Python QC engine and orchestrator — never an estimate. Stages are the
 * extraction/QC pipeline phases; sections roll the per-rule timings up by QC
 * section; rules are the individual rule evaluations.
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record PythonTimings(
        @JsonProperty("total_ms")             Double totalMs,
        @JsonProperty("rule_engine_ms")       Double ruleEngineMs,
        @JsonProperty("measured_pipeline_ms") Double measuredPipelineMs,
        @JsonProperty("rule_count")           Integer ruleCount,
        List<Stage>   stages,
        List<Section> sections,
        List<Rule>    rules
) {
    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Stage(
            String stage,
            String label,
            Double ms,
            @JsonProperty("pct_of_pipeline") Double pctOfPipeline
    ) {}

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Section(
            String section,
            String label,
            Double ms,
            @JsonProperty("rule_count")   Integer ruleCount,
            @JsonProperty("pct_of_rules") Double pctOfRules
    ) {}

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Rule(
            @JsonProperty("rule_id")   String ruleId,
            @JsonProperty("rule_name") String ruleName,
            String section,
            String status,
            Double ms
    ) {}
}
