package com.apprisal.qc.service;

/**
 * Model selection carried from the admin UI into the Python QC service.
 *
 * QC is intentionally pinned to one local Ollama model so text and vision
 * decisions cannot drift between model families.
 */
public record QCModelConfig(
        String provider,
        String textModel,
        String visionModel) {

    public static QCModelConfig defaults() {
        return new QCModelConfig("ollama", "llava:13b", "llava:13b");
    }

    public QCModelConfig {
        provider = "ollama";
        textModel = "llava:13b";
        visionModel = "llava:13b";
    }

    public String label() {
        return provider + ":" + textModel;
    }

    private static String clean(String value, String fallback) {
        return value == null || value.isBlank() ? fallback : value.trim();
    }
}
