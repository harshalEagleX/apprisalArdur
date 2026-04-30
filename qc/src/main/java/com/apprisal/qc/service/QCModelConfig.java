package com.apprisal.qc.service;

/**
 * Model selection carried from the admin UI into the Python QC service.
 *
 * Provider support is intentionally explicit. The Python service currently
 * executes Ollama-backed helpers; Claude can be selected in the UI for future
 * wiring and is logged/displayed so admins can see what was requested.
 */
public record QCModelConfig(
        String provider,
        String textModel,
        String visionModel) {

    public static QCModelConfig defaults() {
        return new QCModelConfig("ollama", "llama3:8b-instruct-q4_0", "moondream2");
    }

    public QCModelConfig {
        provider = clean(provider, "ollama").toLowerCase();
        textModel = clean(textModel, provider.equals("claude") ? "claude-3-5-sonnet-latest" : "llama3:8b-instruct-q4_0");
        visionModel = clean(visionModel, "moondream2");
    }

    public String label() {
        return provider + ":" + textModel;
    }

    private static String clean(String value, String fallback) {
        return value == null || value.isBlank() ? fallback : value.trim();
    }
}
