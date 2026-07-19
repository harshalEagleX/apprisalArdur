package com.shal.common.dto.shalqc;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.List;
import java.util.Map;

/**
 * One checklist item as the reviewer sees it (SHALqc ReviewerCard).
 *
 * <p>status is the 5-word v2 vocabulary — SATISFIED | NOT_SATISFIED | REVIEW |
 * NOT_APPLICABLE | CANNOT_EVALUATE — mapped to the Java rule vocabulary
 * (PASS/FAIL/VERIFY) at persistence time. {@code group} is the reviewer bucket
 * (recommended_reject | please_verify | looks_good | manual_visual |
 * not_applicable). {@code primaryLocation} + each evidence row's page/bbox drive
 * the document auto-scroll.
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record ShalqcCard(
        @JsonProperty("item_id")   String itemId,
        String group,
        String section,
        String status,
        @JsonProperty("item_name") String itemName,
        @JsonProperty("check_text") String checkText,
        String description,
        @JsonProperty("reject_text") String rejectText,
        String headline,
        String expected,
        String found,
        @JsonProperty("reviewer_line") String reviewerLine,
        List<ShalqcEvidence> evidence,
        @JsonProperty("primary_location") ShalqcLocation primaryLocation,
        Map<String, Object> values,
        @JsonProperty("suggested_wording") String suggestedWording,
        Double confidence,
        String judgeable,
        // The check ALSO depends on photos/sketch the judge cannot see, so its text
        // verdict stands but a human must confirm the image (SHALqc run._card).
        // Distinct from judgeable="visual", which is a WHOLLY manual card: this one
        // carries a real text verdict AND the photo note.
        @JsonProperty("photo_verification_required") Boolean photoVerificationRequired,
        List<String> guardrails,
        @JsonProperty("decided_by") String decidedBy,
        @JsonProperty("bound_by")   String boundBy,
        @JsonProperty("binder_confidence") Double binderConfidence,
        @JsonProperty("bound_labels") List<String> boundLabels,
        @JsonProperty("llm_interaction_id") String llmInteractionId,
        // Reject authority (PART 1.1): "rejectable" | "informational". Distinct from
        // QCRuleResult.severity (BLOCKING/STANDARD) — this says whether the AMC can
        // reject on the check at all. Only rejectable items reach the reviewer queue.
        String severity
) {}
