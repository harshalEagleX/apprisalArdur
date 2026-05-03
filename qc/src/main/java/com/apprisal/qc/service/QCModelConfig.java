package com.apprisal.qc.service;

/**
 * Model selection carried from the admin UI into the Python QC service.
 *
 * Default local models are sized for an 8GB Apple Silicon dev machine.
 * Text commentary uses a text LLM; vision fallbacks use a smaller LLaVA model.
 */
public record QCModelConfig(
        String provider,
        String textModel,
        String visionModel) {

    public static QCModelConfig defaults() {
        return new QCModelConfig("ollama", "llama3.1:8b", "llava:7b");
    }

    public QCModelConfig {
        provider = "ollama";
        textModel = clean(textModel, "llama3.1:8b");
        visionModel = clean(visionModel, "llava:7b");
    }

    public String label() {
        return provider + ":" + textModel;
    }

    private static String clean(String value, String fallback) {
        return value == null || value.isBlank() ? fallback : value.trim();
    }
}
