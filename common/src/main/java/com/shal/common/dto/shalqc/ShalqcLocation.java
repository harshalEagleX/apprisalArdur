package com.shal.common.dto.shalqc;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.Map;

/**
 * The single best {page, bbox} to jump the document to when the reviewer clicks a
 * card. bbox is {"x","y","w","h"} normalized 0..1 (top-left origin). Maps onto the
 * flat pdfPage/bboxX/Y/W/H columns of QCRuleResult at persistence time.
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record ShalqcLocation(
        Integer page,
        Map<String, Double> bbox,
        String label,
        @JsonProperty("location_quality") String locationQuality
) {}
