package com.shal.common.mapper;

import com.shal.common.dto.shalqc.*;
import com.shal.common.entity.LLMInteraction;
import com.shal.common.entity.QCDecision;
import com.shal.common.entity.QCRuleResult;
import tools.jackson.databind.ObjectMapper;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * Maps the native SHALqc language response ({@link ShalqcResponse}) into the Java
 * QC domain — the heart of "Java adopts the OrderQCResponse contract" (Approach B).
 *
 * <p><b>Status mapping (v2 5-word → Java 3-word):</b>
 * SATISFIED→PASS, NOT_SATISFIED→FAIL, REVIEW→VERIFY, NOT_APPLICABLE→NOT_APPLICABLE,
 * CANNOT_EVALUATE→VERIFY (the reviewer checks by eye). The 5th word is preserved
 * losslessly in {@link QCRuleResult#getCardGroup()} for the UI bucket.
 *
 * <p><b>Coordinates:</b> {@code primary_location.{page,bbox{x,y,w,h}}} → the flat
 * {@code pdfPage/bboxX/Y/W/H} columns the reviewer auto-scroll already reads.
 *
 * <p>Stateless; construct once with a shared ObjectMapper.
 */
public class ShalqcResponseMapper {

    private final ObjectMapper mapper;

    public ShalqcResponseMapper(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    // ── status ────────────────────────────────────────────────────────────────

    /** v2 vocabulary → Java rule status (PASS | FAIL | VERIFY | NOT_APPLICABLE). */
    public static String mapStatus(String v2) {
        if (v2 == null) return "VERIFY";
        switch (v2.trim().toUpperCase()) {
            case "SATISFIED":       return "PASS";
            case "NOT_SATISFIED":   return "FAIL";
            case "REVIEW":          return "VERIFY";
            case "NOT_APPLICABLE":  return "NOT_APPLICABLE";
            case "CANNOT_EVALUATE": return "VERIFY";
            default:                return "VERIFY";
        }
    }

    private static boolean needsReview(String javaStatus) {
        return "FAIL".equals(javaStatus) || "VERIFY".equals(javaStatus);
    }

    // ── per-card → QCRuleResult ─────────────────────────────────────────────────

    public QCRuleResult toRuleResult(ShalqcCard c) {
        String status = mapStatus(c.status());
        QCRuleResult r = new QCRuleResult();
        r.setRuleId(orElse(c.itemId(), "UNKNOWN_ITEM"));
        r.setRuleName(orElse(c.itemName(), orElse(c.itemId(), "UNKNOWN_ITEM")));
        r.setSection(upper(c.section()));
        r.setStatus(status);
        r.setCheckText(orElse(c.checkText(), c.description()));   // the AMC's full check
        r.setMessage(orElse(c.reviewerLine(), orElse(c.headline(), "No message provided.")));
        r.setDetails(detailsJson(c));   // guardrails + bound_labels + values (nothing dropped)
        r.setSummary(orElse(c.reviewerLine(), orElse(c.itemName(), c.itemId())));
        r.setActionItem(orElse(c.reviewerLine(), orElse(c.suggestedWording(), "No reviewer action required.")));
        r.setRejectionText(orElse(c.rejectText(), orElse(c.suggestedWording(), "")));
        r.setExpectedValue(orElse(c.expected(), "__NO_EXPECTED_VALUE__"));
        r.setExtractedValue(orElse(c.found(), "__NO_EXTRACTED_VALUE__"));
        r.setVerifyQuestion(orElse(c.reviewerLine(), ""));
        r.setConfidenceScore(c.confidence() != null ? c.confidence() : 0.0d);
        r.setConfidenceTier(tier(c.confidence()));
        r.setNeedsVerification(needsReview(status));
        r.setReviewRequired(needsReview(status));
        r.setSeverity("NOT_SATISFIED".equalsIgnoreCase(c.status()) ? "BLOCKING" : "STANDARD");
        r.setEvidence(writeJson(c.evidence(), "[]"));
        r.setHighlightedValues(writeJson(highlightValues(c), "[]"));
        r.setTargetField(firstLabel(c));

        // provenance (Approach B native fields)
        r.setItemId(c.itemId());
        r.setCardGroup(c.group());
        r.setBoundBy(c.boundBy());
        r.setDecidedBy(c.decidedBy());
        r.setBinderConfidence(c.binderConfidence());
        r.setLlmInteractionId(c.llmInteractionId());
        r.setScope(c.judgeable());

        // coordinates for the document auto-scroll
        applyLocation(r, c.primaryLocation());
        return r;
    }

    private void applyLocation(QCRuleResult r, ShalqcLocation loc) {
        int page = 0;
        float x = 0f, y = 0f, w = 0f, h = 0f;
        if (loc != null) {
            page = loc.page() != null ? loc.page() : 0;
            Map<String, Double> b = loc.bbox();
            if (b != null) {
                x = flt(b.get("x")); y = flt(b.get("y"));
                w = flt(b.get("w")); h = flt(b.get("h"));
            }
        }
        r.setPdfPage(page);
        r.setBboxX(x); r.setBboxY(y); r.setBboxW(w); r.setBboxH(h);
    }

    // ── interactions → LLMInteraction ───────────────────────────────────────────

    public LLMInteraction toInteraction(ShalqcInteraction i, Long qcResultId) {
        LLMInteraction e = new LLMInteraction();
        e.setInteractionId(i.id());
        e.setQcResultId(qcResultId);
        e.setItemId(i.itemId());
        e.setCallType(i.callType());
        e.setPromptVersion(i.promptVersion());
        e.setBatchId(i.batchId());
        e.setProvider(i.provider());
        e.setModel(i.model());
        e.setLatencyMs(i.ms());
        e.setCacheHit(Boolean.TRUE.equals(i.cached()));
        e.setRequestJson(writeJson(i.request(), "{}"));
        e.setResponseJson(writeJson(i.response(), "{}"));
        e.setRawResponse(i.rawResponse());
        return e;
    }

    // ── roll-up → QCDecision ────────────────────────────────────────────────────

    /**
     * The order-level decision from the summary counts. Mirrors the legacy
     * precedence: anything to verify pins the whole file to TO_VERIFY (a human must
     * look) before a confident AUTO_FAIL; all-clear is AUTO_PASS. NOT_APPLICABLE is
     * neutral. SHALqc emits no explicit `blocking`, so a confirmed reject is derived.
     */
    public QCDecision decisionFrom(Map<String, Object> summary) {
        int review = asInt(summary, "review") + asInt(summary, "cannot_evaluate");
        int notSatisfied = asInt(summary, "not_satisfied");
        if (review > 0)       return QCDecision.TO_VERIFY;
        if (notSatisfied > 0) return QCDecision.AUTO_FAIL;
        return QCDecision.AUTO_PASS;
    }

    public int passed(Map<String, Object> s)  { return asInt(s, "satisfied"); }
    public int failed(Map<String, Object> s)  { return asInt(s, "not_satisfied"); }
    public int verify(Map<String, Object> s)  { return asInt(s, "review") + asInt(s, "cannot_evaluate"); }

    // ── helpers ──────────────────────────────────────────────────────────────────

    /** Everything without a first-class column, kept as JSON so nothing is lost:
     *  guardrails (judge-quality signals), the full bound_labels, and the raw
     *  label→value map. */
    private String detailsJson(ShalqcCard c) {
        Map<String, Object> d = new LinkedHashMap<>();
        d.put("guardrails", c.guardrails() != null ? c.guardrails() : List.of());
        d.put("bound_labels", c.boundLabels() != null ? c.boundLabels() : List.of());
        d.put("values", c.values() != null ? c.values() : Map.of());
        return writeJson(d, "{}");
    }

    private List<String> highlightValues(ShalqcCard c) {
        Set<String> out = new LinkedHashSet<>();
        if (c.evidence() != null) {
            for (ShalqcEvidence e : c.evidence()) {
                if (e.value() != null) {
                    String v = String.valueOf(e.value()).trim();
                    if (!v.isEmpty()) out.add(v);
                }
            }
        }
        return new ArrayList<>(out);
    }

    private String firstLabel(ShalqcCard c) {
        if (c.boundLabels() != null && !c.boundLabels().isEmpty()) return c.boundLabels().get(0);
        return "checklist_item";
    }

    private static String tier(Double confidence) {
        double v = confidence != null ? confidence : 0.0;
        if (v >= 0.8) return "high";
        if (v >= 0.5) return "medium";
        return "low";
    }

    private String writeJson(Object o, String fallback) {
        if (o == null) return fallback;
        try {
            return mapper.writeValueAsString(o);
        } catch (Exception e) {
            return fallback;
        }
    }

    private static int asInt(Map<String, Object> m, String key) {
        if (m == null) return 0;
        Object v = m.get(key);
        if (v instanceof Number n) return n.intValue();
        try { return v != null ? Integer.parseInt(String.valueOf(v)) : 0; }
        catch (NumberFormatException e) { return 0; }
    }

    private static float flt(Double d) { return d != null ? d.floatValue() : 0.0f; }

    private static String orElse(String v, String fallback) {
        return (v == null || v.isBlank()) ? fallback : v;
    }

    private static String upper(String v) { return v == null ? null : v.toUpperCase(); }
}
