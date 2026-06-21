package com.apprisal.common.dto.python;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Unit coverage for PythonRuleResult.needsVerification() — the predicate that decides
 * whether a single Python rule row pulls a document into the reviewer queue. This drives
 * the batch decision aggregate, so its status handling (case, review-like statuses, the
 * reviewRequired flag, null safety) is pinned here. No Spring context.
 */
class PythonRuleResultTest {

    /** Builds a rule result with only status + reviewRequired set; everything else null. */
    private PythonRuleResult result(String status, boolean reviewRequired) {
        return new PythonRuleResult(
                "R-1", "Test rule", "section",
                status, "msg", "severity", "action",
                null, null, null, null, null, null,
                null, null, null, reviewRequired,
                null, null, null, null, null, null);
    }

    @Test
    void failAlwaysNeedsVerification() {
        assertThat(result("fail", false).needsVerification()).isTrue();
        assertThat(result("FAIL", false).needsVerification()).isTrue();
        assertThat(result("  Fail  ", false).needsVerification()).isTrue();
    }

    @Test
    void reviewLikeStatusesNeedVerification() {
        for (String s : new String[]{"verify", "review", "extraction_failed",
                "ocr_low_confidence", "system_error", "source_missing", "cross_doc_mismatch"}) {
            assertThat(result(s, false).needsVerification())
                    .as("status=%s", s).isTrue();
        }
    }

    @Test
    void passDoesNotNeedVerification() {
        assertThat(result("pass", false).needsVerification()).isFalse();
        assertThat(result("not_applicable", false).needsVerification()).isFalse();
    }

    @Test
    void reviewRequiredFlagForcesVerificationEvenOnPass() {
        assertThat(result("pass", true).needsVerification()).isTrue();
    }

    @Test
    void nullStatusIsSafeAndNotReviewable() {
        assertThat(result(null, false).needsVerification()).isFalse();
        assertThat(result(null, true).needsVerification()).isTrue();
    }
}
