package com.apprisal.qc.service;

/**
 * Model selection carried into the Python QC service.
 *
 * The platform uses Groq (cloud) for LLM extraction — a reasoning text model plus a
 * multimodal vision fallback. The authoritative model ids live in the Python service
 * config (GROQ_MODEL / GROQ_VISION_MODEL); these are display/telemetry labels.
 */
public record QCModelConfig(
        String provider,
        String textModel,
        String visionModel) {

    public static QCModelConfig defaults() {
        return new QCModelConfig("groq", "gpt-oss-120b", "llama-4-scout");
    }

    public QCModelConfig {
        provider = "groq";
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
