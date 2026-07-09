package com.shal.common.service;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Content-based document-type heuristic. A sales contract mis-filed in the AMC's
 * engagement folder was being counted as a second engagement letter ("2 engagement
 * letters found"); looksLikeSalesContract corrects that by content. The text
 * snippets below mirror the real corpus documents (Offer Summary contract vs the
 * Equity Solutions engagement letter), validated to score 14.5 vs 0-4.5.
 */
class DocumentContentSnifferTest {

    private final DocumentContentSniffer sniffer = new DocumentContentSniffer();

    // Mirrors "Offer to purchase 10735 Secor.pdf" — an Offer Summary form.
    private static final String OFFER_SUMMARY_CONTRACT = """
        Offer Summary
        Property Address: 10735 Secor Rd
        Sales Price: $  Close by date:  Seller's Concessions: $
        Loan Type:  EMD Amount: $  Held By:
        Buyer's Agent   Buyers Title Company
        Listing Agent   Seller's Title Company
        Escrow / Terms:
        """;

    // Mirrors a real Equity Solutions engagement letter.
    private static final String ENGAGEMENT_LETTER = """
        File ID: ESMI-0048528
        Service Fee: $450
        Intended Use: Mortgage lending
        Assigned: 2026-07-01
        Appraiser: Ghasan Aboona
        Form: Conventional
        """;

    @Test
    void detectsOfferSummaryContractByContent() {
        assertThat(sniffer.looksLikeSalesContract(OFFER_SUMMARY_CONTRACT)).isTrue();
    }

    @Test
    void keepsRealEngagementLetter() {
        assertThat(sniffer.looksLikeSalesContract(ENGAGEMENT_LETTER)).isFalse();
    }

    @Test
    void doesNotReclassifyOnAFewIncidentalMarkers() {
        // "escrow" + "title company" alone (5.0) is below the 6.0 threshold — a passing
        // mention must never drop a document from QC.
        assertThat(sniffer.looksLikeSalesContract("Funds held in escrow by the title company."))
                .isFalse();
    }

    @Test
    void weakMarkersWithoutAContractHeadingAreNotAContract() {
        // Accumulated weak markers (score well over threshold) but NO contract heading —
        // an engagement letter must never be reclassified as a contract on these alone,
        // which is exactly the misfire that hid an engagement and blocked its order.
        String weakButNoHeading =
                "Sales Price $500,000. Closing date to be set. Funds held in escrow by the "
                + "title company. Buyer's Agent and Listing Agent to coordinate. Financing "
                + "contingency applies.";
        assertThat(sniffer.looksLikeSalesContract(weakButNoHeading)).isFalse();
    }

    @Test
    void emptyOrNullIsNotAContract() {
        assertThat(sniffer.looksLikeSalesContract(null)).isFalse();
        assertThat(sniffer.looksLikeSalesContract("   ")).isFalse();
    }

    @Test
    void classicPurchaseAgreementLanguageDetected() {
        assertThat(sniffer.looksLikeSalesContract(
                "Real Estate Purchase Agreement. The purchase price and earnest money "
                + "are held in escrow until the closing date."))
                .isTrue();
    }
}
