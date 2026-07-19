package com.shal.qc.controller.api;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.params.provider.ValueSource;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * The reviewer API's decision logic.
 *
 * The qc module measured 0.3% line coverage — effectively untested — while
 * holding the endpoints the reviewer UI runs on. These three helpers are the
 * highest-consequence pure logic in it:
 *
 *   normalizeStatus     — what an absent/odd status word degrades to
 *   needsReviewerAction — whether a finding is put in front of a human AT ALL
 *   sectionForRule      — which report section a finding is filed under
 *
 * A bug in the second silently drops findings out of the queue; a bug in the
 * third files them under the wrong section so a reviewer never looks there.
 */
class ReviewerApiControllerLogicTest {

    // ── normalizeStatus ─────────────────────────────────────────────────────

    @Test
    @DisplayName("a missing status degrades to 'verify' — never to a silent pass")
    void nullAndBlankStatusBecomeVerify() {
        // Fail-safe direction matters: an unknown status must land a human on it,
        // not wave it through.
        assertThat(ReviewerApiController.normalizeStatus(null)).isEqualTo("verify");
        assertThat(ReviewerApiController.normalizeStatus("")).isEqualTo("verify");
        assertThat(ReviewerApiController.normalizeStatus("   ")).isEqualTo("verify");
    }

    @ParameterizedTest
    @CsvSource({"FAIL,fail", "Fail,fail", "  PASS  ,pass", "Verify,verify"})
    @DisplayName("status is trimmed and lower-cased so casing never changes behaviour")
    void statusIsNormalized(String raw, String expected) {
        assertThat(ReviewerApiController.normalizeStatus(raw)).isEqualTo(expected);
    }

    // ── needsReviewerAction ─────────────────────────────────────────────────

    @ParameterizedTest
    @ValueSource(strings = {"fail", "verify", "review", "extraction_failed",
                            "ocr_low_confidence", "system_error", "source_missing",
                            "cross_doc_mismatch"})
    @DisplayName("every actionable status reaches a reviewer")
    void actionableStatusesNeedAReviewer(String status) {
        assertThat(ReviewerApiController.needsReviewerAction(status)).isTrue();
    }

    @ParameterizedTest
    @ValueSource(strings = {"pass", "not_applicable", "manual_pass", "looks_good"})
    @DisplayName("settled statuses do not demand reviewer action")
    void settledStatusesDoNot(String status) {
        assertThat(ReviewerApiController.needsReviewerAction(status)).isFalse();
    }

    @Test
    @DisplayName("an absent status is actionable, because it normalizes to verify")
    void absentStatusIsActionable() {
        assertThat(ReviewerApiController.needsReviewerAction(null)).isTrue();
        assertThat(ReviewerApiController.needsReviewerAction("")).isTrue();
    }

    @Test
    @DisplayName("casing never decides whether a human sees a finding")
    void actionabilityIsCaseInsensitive() {
        assertThat(ReviewerApiController.needsReviewerAction("FAIL")).isTrue();
        assertThat(ReviewerApiController.needsReviewerAction("  Cross_Doc_Mismatch  ")).isTrue();
    }

    // ── sectionForRule ──────────────────────────────────────────────────────

    @ParameterizedTest
    @CsvSource({
            "SCA-5,   SALES_COMPARISON",
            "SIG-1,   SIGNATURE",
            "ST-7,    SITE",
            "FHA-2,   FHA",
            "USDA-1,  USDA",
            "ADD-3,   ADDENDUM",
            "RECON-1, RECONCILIATION",
            "PH-4,    PHOTOS",
            "CA-2,    COST_APPROACH",
            "DOC-1,   DOCUMENTS",
            "M-3,     MAPS",
            "SK-1,    SKETCH",
    })
    @DisplayName("multi-letter prefixes map to their section")
    void multiLetterPrefixes(String ruleId, String section) {
        assertThat(ReviewerApiController.sectionForRule(ruleId)).isEqualTo(section);
    }

    @ParameterizedTest
    @CsvSource({"S-1, SUBJECT", "C-2, CONTRACT", "N-3, NEIGHBORHOOD",
                "I-4, IMPROVEMENTS", "R-5, RECONCILIATION", "G-6, GLOBAL"})
    @DisplayName("single-letter prefixes map to their section")
    void singleLetterPrefixes(String ruleId, String section) {
        assertThat(ReviewerApiController.sectionForRule(ruleId)).isEqualTo(section);
    }

    @Test
    @DisplayName("longer prefixes win over their single-letter prefix")
    void longerPrefixesTakePrecedence() {
        // Each of these starts with a letter that ALSO has a single-letter rule, so
        // the ordering of the checks is what keeps them correct. Get this wrong and
        // sales-comparison findings file under SUBJECT, where nobody looks for them.
        assertThat(ReviewerApiController.sectionForRule("SCA-1")).isEqualTo("SALES_COMPARISON");
        assertThat(ReviewerApiController.sectionForRule("SIG-1")).isEqualTo("SIGNATURE");
        assertThat(ReviewerApiController.sectionForRule("ST-1")).isEqualTo("SITE");
        assertThat(ReviewerApiController.sectionForRule("SK-1")).isEqualTo("SKETCH");
        assertThat(ReviewerApiController.sectionForRule("CA-1")).isEqualTo("COST_APPROACH");
        assertThat(ReviewerApiController.sectionForRule("RECON-1")).isEqualTo("RECONCILIATION");
    }

    @Test
    @DisplayName("case-insensitive")
    void lowerCaseRuleIdsStillMap() {
        assertThat(ReviewerApiController.sectionForRule("sca-5")).isEqualTo("SALES_COMPARISON");
        assertThat(ReviewerApiController.sectionForRule("s-1")).isEqualTo("SUBJECT");
    }

    @Test
    @DisplayName("an unknown or absent rule id lands in OTHER rather than throwing")
    void unknownFallsBackToOther() {
        assertThat(ReviewerApiController.sectionForRule(null)).isEqualTo("OTHER");
        assertThat(ReviewerApiController.sectionForRule("ZZZ-1")).isEqualTo("OTHER");
        assertThat(ReviewerApiController.sectionForRule("EQ-62")).isEqualTo("OTHER");
    }

    @Test
    @DisplayName("never throws on malformed input")
    void malformedInputIsSafe() {
        // A rule id is engine-supplied; a crash here takes out the whole queue view.
        assertThat(ReviewerApiController.sectionForRule("")).isEqualTo("OTHER");
        assertThat(ReviewerApiController.sectionForRule("-")).isEqualTo("OTHER");
        assertThat(ReviewerApiController.sectionForRule("123")).isEqualTo("OTHER");
    }
}
