package com.shal.common.mapper;

import com.shal.common.dto.shalqc.ShalqcCard;
import com.shal.common.dto.shalqc.ShalqcResponse;
import com.shal.common.entity.LLMInteraction;
import com.shal.common.entity.QCRuleResult;
import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Live-contract check: deserialize the ACTUAL SHALqc /qc/process response captured
 * from a real order and run it through {@link ShalqcResponseMapper} — proving the
 * Python wire output → Java DTO → domain entities (QCRuleResult with coordinates +
 * LLMInteraction) path the reviewer UI consumes. Skips unless -Dshalqc.resp=&lt;file&gt;
 * points at a captured response, so CI without the running service is unaffected.
 */
class ShalqcLiveResponseMappingIT {

    @Test
    void mapsRealShalqcResponse() throws Exception {
        String path = System.getProperty("shalqc.resp");
        Assumptions.assumeTrue(path != null && Files.exists(Path.of(path)),
                "set -Dshalqc.resp=<captured /qc/process json> to run");

        ObjectMapper om = new ObjectMapper();
        String json = Files.readString(Path.of(path));
        ShalqcResponse resp = om.readValue(json, ShalqcResponse.class);

        assertNotNull(resp.orderId(), "order_id present");
        assertNotNull(resp.cards(), "cards present");
        assertFalse(resp.cards().isEmpty(), "cards non-empty");

        ShalqcResponseMapper mapper = new ShalqcResponseMapper(om);

        int withCoords = 0, withItemId = 0;
        for (ShalqcCard c : resp.cards()) {
            QCRuleResult r = mapper.toRuleResult(c);
            assertNotNull(r.getRuleId(), "ruleId");
            assertNotNull(r.getStatus(), "status mapped to Java vocab");
            assertTrue(java.util.Set.of("PASS", "FAIL", "VERIFY", "NOT_APPLICABLE").contains(r.getStatus()),
                    "status in Java vocab: " + r.getStatus());
            if (r.getPdfPage() > 0 || r.getBboxW() > 0f) withCoords++;
            if (r.getItemId() != null) withItemId++;
        }

        int interactions = 0;
        if (resp.llmInteractions() != null) {
            for (var i : resp.llmInteractions()) {
                LLMInteraction e = mapper.toInteraction(i, 999L);
                assertEquals(999L, e.getQcResultId());
                assertNotNull(e.getInteractionId());
                interactions++;
            }
        }

        var summary = resp.summary() != null ? resp.summary() : java.util.Map.<String, Object>of();
        System.out.printf("LIVE MAP OK: order=%s cards=%d coords=%d itemIds=%d interactions=%d decision=%s pass=%d fail=%d verify=%d%n",
                resp.orderId(), resp.cards().size(), withCoords, withItemId, interactions,
                mapper.decisionFrom(summary), mapper.passed(summary), mapper.failed(summary), mapper.verify(summary));

        assertTrue(withItemId > 0, "at least one card carries the native item_id (Approach B provenance)");
    }
}
