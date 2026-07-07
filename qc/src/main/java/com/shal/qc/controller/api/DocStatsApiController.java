package com.shal.qc.controller.api;

import com.shal.common.entity.DocStat;
import com.shal.common.repository.DocStatRepository;
import com.shal.qc.config.DocStatsThresholds;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.http.ResponseEntity;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;

import java.util.*;

/**
 * Admin docStats API — read-only views over the measured QC timing breakdown.
 *
 * All timings served here originate from the Python engine's perf_counter
 * measurements (persisted in {@link DocStat}); the only values this controller
 * derives are statistical aggregates (percentiles, averages) computed over those
 * real measurements. ROLE_ADMIN is enforced in SecurityConfig for /api/admin/**.
 */
@RestController
@RequestMapping("/api/admin/doc-stats")
public class DocStatsApiController {

    private final DocStatRepository docStatRepository;
    private final DocStatsThresholds thresholds;

    public DocStatsApiController(DocStatRepository docStatRepository, DocStatsThresholds thresholds) {
        this.docStatRepository = docStatRepository;
        this.thresholds = thresholds;
    }

    /** Paginated, searchable list — one row per processed appraisal. */
    @GetMapping
    public ResponseEntity<Map<String, Object>> list(
            @RequestParam(required = false) String q,
            @RequestParam(required = false) Long batchId,
            @RequestParam(defaultValue = "true") boolean latestOnly,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        Pageable pageable = PageRequest.of(Math.max(0, page), Math.min(Math.max(1, size), 100),
                Sort.by(Sort.Direction.DESC, "createdAt"));
        String query = (q == null || q.isBlank()) ? null : q.trim();
        Page<DocStat> result = docStatRepository.search(query, batchId, latestOnly, pageable);

        List<Map<String, Object>> rows = result.getContent().stream()
                .map(DocStatsApiController::toSummary).toList();

        return ResponseEntity.ok(Map.of(
                "content", rows,
                "number", result.getNumber(),
                "totalPages", result.getTotalPages(),
                "totalElements", result.getTotalElements()));
    }

