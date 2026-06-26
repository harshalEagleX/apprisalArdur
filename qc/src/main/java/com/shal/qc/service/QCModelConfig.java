package com.shal.qc.service;

/**
 * Model selection carried into the Python QC service.
 *
 * The platform uses Together AI (cloud) as the PRIMARY LLM provider for structured
 * extraction (gpt-oss-120b), with Groq as the automatic fallback when Together is
 * down or rate-limited. The authoritative model ids live in the Python service
 * config (TOGETHER_MODEL / GROQ_MODEL); these are display/telemetry labels.
 */
public record QCModelConfig(
        String provider,
        String textModel,
        String visionModel) {

    public static QCModelConfig defaults() {
        return new QCModelConfig("together", "gpt-oss-120b", "llama-4-scout");
    }

    public QCModelConfig {
        // Together is the primary provider; Groq is the silent fallback. The label
        // reflects the primary so the UI shows where work actually runs first.
        provider = clean(provider, "together");
        textModel = clean(textModel, "gpt-oss-120b");
        visionModel = clean(visionModel, "llama-4-scout");
    }

    public String label() {
        return provider + ":" + textModel;
    }

    private static String clean(String value, String fallback) {
        return value == null || value.isBlank() ? fallback : value.trim();
    }
}
