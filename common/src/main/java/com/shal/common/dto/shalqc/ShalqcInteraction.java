package com.shal.common.dto.shalqc;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.Map;

/**
 * One stored LLM exchange for one checklist item — the request packet we sent, the
 * parsed response, the raw model text, and call metadata. Persisted as an
 * LLMInteraction row and surfaced to the reviewer ("why this verdict") via the
 * card's llm_interaction_id.
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record ShalqcInteraction(
        String id,
        @JsonProperty("item_id")   String itemId,
        @JsonProperty("call_type") String callType,
        @JsonProperty("prompt_version") String promptVersion,
        @JsonProperty("batch_id")  String batchId,
        String provider,
        String model,
        Double ms,
        Boolean cached,
        Map<String, Object> request,
        Map<String, Object> response,
        @JsonProperty("raw_response") String rawResponse,
        String error
) {}
