package com.shal.common.dto.shalqc;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.Map;

/**
 * One located value backing a card. {@code page} + {@code bbox} ({"x","y","w","h"}
 * normalized 0..1, top-left origin) let the reviewer UI draw a highlight and
 * auto-scroll the appraisal to this field. {@code quote} is the grounded LLM
 * citation (verbatim from a packet value), when present.
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record ShalqcEvidence(
        String label,
        Object value,
        String quote,
        Integer page,
        Map<String, Double> bbox,
        @JsonProperty("location_quality") String locationQuality,
        String source,
        @JsonProperty("source_badge") String sourceBadge,
        Double confidence
) {}
