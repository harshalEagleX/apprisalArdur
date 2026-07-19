package com.shal.common.service;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import java.util.Set;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Document pairing — which engagement letter belongs to which appraisal.
 *
 * This is the highest-consequence logic in FileMatchingService and had no tests
 * (only the static extractOrderId did). A wrong pairing does not fail loudly: the
 * appraisal is QC'd against ANOTHER ORDER'S engagement letter, so every
 * cross-document check — borrower, lender, address, form type — compares the
 * wrong two documents and the reviewer is shown confident nonsense.
 *
 * The scoring ladder being pinned here:
 *   100  identical normalised key
 *    50  one key contains the other
 *    n   overlapping tokens, but ONLY when a number AND a word both match
 *     0  no usable overlap
 */
class FileMatchingScoringTest {

    private static int score(String appraisal, String candidate) {
        return FileMatchingService.scoreMatch(
                FileMatchingService.normalizedMatchKey(appraisal),
                FileMatchingService.matchTokens(appraisal),
                FileMatchingService.normalizedMatchKey(candidate),
                FileMatchingService.matchTokens(candidate));
    }

    // ── normalisation ───────────────────────────────────────────────────────

    @Test
    @DisplayName("document-type words are stripped so they cannot create false overlap")
    void documentWordsStripped() {
        // "appraisal"/"report"/"contract" appear in almost every filename; if they
        // survived normalisation every pair would share a word token.
        String k = FileMatchingService.normalizedMatchKey("Purchase Agreement Contract Order Form.pdf");
        assertThat(k).isBlank();
    }

    @ParameterizedTest
    @CsvSource({
            "'123 Main Street.pdf',   '123 Main St.pdf'",
            "'45 Oak Court.pdf',      '45 Oak Ct.pdf'",
            "'9 Elm Circle.pdf',      '9 Elm Cir.pdf'",
            "'7 Pine Road.pdf',       '7 Pine Rd.pdf'",
            "'2 Fox Avenue.pdf',      '2 Fox Ave.pdf'",
            "'8 Bay Terrace.pdf',     '8 Bay Trace.pdf'",
    })
    @DisplayName("street-type spellings normalise to the same key")
    void streetTypesNormalise(String a, String b) {
        assertThat(FileMatchingService.normalizedMatchKey(a))
                .isEqualTo(FileMatchingService.normalizedMatchKey(b));
    }

    @Test
    @DisplayName("directionals are dropped, so N/North/no-prefix all agree")
    void directionalsDropped() {
        String a = FileMatchingService.normalizedMatchKey("1416 N Potomac St.pdf");
        String b = FileMatchingService.normalizedMatchKey("1416 North Potomac Street.pdf");
        String c = FileMatchingService.normalizedMatchKey("1416 Potomac.pdf");
        assertThat(a).isEqualTo(b).isEqualTo(c);
    }

    @Test
    @DisplayName("case and punctuation do not affect the key")
    void caseAndPunctuationIgnored() {
        assertThat(FileMatchingService.normalizedMatchKey("6296_PARKER-ST_SW.PDF"))
                .isEqualTo(FileMatchingService.normalizedMatchKey("6296 parker st sw.pdf"));
    }

    @Test
    @DisplayName("a null or blank filename normalises to blank rather than throwing")
    void nullSafe() {
        assertThat(FileMatchingService.normalizedMatchKey(null)).isEmpty();
        assertThat(FileMatchingService.matchTokens(null)).isEmpty();
        assertThat(FileMatchingService.matchTokens("   ")).isEmpty();
    }

    // ── the scoring ladder ──────────────────────────────────────────────────

    @Test
    @DisplayName("an identical address scores highest")
    void identicalScores100() {
        assertThat(score("1416 N Potomac St.pdf", "1416 North Potomac Street.pdf")).isEqualTo(100);
    }

    @Test
    @DisplayName("a contained key scores 50 — an engagement letter with a suffix still pairs")
    void containmentScores50() {
        assertThat(score("1416 Potomac EngagementLetter.pdf", "1416 Potomac.pdf")).isEqualTo(50);
    }

