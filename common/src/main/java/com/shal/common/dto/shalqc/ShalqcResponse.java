package com.shal.common.dto.shalqc;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.List;
import java.util.Map;

/**
 * The native SHALqc language-mode QC response (OrderQCResponse contract, resp-1.0.0).
 *
 * This is the single specified shape the Python service produces and the Java
 * reviewer pipeline consumes: per-checklist-item {@link ShalqcCard}s (each with
 * coordinates for the document auto-scroll and a link to the stored LLM exchange),
 * a roll-up summary, extraction gaps for the Ops tab, and every raw LLM exchange.
 *
 * Jackson 3 deserializes records natively via the canonical constructor;
 * {@code @JsonIgnoreProperties(ignoreUnknown = true)} tolerates additive fields
 * the Python side may add ahead of Java mapping them.
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record ShalqcResponse(
        @JsonProperty("order_id")      String orderId,
        @JsonProperty("amc_code")      String amcCode,
        String status,                 // "OK" | "BLOCKED"
        @JsonProperty("verdict_vocab") String verdictVocab,   // "v2"
        Map<String, Object> summary,
        List<ShalqcCard> cards,
        @JsonProperty("extraction_gaps")  List<Map<String, Object>> extractionGaps,
        @JsonProperty("llm_interactions") List<ShalqcInteraction> llmInteractions,
        @JsonProperty("location_metric")  Map<String, Object> locationMetric,
        List<String> degradations,
        Map<String, Object> versions,
        String fingerprint,
        @JsonProperty("revision_no")   Integer revisionNo,
        @JsonProperty("cached_run")    Boolean cachedRun
) {}
