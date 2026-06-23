package com.shal.common.dto.python;

import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Contract test for the Python /qc/process -> Java mapping (common module). Pins the
 * snake_case bindings, the blocking signal (remediation E1), and — critically —
 * forward compatibility: an unknown field the Python side may add later must NOT break
 * deserialization (@JsonIgnoreProperties(ignoreUnknown = true)). No Spring context.
 */
class PythonQCResponseTest {

    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void mapsSnakeCaseFieldsAndBlockingSignal() {
        String json = """
            {
              "success": true,
              "processing_time_ms": 1234,
              "total_rules": 10,
              "passed": 7, "failed": 1, "verify": 2,
              "rule_engine_version": "qc-1.0.0+abc",
              "blocking": true,
              "blocking_rules": ["G-0", "VAL-1"],
              "supporting_document_missing": true,
              "missing_supporting_documents": ["engagement"],
              "rule_results": [
                {"rule_id": "G-0", "status": "verify", "review_required": true, "message": "hold"}
              ]
            }
            """;

        PythonQCResponse r = mapper.readValue(json, PythonQCResponse.class);

        assertThat(r.success()).isTrue();
        assertThat(r.processingTimeMs()).isEqualTo(1234);
        assertThat(r.passed()).isEqualTo(7);
        assertThat(r.ruleEngineVersion()).isEqualTo("qc-1.0.0+abc");
        assertThat(r.blocking()).isTrue();
        assertThat(r.blockingRules()).containsExactly("G-0", "VAL-1");
        assertThat(r.supportingDocumentMissing()).isTrue();
        assertThat(r.missingSupportingDocuments()).containsExactly("engagement");
        assertThat(r.ruleResults()).hasSize(1);
        assertThat(r.ruleResults().get(0).ruleId()).isEqualTo("G-0");
        assertThat(r.ruleResults().get(0).needsVerification()).isTrue();
    }

    @Test
    void unknownFieldsAreIgnored() {
        String json = """
            {"success": true, "some_future_field": {"nested": 1}, "another_new_one": [1,2,3]}
            """;
        PythonQCResponse r = mapper.readValue(json, PythonQCResponse.class);
        assertThat(r.success()).isTrue();
    }

    @Test
    void missingOptionalFieldsBecomeNull() {
        PythonQCResponse r = mapper.readValue("{\"success\": false}", PythonQCResponse.class);
        assertThat(r.success()).isFalse();
        assertThat(r.blocking()).isNull();
        assertThat(r.blockingRules()).isNull();
        assertThat(r.ruleResults()).isNull();
    }

    @Test
    void emptyRuleListDeserializes() {
        PythonQCResponse r = mapper.readValue(
                "{\"success\": true, \"rule_results\": []}", PythonQCResponse.class);
        assertThat(r.ruleResults()).isEqualTo(List.of());
    }
}