    @Test
    @DisplayName("a shared NUMBER alone is not a match — house numbers repeat across streets")
    void sharedNumberAloneIsNotAMatch() {
        // "1416 Potomac" vs "1416 Sparrow" are different properties. Requiring a word
        // too is what stops two unrelated orders being paired on a common number.
        assertThat(score("1416 Potomac.pdf", "1416 Sparrow.pdf")).isZero();
    }

    @Test
    @DisplayName("a shared WORD alone is not a match — street names repeat too")
    void sharedWordAloneIsNotAMatch() {
        // Same street, DIFFERENT house number: two genuinely different properties on
        // Potomac must not pair just because they share the street name.
        assertThat(score("1416 Potomac.pdf", "922 Potomac.pdf")).isZero();
    }

    @Test
    @DisplayName("containment outranks the token rule — and ambiguity is what makes that safe")
    void containmentOutranksTokenRule() {
        // A bare street name scores 50 by CONTAINMENT even though it shares no
        // number, so a tersely-named letter ("Potomac.pdf") still pairs with its
        // appraisal. That is deliberate, and it is only safe because equal top
        // scores are flagged ambiguous rather than silently picking one: in a batch
        // holding BOTH 1416 and 922 Potomac, "Potomac.pdf" ties at 50 against each.
        assertThat(score("1416 Potomac.pdf", "Potomac.pdf")).isEqualTo(50);
        assertThat(score("922 Potomac.pdf", "Potomac.pdf")).isEqualTo(50);
    }

    @Test
    @DisplayName("a number AND a word together do pair")
    void numberPlusWordPairs() {
        assertThat(score("1416 Potomac Apt 2.pdf", "1416 Potomac unit.pdf")).isPositive();
    }

    @Test
    @DisplayName("completely unrelated filenames score zero")
    void unrelatedScoresZero() {
        assertThat(score("1416 N Potomac St.pdf", "6296 Parker St SW.pdf")).isZero();
    }

    @Test
    @DisplayName("a blank key on either side scores zero rather than matching everything")
    void blankKeyScoresZero() {
        // A filename made only of document words normalises to blank; if that scored
        // as containment it would match EVERY candidate.
        assertThat(score("Appraisal Report.pdf", "1416 Potomac.pdf")).isZero();
        assertThat(score("1416 Potomac.pdf", "Appraisal Report.pdf")).isZero();
        assertThat(score("Appraisal.pdf", "Report.pdf")).isZero();
    }

    @Test
    @DisplayName("scoring is symmetric — pairing must not depend on argument order")
    void scoringIsSymmetric() {
        assertThat(score("1416 Potomac EngagementLetter.pdf", "1416 Potomac.pdf"))
                .isEqualTo(score("1416 Potomac.pdf", "1416 Potomac EngagementLetter.pdf"));
        assertThat(score("1416 Potomac.pdf", "6296 Parker.pdf"))
                .isEqualTo(score("6296 Parker.pdf", "1416 Potomac.pdf"));
    }

    @Test
    @DisplayName("real order filenames from the corpus pair correctly and do NOT cross-pair")
    void realCorpusPairsCorrectly() {
        // Straight from testfiles/: each appraisal must beat every other order's letter.
        int own = score("1416 N Potomac St.pdf", "1416 N Potomac St EngagementLetter.pdf");
        int other = score("1416 N Potomac St.pdf", "6296 Parker St SW EngagementLetter.pdf");
        assertThat(own).isGreaterThan(other);
        assertThat(other).isZero();
    }

    // ── tokens ──────────────────────────────────────────────────────────────

    @Test
    @DisplayName("tokens are the normalised words, with document noise removed")
    void tokensExcludeNoise() {
        Set<String> t = FileMatchingService.matchTokens("1416 N Potomac Street Appraisal Report.pdf");
        assertThat(t).contains("1416", "potomac");
        assertThat(t).doesNotContain("appraisal", "report", "n", "street", "st");
    }
}
