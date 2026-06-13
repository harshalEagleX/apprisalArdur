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
 * section; rules are the individual rule evaluations. The LLM fields separate
 * the two costs that look identical in plain wall-clock time: model inference
 * time vs throttle/rate-limit wait time.
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record PythonTimings(
        @JsonProperty("total_ms")             Double totalMs,
        @JsonProperty("rule_engine_ms")       Double ruleEngineMs,
        @JsonProperty("measured_pipeline_ms") Double measuredPipelineMs,
        @JsonProperty("rule_count")           Integer ruleCount,
        List<Stage>   stages,
        List<Section> sections,
        List<Rule>    rules,
        Llm           llm
) {
    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Stage(
            String stage,
            String label,
            Double ms,
            @JsonProperty("pct_of_pipeline") Double pctOfPipeline,
            @JsonProperty("llm_calls")       Integer llmCalls,
            @JsonProperty("inference_ms")    Double inferenceMs,
            @JsonProperty("throttle_wait_ms") Double throttleWaitMs
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
            Double ms,
            Double confidence,
            @JsonProperty("llm_calls")   Integer llmCalls,
            @JsonProperty("llm_ms")      Double llmMs,
            @JsonProperty("throttle_ms") Double throttleMs
    ) {}

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Llm(
            @JsonProperty("total_calls")            Integer totalCalls,
            @JsonProperty("total_inference_ms")     Double totalInferenceMs,
            @JsonProperty("total_throttle_wait_ms") Double totalThrottleWaitMs,
            @JsonProperty("rate_limit_hits")        Integer rateLimitHits
    ) {}
}