    /** Full timing breakdown for one appraisal (stages + sections + rules).
     *  readOnly tx keeps the session open while the lazy child collections are
     *  mapped (open-in-view is disabled). */
    @GetMapping("/{id}")
    @Transactional(readOnly = true)
    public ResponseEntity<Map<String, Object>> detail(@PathVariable Long id) {
        return docStatRepository.findById(id)
                .map(d -> ResponseEntity.ok(toDetail(d)))
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    /**
     * Per-batch rollup with P50/P95/P99 over each batch's appraisals — answers
     * "how long does a typical appraisal in this batch take, and how bad is the
     * tail?" Percentiles use nearest-rank over the real per-file measurements.
     */
    @GetMapping("/batches")
    public ResponseEntity<List<Map<String, Object>>> batches(
            @RequestParam(defaultValue = "2000") int sample) {
        var rows = docStatRepository.batchTimingRows(PageRequest.of(0, Math.min(Math.max(1, sample), 5000)));

        // group rows by batch
        Map<Long, List<Object[]>> byBatch = new LinkedHashMap<>();
        for (Object[] r : rows) {
            byBatch.computeIfAbsent((Long) r[0], k -> new ArrayList<>()).add(r);
        }

        List<Map<String, Object>> out = new ArrayList<>();
        for (var e : byBatch.entrySet()) {
            List<Object[]> g = e.getValue();
            List<Double> totals   = collect(g, 2);
            List<Double> ruleEng  = collect(g, 3);
            List<Double> pipeline = collect(g, 4);
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("batchId", e.getKey());
            m.put("clientName", g.get(0)[1] != null ? g.get(0)[1] : "—");
            m.put("appraisalCount", g.size());
            m.put("lastRun", String.valueOf(g.get(0)[5]));
            m.put("totalMs", percentiles(totals));
            m.put("ruleEngineMs", percentiles(ruleEng));
            m.put("pipelineMs", percentiles(pipeline));
            out.add(m);
        }
        // newest batch first (rows already came newest-first)
        return ResponseEntity.ok(out);
    }

    /**
     * Cumulative per-rule ranking across all measured runs — average time, LLM
     * call volume, and how often each rule triggers an LLM call. This is the
     * "where to optimize across the corpus" view, not a single run.
     */
    @GetMapping("/rules/ranking")
    public ResponseEntity<List<Map<String, Object>>> ruleRanking(
            @RequestParam(defaultValue = "300") int size) {
        var rows = docStatRepository.ruleRanking(PageRequest.of(0, Math.min(Math.max(1, size), 1000)));
        List<Map<String, Object>> out = new ArrayList<>();
        for (Object[] r : rows) {
            long runs    = ((Number) r[6]).longValue();
            long llmRuns = r[7] != null ? ((Number) r[7]).longValue() : 0L;
            double avgMs = r[3] != null ? ((Number) r[3]).doubleValue() : 0.0;
            double avgConf = r[8] != null ? ((Number) r[8]).doubleValue() : 0.0;
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("ruleId", r[0]);
            m.put("ruleName", r[1]);
            m.put("section", r[2]);
            m.put("avgMs", round3(avgMs));
            m.put("maxMs", round3(r[4] != null ? ((Number) r[4]).doubleValue() : 0.0));
            m.put("llmCalls", r[5] != null ? ((Number) r[5]).longValue() : 0L);
            m.put("runs", runs);
            m.put("llmRuns", llmRuns);
            m.put("pctLlm", runs > 0 ? Math.round(llmRuns * 1000.0 / runs) / 10.0 : 0.0);
            m.put("avgConfidence", round3(avgConf));
            // confidence-per-ms: output quality earned per millisecond spent
            m.put("confidencePerMs", avgMs > 0 ? round3(avgConf / avgMs) : 0.0);
            out.add(m);
        }
        return ResponseEntity.ok(out);
    }

    /** Per-stage expected-max thresholds (ms) so the UI can flag slow stages. */
    @GetMapping("/thresholds")
    public ResponseEntity<Map<String, Long>> thresholds() {
        return ResponseEntity.ok(thresholds.getThresholds());
    }

    /**
     * Time-series of recent runs (oldest→newest) for trend charting — total,
     * rule-engine, and the LLM inference/throttle split. Pass {@code filename}
     * to watch one appraisal's timing across re-runs (did the optimization land?).
     */
    @GetMapping("/trend")
    public ResponseEntity<List<Map<String, Object>>> trend(
            @RequestParam(required = false) String filename,
            @RequestParam(defaultValue = "30") int limit) {
        String f = (filename == null || filename.isBlank()) ? null : filename.trim();
        var rows = docStatRepository.recentTrend(f, PageRequest.of(0, Math.min(Math.max(1, limit), 200)));
        List<Map<String, Object>> out = new ArrayList<>();
        for (Object[] r : rows) {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("id", r[0]);
            m.put("at", String.valueOf(r[1]));
            m.put("filename", r[2]);
            m.put("totalMs", r[3] != null ? ((Number) r[3]).doubleValue() : 0.0);
            m.put("ruleEngineMs", r[4] != null ? ((Number) r[4]).doubleValue() : 0.0);
            m.put("inferenceMs", r[5] != null ? ((Number) r[5]).doubleValue() : 0.0);
            m.put("throttleWaitMs", r[6] != null ? ((Number) r[6]).doubleValue() : 0.0);
            out.add(m);
        }
        Collections.reverse(out); // chronological for the chart
        return ResponseEntity.ok(out);
    }

    /**
     * Before/after timing comparison: this run vs the run it superseded (same
     * file re-QC'd). Returns both detail payloads plus headline deltas so the UI
     * can show whether a change made the file faster or slower.
     */
    @GetMapping("/{id}/compare")
    @Transactional(readOnly = true)
    public ResponseEntity<Map<String, Object>> compare(@PathVariable Long id) {
        var cur = docStatRepository.findById(id).orElse(null);
        if (cur == null) return ResponseEntity.notFound().build();
        var prev = docStatRepository.findPreviousByDocStatId(id).orElse(null);
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("current", toDetail(cur));
        out.put("previous", prev != null ? toDetail(prev) : null);
        if (prev != null) {
            Map<String, Object> delta = new LinkedHashMap<>();
            delta.put("totalMs", diff(cur.getTotalMs(), prev.getTotalMs()));
            delta.put("ruleEngineMs", diff(cur.getRuleEngineMs(), prev.getRuleEngineMs()));
            delta.put("llmInferenceMs", diff(cur.getLlmInferenceMs(), prev.getLlmInferenceMs()));
            delta.put("llmThrottleWaitMs", diff(cur.getLlmThrottleWaitMs(), prev.getLlmThrottleWaitMs()));
            out.put("delta", delta);
        }
        return ResponseEntity.ok(out);
    }

    /** {current, previous, deltaMs, pct} — negative deltaMs means the current run was faster. */
    private static Map<String, Object> diff(Double cur, Double prev) {
        double c = cur != null ? cur : 0.0, p = prev != null ? prev : 0.0;
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("current", round3(c));
        m.put("previous", round3(p));
        m.put("deltaMs", round3(c - p));
        m.put("pct", p > 0 ? Math.round((c - p) / p * 1000.0) / 10.0 : 0.0);
        return m;
    }

    // ── helpers ─────────────────────────────────────────────────────────────

    private static List<Double> collect(List<Object[]> rows, int col) {
        List<Double> v = new ArrayList<>(rows.size());
        for (Object[] r : rows) if (r[col] != null) v.add(((Number) r[col]).doubleValue());
        return v;
    }

    /** {p50, p95, p99, min, max, avg, count} over a value list (nearest-rank). */
    private static Map<String, Object> percentiles(List<Double> values) {
        Map<String, Object> m = new LinkedHashMap<>();
        if (values.isEmpty()) {
            m.put("count", 0);
            for (String k : new String[]{"p50", "p95", "p99", "min", "max", "avg"}) m.put(k, 0.0);
            return m;
        }
        List<Double> s = new ArrayList<>(values);
        Collections.sort(s);
        m.put("count", s.size());
        m.put("p50", round3(nearestRank(s, 50)));
        m.put("p95", round3(nearestRank(s, 95)));
        m.put("p99", round3(nearestRank(s, 99)));
        m.put("min", round3(s.get(0)));
        m.put("max", round3(s.get(s.size() - 1)));
        m.put("avg", round3(s.stream().mapToDouble(Double::doubleValue).average().orElse(0.0)));
        return m;
    }

    private static double nearestRank(List<Double> sorted, int p) {
        if (sorted.isEmpty()) return 0.0;
        int rank = (int) Math.ceil(p / 100.0 * sorted.size());
        int idx = Math.min(Math.max(rank - 1, 0), sorted.size() - 1);
        return sorted.get(idx);
    }

    private static double round3(double v) { return Math.round(v * 1000.0) / 1000.0; }

    private static Map<String, Object> toSummary(DocStat d) {
        var m = new LinkedHashMap<String, Object>();
        m.put("id", d.getId());
        m.put("batchFileId", d.getBatchFileId());
        m.put("batchId", d.getBatchId());
        m.put("filename", d.getFilename());
        m.put("clientName", d.getClientName());
        m.put("qcDecision", d.getQcDecision());
        m.put("totalMs", d.getTotalMs());
        m.put("ruleEngineMs", d.getRuleEngineMs());
        m.put("measuredPipelineMs", d.getMeasuredPipelineMs());
        m.put("ruleCount", d.getRuleCount());
        m.put("slowestStageLabel", d.getSlowestStageLabel());
        m.put("slowestStageMs", d.getSlowestStageMs());
        m.put("slowestSectionLabel", d.getSlowestSectionLabel());
        m.put("slowestSectionMs", d.getSlowestSectionMs());
        m.put("slowestRuleId", d.getSlowestRuleId());
        m.put("slowestRuleName", d.getSlowestRuleName());
        m.put("slowestRuleMs", d.getSlowestRuleMs());
        m.put("llmCalls", d.getLlmCalls());
        m.put("llmInferenceMs", d.getLlmInferenceMs());
        m.put("llmThrottleWaitMs", d.getLlmThrottleWaitMs());
        m.put("rateLimitHits", d.getRateLimitHits());
        m.put("createdAt", String.valueOf(d.getCreatedAt()));
        return m;
    }

    private static Map<String, Object> toDetail(DocStat d) {
        var m = toSummary(d);
        m.put("clientId", d.getClientId());
        m.put("stages", d.getStages().stream()
                .sorted(Comparator.comparingInt(s -> nz(s.getOrdinal())))
                .map(s -> {
                    var x = new LinkedHashMap<String, Object>();
                    x.put("stage", s.getStage());   // display name derived from key in the UI
                    x.put("ms", nz(s.getMs())); x.put("pctOfPipeline", nz(s.getPctOfPipeline()));
                    x.put("llmCalls", nz(s.getLlmCalls()));
                    x.put("inferenceMs", nz(s.getInferenceMs()));
                    x.put("throttleWaitMs", nz(s.getThrottleWaitMs()));
                    return x;
                }).toList());
        m.put("sections", d.getSections().stream()
                .sorted(Comparator.comparingInt(s -> nz(s.getOrdinal())))
                .map(s -> Map.<String, Object>of(
                        "section", s.getSection(), "label", s.getLabel(),
                        "ms", nz(s.getMs()), "ruleCount", s.getRuleCount() != null ? s.getRuleCount() : 0,
                        "pctOfRules", nz(s.getPctOfRules())))
                .toList());
        m.put("rules", d.getRules().stream()
                .sorted(Comparator.comparingInt(r -> nz(r.getOrdinal())))
                .map(r -> {
                    var x = new LinkedHashMap<String, Object>();
                    x.put("ruleId", r.getRuleId() != null ? r.getRuleId() : "");
                    x.put("ruleName", r.getRuleName() != null ? r.getRuleName() : "");
                    x.put("section", r.getSection() != null ? r.getSection() : "");
                    x.put("status", r.getStatus() != null ? r.getStatus() : "");
                    x.put("ms", nz(r.getMs()));
                    x.put("confidence", nz(r.getConfidence()));
                    x.put("llmCalls", nz(r.getLlmCalls()));
                    x.put("llmMs", nz(r.getLlmMs()));
                    x.put("throttleMs", nz(r.getThrottleMs()));
                    return x;
                }).toList());
        return m;
    }

    private static int nz(Integer v)  { return v != null ? v : 0; }
    private static double nz(Double v) { return v != null ? v : 0.0; }
}
