package com.shal.qc.service;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Unit coverage for the QCModelConfig record's compact-constructor normalization
 * (qc module, no Spring context). Together AI is the primary provider; blank/null
 * model ids fall back to defaults so a malformed admin model selection can never push
 * an empty model id into the Python call.
 */
class QCModelConfigTest {

    @Test
    void defaultsAreTogetherStack() {
        QCModelConfig d = QCModelConfig.defaults();
        assertThat(d.provider()).isEqualTo("together");
        assertThat(d.textModel()).isEqualTo("gpt-oss-120b");
        assertThat(d.visionModel()).isEqualTo("llama-4-scout");
        assertThat(d.label()).isEqualTo("together:gpt-oss-120b");
    }

    @Test
    void unknownProviderFallsBackToTogether() {
        assertThat(new QCModelConfig(null, "x", "y").provider()).isEqualTo("together");
        assertThat(new QCModelConfig("", "x", "y").provider()).isEqualTo("together");
    }

    @Test
    void blankOrNullModelsFallBackToDefaults() {
        QCModelConfig c = new QCModelConfig("together", null, "  ");
        assertThat(c.textModel()).isEqualTo("gpt-oss-120b");
        assertThat(c.visionModel()).isEqualTo("llama-4-scout");
    }

    @Test
    void modelIdsAreTrimmed() {
        QCModelConfig c = new QCModelConfig("together", "  custom-text  ", "  custom-vision ");
        assertThat(c.textModel()).isEqualTo("custom-text");
        assertThat(c.visionModel()).isEqualTo("custom-vision");
    }
}
