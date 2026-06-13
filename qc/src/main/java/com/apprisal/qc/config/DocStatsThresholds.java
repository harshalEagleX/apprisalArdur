package com.apprisal.qc.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Configuration;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Per-stage "expected maximum" durations (milliseconds) for the docStats UI.
 *
 * A stage whose measured time exceeds its threshold is highlighted in the admin
 * detail view, so a slow run is visible without the admin having to know what
 * "normal" looks like. Defaults are seeded from observed Fantail timings; any of
 * them can be overridden in application.yml under {@code docstats.thresholds.*}
 * without a code change (P-4 config-over-hardcoding).
 */
@Configuration
@ConfigurationProperties(prefix = "docstats")
public class DocStatsThresholds {

    /** stage key -> expected max ms. Overridable via docstats.thresholds.<stage>=<ms>. */
    private Map<String, Long> thresholds = defaults();

    private static Map<String, Long> defaults() {
        Map<String, Long> m = new LinkedHashMap<>();
        m.put("extract_appraisal", 60_000L);  // OCR + field extraction
        m.put("sca_grid", 20_000L);
        m.put("sca_llm", 90_000L);             // LLM grid repair
        m.put("subject_llm", 120_000L);        // LLM gap-fill (the usual hotspot)
        m.put("sketch", 15_000L);
        m.put("photos", 20_000L);
        m.put("extract_engagement", 30_000L);
        m.put("extract_contract", 60_000L);
        m.put("rules", 5_000L);                // whole rule engine
        m.put("extraction", 90_000L);          // folder-path coarse extraction
        return m;
    }

    public Map<String, Long> getThresholds() { return thresholds; }
    public void setThresholds(Map<String, Long> thresholds) {
        // merge over defaults so a partial override still covers every stage
        Map<String, Long> merged = defaults();
        if (thresholds != null) merged.putAll(thresholds);
        this.thresholds = merged;
    }
}
