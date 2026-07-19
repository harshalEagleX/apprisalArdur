package com.shal.common.mapper;

import com.shal.common.dto.shalqc.ShalqcCard;
import com.shal.common.entity.QCRuleResult;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.params.provider.ValueSource;
import tools.jackson.databind.ObjectMapper;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * The Python → Java translation layer, unit-level.
 *
 * ShalqcRoundTripRegressionTest proves a whole realistic response survives; this
 * covers the per-field EDGES it does not exercise — unknown status words, absent
 * confidence, empty collections, malformed summaries. A bug in any of these
 * corrupts every card of every order, silently.
 */
class ShalqcResponseMapperTest {

    private final ShalqcResponseMapper mapper = new ShalqcResponseMapper(new ObjectMapper());

    /** A card with only the fields a given test cares about. */
    private static ShalqcCard card(String status, String group, String severity) {
        return new ShalqcCard("EQ-1", group, "SUBJECT", status, "Item", "check", "check",
                null, "headline", "expected", "found", "reviewer line",
                List.of(), null, Map.of(), null, 0.9, "text", false, List.of(),
                "judge_v2", "llm", 0.9, List.of("label_a"), null, severity);
    }

    // ── status vocabulary (5 words → 4) ─────────────────────────────────────

    @ParameterizedTest
    @CsvSource({
            "SATISFIED,       PASS",
            "NOT_SATISFIED,   FAIL",
            "REVIEW,          VERIFY",
            "NOT_APPLICABLE,  NOT_APPLICABLE",
            "CANNOT_EVALUATE, VERIFY",
    })
    @DisplayName("every v2 status maps to its Java status")
    void statusVocabularyMapsCompletely(String v2, String java) {
        assertThat(ShalqcResponseMapper.mapStatus(v2)).isEqualTo(java);
    }

    @Test
    @DisplayName("an unknown or absent status degrades to VERIFY, never to PASS")
    void unknownStatusDegradesToVerify() {
        // Fail-safe: a status word this build does not know must put a human on the
        // item rather than mark the order clean.
        assertThat(ShalqcResponseMapper.mapStatus(null)).isEqualTo("VERIFY");
        assertThat(ShalqcResponseMapper.mapStatus("")).isEqualTo("VERIFY");
        assertThat(ShalqcResponseMapper.mapStatus("SOMETHING_NEW")).isEqualTo("VERIFY");
    }

    @Test
    @DisplayName("status is case- and whitespace-tolerant")
    void statusIsNormalized() {
        assertThat(ShalqcResponseMapper.mapStatus("  satisfied  ")).isEqualTo("PASS");
        assertThat(ShalqcResponseMapper.mapStatus("Not_Satisfied")).isEqualTo("FAIL");
    }

    // ── queue placement: group is authoritative, not severity ───────────────

    @Test
    @DisplayName("an informational card stays OFF the queue whatever its status says")
    void informationalNeverEntersTheQueue() {
        QCRuleResult r = mapper.toRuleResult(card("NOT_SATISFIED", "informational", "informational"));
        assertThat(r.getReviewRequired()).isFalse();
        assertThat(r.getNeedsVerification()).isFalse();
        assertThat(r.getSeverity()).isEqualTo("STANDARD");   // never BLOCKING
    }

    @Test
    @DisplayName("a PROMOTED informational card is actionable but still never blocking")
    void promotedInformationalIsActionableButNotBlocking() {
        // Python promotes a failing informational item into an actionable group; Java
        // must honour the GROUP (so the reviewer sees it) without granting the AMC
        // reject authority it never had.
        QCRuleResult r = mapper.toRuleResult(card("NOT_SATISFIED", "please_verify", "informational"));
        assertThat(r.getReviewRequired()).isTrue();
        assertThat(r.getSeverity()).isEqualTo("STANDARD");
    }

    @Test
    @DisplayName("only a rejectable NOT_SATISFIED is BLOCKING")
    void onlyRejectableFailIsBlocking() {
        assertThat(mapper.toRuleResult(card("NOT_SATISFIED", "recommended_reject", "rejectable"))
                .getSeverity()).isEqualTo("BLOCKING");
        // a rejectable card that merely needs review is not blocking
        assertThat(mapper.toRuleResult(card("REVIEW", "please_verify", "rejectable"))
                .getSeverity()).isEqualTo("STANDARD");
    }

    @ParameterizedTest
    @ValueSource(strings = {"SATISFIED", "NOT_APPLICABLE"})
    @DisplayName("settled statuses need no reviewer")
    void settledStatusesNeedNoReviewer(String status) {
        assertThat(mapper.toRuleResult(card(status, "looks_good", "rejectable"))
                .getReviewRequired()).isFalse();
    }

    // ── confidence tiers ────────────────────────────────────────────────────

    @Test
    @DisplayName("confidence maps to the plain-language tier at its boundaries")
    void confidenceTierBoundaries() {
        assertThat(tierFor(0.8)).isEqualTo("high");     // inclusive lower bound
        assertThat(tierFor(0.79)).isEqualTo("medium");
        assertThat(tierFor(0.5)).isEqualTo("medium");   // inclusive lower bound
        assertThat(tierFor(0.49)).isEqualTo("low");
        assertThat(tierFor(1.0)).isEqualTo("high");
        assertThat(tierFor(0.0)).isEqualTo("low");
    }

