package com.shal.common.mapper;

import com.shal.common.dto.shalqc.ShalqcCard;
import com.shal.common.dto.shalqc.ShalqcInteraction;
import com.shal.common.dto.shalqc.ShalqcResponse;
import com.shal.common.entity.LLMInteraction;
import com.shal.common.entity.QCDecision;
import com.shal.common.entity.QCRuleResult;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.stream.Collectors;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * FULL round-trip regression: parses a REAL SHALqc language response with the Java
 * DTOs and runs {@link ShalqcResponseMapper} over every card + interaction, then
 * prints a GAP REPORT (status coverage, coordinate coverage, interaction linkage,
 * and card fields that currently have no home in QCRuleResult).
 *
 * <p>Default input is the PII-free bundled fixture. To run against a real captured
 * response (e.g. from a live /qc/process zip round-trip), set:
 * {@code SHALQC_RESP=/path/to/shalqc_response.json}.
 *
 * <p>Hard assertions cover contract breaks (parse failure, unmapped status, lost
 * coordinates, broken interaction link). Field-coverage gaps are REPORTED, not
 * failed — that is the point of the exercise.
 */
class ShalqcRoundTripRegressionTest {

    private final ObjectMapper om = new ObjectMapper();
    private final ShalqcResponseMapper mapper = new ShalqcResponseMapper(om);

    private ShalqcResponse load() throws Exception {
        String override = System.getenv("SHALQC_RESP");
        String json;
        if (override != null && !override.isBlank()) {
            json = Files.readString(Path.of(override));
            System.out.println("[regression] input = " + override);
        } else {
            json = new String(getClass().getResourceAsStream("/shalqc/sample_response.json").readAllBytes());
            System.out.println("[regression] input = bundled sample_response.json");
        }
        return om.readValue(json, ShalqcResponse.class);
    }

    @Test
    void roundTripMapsEveryCardAndReportsGaps() throws Exception {
        ShalqcResponse resp = load();

        // 1) parse — the DTO must deserialize the native contract cleanly.
        assertThat(resp).isNotNull();
        assertThat(resp.cards()).as("cards deserialized").isNotEmpty();
        List<ShalqcCard> cards = resp.cards();
        List<ShalqcInteraction> interactions =
                resp.llmInteractions() == null ? List.of() : resp.llmInteractions();
        Set<String> interactionIds =
                interactions.stream().map(ShalqcInteraction::id).collect(Collectors.toSet());

        // 2) map every card → QCRuleResult; collect coverage stats.
        Map<String, Integer> v2StatusDist = new TreeMap<>();
        Map<String, Integer> javaStatusDist = new TreeMap<>();
        int withCoords = 0, linked = 0, linkResolved = 0, cardsWithLoc = 0;
        for (ShalqcCard c : cards) {
            QCRuleResult r = mapper.toRuleResult(c);

            v2StatusDist.merge(String.valueOf(c.status()), 1, Integer::sum);
            javaStatusDist.merge(r.getStatus(), 1, Integer::sum);

            // status must always map to a known Java vocabulary word
            assertThat(r.getStatus())
                    .as("status mapped for " + c.itemId() + " (" + c.status() + ")")
                    .isIn("PASS", "FAIL", "VERIFY", "NOT_APPLICABLE");

            // coordinates: when the card has a primary_location page, it must survive
            if (c.primaryLocation() != null && c.primaryLocation().page() != null
                    && c.primaryLocation().page() > 0) {
                cardsWithLoc++;
                assertThat(r.getPdfPage())
                        .as("pdfPage preserved for " + c.itemId())
                        .isEqualTo(c.primaryLocation().page());
                if (r.getPdfPage() > 0) withCoords++;
            }

            // interaction link integrity
            if (c.llmInteractionId() != null) {
                linked++;
                if (interactionIds.contains(c.llmInteractionId())) linkResolved++;
            }
        }

        // 3) interactions → LLMInteraction entities
        for (ShalqcInteraction i : interactions) {
            LLMInteraction e = mapper.toInteraction(i, 999L);
            assertThat(e.getInteractionId()).isEqualTo(i.id());
            assertThat(e.getRawResponse()).isNotNull();
        }

        // 4) order decision from the roll-up
        QCDecision decision = mapper.decisionFrom(resp.summary());
        assertThat(decision).isNotNull();

        // every linked card must resolve to a stored interaction (no dangling links)
        assertThat(linkResolved).as("all card->interaction links resolve").isEqualTo(linked);

        // ── GAP REPORT ──────────────────────────────────────────────────────────
        System.out.println("\n================ SHALqc → Java ROUND-TRIP GAP REPORT ================");
        System.out.printf("cards=%d  interactions=%d  summary=%s%n",
                cards.size(), interactions.size(), resp.summary());
        System.out.println("v2 status distribution   : " + v2StatusDist);
        System.out.println("java status distribution : " + javaStatusDist);
        System.out.printf("coordinate coverage      : %d/%d cards had a page, %d preserved%n",
                cardsWithLoc, cards.size(), withCoords);
        System.out.printf("interaction linkage      : %d cards linked, %d resolved%n", linked, linkResolved);
        System.out.println("order decision           : " + decision
                + "  (passed=" + mapper.passed(resp.summary())
                + " failed=" + mapper.failed(resp.summary())
                + " verify=" + mapper.verify(resp.summary()) + ")");

        // Card fields with NO dedicated QCRuleResult column today (persisted only in
        // a fallback field or dropped) — the concrete gaps to close in Slice 2/3.
        Map<String, String> fieldHomes = new LinkedHashMap<>();
        fieldHomes.put("item_id", "ruleId + itemId ✓");
        fieldHomes.put("item_name", "ruleName ✓");
        fieldHomes.put("group", "cardGroup ✓");
        fieldHomes.put("status", "status (5→3) ✓");
        fieldHomes.put("reject_text", "rejectionText ✓");
        fieldHomes.put("expected", "expectedValue ✓");
        fieldHomes.put("found", "extractedValue ✓");
        fieldHomes.put("reviewer_line", "message + summary ✓");
        fieldHomes.put("evidence(+coords)", "evidence json + pdfPage/bbox ✓");
        fieldHomes.put("confidence", "confidenceScore ✓");
        fieldHomes.put("bound_by/decided_by/binder_confidence", "provenance columns ✓");
        fieldHomes.put("llm_interaction_id", "llmInteractionId ✓");
        fieldHomes.put("check_text / description", "checkText column ✓");
        fieldHomes.put("guardrails", "details json ✓");
        fieldHomes.put("bound_labels (full list)", "details json ✓ (first also in targetField)");
        fieldHomes.put("values (label→value map)", "details json ✓ (evidence also carries located values)");
        fieldHomes.put("headline", "folded into message fallback");
        fieldHomes.put("REMAINING", "manual_visual/unbound cards have no coordinates (nothing to scroll to)");
        System.out.println("\nfield homes / gaps:");
        fieldHomes.forEach((k, v) -> System.out.printf("  %-42s %s%n", k, v));
        System.out.println("====================================================================\n");
    }
}
