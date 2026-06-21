package com.apprisal.common.service;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Unit coverage for the static orderId extraction that drives appraisal<->engagement
 * /contract pairing (common module, no Spring context). A wrong orderId silently
 * mis-pairs documents, so the parsing edge cases are pinned here.
 */
class FileMatchingServiceTest {

    @Test
    void extractsOrderIdAfterLastUnderscore() {
        assertThat(FileMatchingService.extractOrderId("appraisal_001.pdf")).isEqualTo("001");
        assertThat(FileMatchingService.extractOrderId("engagement_001.pdf")).isEqualTo("001");
        assertThat(FileMatchingService.extractOrderId("contract_ABC123.PDF")).isEqualTo("ABC123");
    }

    @Test
    void usesLastUnderscoreWhenMultiple() {
        assertThat(FileMatchingService.extractOrderId("a_b_c_042.pdf")).isEqualTo("042");
    }

    @Test
    void leadingUnderscoreStillYieldsId() {
        assertThat(FileMatchingService.extractOrderId("_001.pdf")).isEqualTo("001");
    }

    @Test
    void noUnderscoreFallsBackToBaseName() {
        assertThat(FileMatchingService.extractOrderId("nounderscore.pdf")).isEqualTo("nounderscore");
    }

    @Test
    void handlesMissingExtension() {
        assertThat(FileMatchingService.extractOrderId("report_42")).isEqualTo("42");
    }

    @Test
    void trailingUnderscoreFallsBackToBaseName() {
        // lastUnderscore is at the final position, so nothing follows it -> fallback.
        assertThat(FileMatchingService.extractOrderId("file_.pdf")).isEqualTo("file_");
    }

    @Test
    void nullAndBlankReturnNull() {
        assertThat(FileMatchingService.extractOrderId(null)).isNull();
        assertThat(FileMatchingService.extractOrderId("")).isNull();
        assertThat(FileMatchingService.extractOrderId("   ")).isNull();
    }
}