    @Test
    @DisplayName("an absent confidence is treated as lowest trust, not highest")
    void absentConfidenceIsLow() {
        ShalqcCard c = new ShalqcCard("EQ-1", "please_verify", "SUBJECT", "REVIEW", "Item",
                "check", "check", null, "h", "e", "f", "line", List.of(), null, Map.of(),
                null, null, "text", false, List.of(), "judge_v2", "llm", null,
                List.of(), null, "rejectable");
        QCRuleResult r = mapper.toRuleResult(c);
        assertThat(r.getConfidenceTier()).isEqualTo("low");
        assertThat(r.getConfidenceScore()).isEqualTo(0.0d);
    }

    private String tierFor(double conf) {
        ShalqcCard c = new ShalqcCard("EQ-1", "please_verify", "SUBJECT", "REVIEW", "Item",
                "check", "check", null, "h", "e", "f", "line", List.of(), null, Map.of(),
                null, conf, "text", false, List.of(), "judge_v2", "llm", conf,
                List.of(), null, "rejectable");
        return mapper.toRuleResult(c).getConfidenceTier();
    }

    // ── nothing silently dropped ────────────────────────────────────────────

    @Test
    @DisplayName("guardrails, bound_labels, values and severity all survive in details JSON")
    void detailsJsonRetainsEverythingWithoutAColumn() {
        ShalqcCard c = new ShalqcCard("EQ-9", "please_verify", "SUBJECT", "REVIEW", "Item",
                "check", "check", null, "h", "e", "f", "line", List.of(), null,
                Map.of("label_a", "value_a"), null, 0.9, "text", false,
                List.of("absent_data", "ungrounded"), "judge_v2", "llm", 0.9,
                List.of("label_a", "label_b"), null, "rejectable");
        String details = mapper.toRuleResult(c).getDetails();
        assertThat(details).contains("absent_data").contains("ungrounded");
        assertThat(details).contains("label_a").contains("label_b");
        assertThat(details).contains("value_a");
        assertThat(details).contains("\"severity\":\"rejectable\"");
    }

    @Test
    @DisplayName("a card with empty collections still produces valid details JSON")
    void emptyCollectionsAreSafe() {
        String details = mapper.toRuleResult(card("REVIEW", "please_verify", null)).getDetails();
        assertThat(details).startsWith("{").endsWith("}");
        // absent reject authority defaults to informational, never to rejectable
        assertThat(details).contains("\"severity\":\"informational\"");
    }

    @Test
    @DisplayName("targetField falls back to a placeholder rather than null")
    void targetFieldAlwaysPopulated() {
        ShalqcCard noLabels = new ShalqcCard("EQ-1", "please_verify", "SUBJECT", "REVIEW",
                "Item", "check", "check", null, "h", "e", "f", "line", List.of(), null,
                Map.of(), null, 0.9, "text", false, List.of(), "judge_v2", "llm", 0.9,
                List.of(), null, "rejectable");
        assertThat(mapper.toRuleResult(noLabels).getTargetField()).isEqualTo("checklist_item");
        assertThat(mapper.toRuleResult(card("REVIEW", "please_verify", "rejectable"))
                .getTargetField()).isEqualTo("label_a");
    }

    @Test
    @DisplayName("a card with no location gets zeroed coordinates, not nulls")
    void missingLocationZeroes() {
        // pdfPage/bbox are non-null columns; a null here would fail the insert.
        QCRuleResult r = mapper.toRuleResult(card("REVIEW", "please_verify", "rejectable"));
        assertThat(r.getPdfPage()).isZero();
        assertThat(r.getBboxX()).isZero();
        assertThat(r.getBboxY()).isZero();
        assertThat(r.getBboxW()).isZero();
        assertThat(r.getBboxH()).isZero();
    }

    // ── summary roll-up, including legacy synonyms ──────────────────────────

    @Test
    @DisplayName("summary counts read v2 keys and their legacy synonyms")
    void summaryCountsAcceptBothVocabularies() {
        assertThat(mapper.passed(Map.of("satisfied", 3))).isEqualTo(3);
        assertThat(mapper.passed(Map.of("passed", 2))).isEqualTo(2);
        assertThat(mapper.failed(Map.of("not_satisfied", 1))).isEqualTo(1);
        assertThat(mapper.failed(Map.of("failed", 4))).isEqualTo(4);
        // review + cannot_evaluate + to_verify + hold all mean "a human must look"
        assertThat(mapper.verify(Map.of("review", 1, "cannot_evaluate", 2,
                                        "to_verify", 3, "hold", 4))).isEqualTo(10);
    }

    @Test
    @DisplayName("an empty or malformed summary yields zeroes rather than throwing")
    void malformedSummaryIsSafe() {
        assertThat(mapper.passed(Map.of())).isZero();
        assertThat(mapper.failed(Map.of("failed", "not-a-number"))).isZero();
        // HashMap, not Map.of — the latter rejects null VALUES at construction, so a
        // null-valued key can only be built this way (and JSON can produce one).
        java.util.Map<String, Object> withNull = new java.util.HashMap<>();
        withNull.put("review", null);
        assertThat(mapper.verify(withNull)).isZero();
        assertThat(mapper.passed(null)).isZero();
    }

    @Test
    @DisplayName("a numeric count arriving as a JSON string is still counted")
    void numericStringsAreParsed() {
        // Python/JSON can deliver "3" rather than 3; dropping it would under-report
        // the roll-up the order decision is made from.
        assertThat(mapper.passed(Map.of("satisfied", "3"))).isEqualTo(3);
        assertThat(mapper.verify(Map.of("review", 2.0))).isEqualTo(2);
    }
}
