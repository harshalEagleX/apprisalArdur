package com.apprisal.qc.service;

/**
 * Model selection carried from the admin UI into the Python QC service.
 *
 * Default local model uses llava:7b for both OCR-text reading and vision fallbacks.
 */
public record QCModelConfig(
        String provider,
        String textModel,
        String visionModel) {

    public static QCModelConfig defaults() {
        return new QCModelConfig("ollama", "llava:7b", "llava:7b");
    }

    public QCModelConfig {
        provider = "ollama";
        textModel = clean(textModel, "llava:7b");
        visionModel = clean(visionModel, "llava:7b");
    }

    public String label() {
        return provider + ":" + textModel;
    }

    private static String clean(String value, String fallback) {
        return value == null || value.isBlank() ? fallback : value.trim();
    }
}
