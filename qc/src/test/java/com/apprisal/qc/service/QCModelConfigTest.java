package com.apprisal.qc.service;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Unit coverage for the QCModelConfig record's compact-constructor normalization
 * (qc module, no Spring context). The provider is always pinned to groq and blank/null
 * model ids fall back to defaults, so a malformed admin model selection can never push
 * an empty model id into the Python call.
 */
class QCModelConfigTest {

    @Test
    void defaultsAreGroqStack() {
        QCModelConfig d = QCModelConfig.defaults();
        assertThat(d.provider()).isEqualTo("groq");
        assertThat(d.textModel()).isEqualTo("gpt-oss-120b");
        assertThat(d.visionModel()).isEqualTo("llama-4-scout");
        assertThat(d.label()).isEqualTo("groq:gpt-oss-120b");
    }

    @Test
    void providerIsAlwaysGroqRegardlessOfInput() {
        assertThat(new QCModelConfig("openai", "x", "y").provider()).isEqualTo("groq");
        assertThat(new QCModelConfig(null, "x", "y").provider()).isEqualTo("groq");
    }

    @Test
    void blankOrNullModelsFallBackToDefaults() {
        QCModelConfig c = new QCModelConfig("groq", null, "  ");
        assertThat(c.textModel()).isEqualTo("gpt-oss-120b");
        assertThat(c.visionModel()).isEqualTo("llama-4-scout");
    }

    @Test
    void modelIdsAreTrimmed() {
        QCModelConfig c = new QCModelConfig("groq", "  custom-text  ", "  custom-vision ");
        assertThat(c.textModel()).isEqualTo("custom-text");
        assertThat(c.visionModel()).isEqualTo("custom-vision");
    }
}
