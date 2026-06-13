package com.apprisal.qc.controller.api;

import com.apprisal.common.entity.DocStat;
import com.apprisal.common.repository.DocStatRepository;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * Admin docStats API — read-only views over the measured QC timing breakdown.
 *
 * All timings served here originate from the Python engine's perf_counter
 * measurements (persisted in {@link DocStat}); nothing is computed or estimated
 * in this controller. ROLE_ADMIN is enforced in SecurityConfig for /api/admin/**.
 */
@RestController
@RequestMapping("/api/admin/doc-stats")
public class DocStatsApiController {

    private final DocStatRepository docStatRepository;

    public DocStatsApiController(DocStatRepository docStatRepository) {
        this.docStatRepository = docStatRepository;
    }

    /** Paginated, searchable list — one row per processed appraisal. */
    @GetMapping
    public ResponseEntity<Map<String, Object>> list(
            @RequestParam(required = false) String q,
            @RequestParam(required = false) Long batchId,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        Pageable pageable = PageRequest.of(Math.max(0, page), Math.min(Math.max(1, size), 100),
                Sort.by(Sort.Direction.DESC, "createdAt"));
        String query = (q == null || q.isBlank()) ? null : q.trim();
        Page<DocStat> result = docStatRepository.search(query, batchId, pageable);

        List<Map<String, Object>> rows = result.getContent().stream()
                .map(DocStatsApiController::toSummary).toList();

        return ResponseEntity.ok(Map.of(
                "content", rows,
                "number", result.getNumber(),
                "totalPages", result.getTotalPages(),
                "totalElements", result.getTotalElements()));
    }

    /** Full timing breakdown for one appraisal (stages + sections + rules). */
    @GetMapping("/{id}")
    public ResponseEntity<Map<String, Object>> detail(@PathVariable Long id) {
        return docStatRepository.findById(id)
                .map(d -> ResponseEntity.ok(toDetail(d)))
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    /** Per-batch rollup: how long QC took across all appraisals in each batch. */
    @GetMapping("/batches")
    public ResponseEntity<List<Map<String, Object>>> batches(
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "25") int size) {
        Pageable pageable = PageRequest.of(Math.max(0, page), Math.min(Math.max(1, size), 100));
        List<Map<String, Object>> rows = docStatRepository.batchRollup(pageable).stream()
                .map(r -> Map.<String, Object>of(
                        "batchId", r[0],
                        "clientName", r[1] != null ? r[1] : "—",
                        "appraisalCount", r[2],
                        "totalMs", r[3] != null ? r[3] : 0.0,
                        "ruleEngineMs", r[4] != null ? r[4] : 0.0,
                        "avgMs", r[5] != null ? r[5] : 0.0,
                        "lastRun", String.valueOf(r[6])))
                .toList();
        return ResponseEntity.ok(rows);
    }

    // ── mappers ─────────────────────────────────────────────────────────────

    private static Map<String, Object> toSummary(DocStat d) {
        var m = new java.util.LinkedHashMap<String, Object>();
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
        m.put("createdAt", String.valueOf(d.getCreatedAt()));
        return m;
    }

    private static Map<String, Object> toDetail(DocStat d) {
        var m = toSummary(d);
        m.put("clientId", d.getClientId());
        m.put("stages", d.getStages().stream()
                .sorted(java.util.Comparator.comparingInt(s -> nz(s.getOrdinal())))
                .map(s -> Map.<String, Object>of(
                        "stage", s.getStage(), "label", s.getLabel(),
                        "ms", nz(s.getMs()), "pctOfPipeline", nz(s.getPctOfPipeline())))
                .toList());
        m.put("sections", d.getSections().stream()
                .sorted(java.util.Comparator.comparingInt(s -> nz(s.getOrdinal())))
                .map(s -> Map.<String, Object>of(
                        "section", s.getSection(), "label", s.getLabel(),
                        "ms", nz(s.getMs()), "ruleCount", s.getRuleCount() != null ? s.getRuleCount() : 0,
                        "pctOfRules", nz(s.getPctOfRules())))
                .toList());
        m.put("rules", d.getRules().stream()
                .sorted(java.util.Comparator.comparingInt(r -> nz(r.getOrdinal())))
                .map(r -> Map.<String, Object>of(
                        "ruleId", r.getRuleId() != null ? r.getRuleId() : "",
                        "ruleName", r.getRuleName() != null ? r.getRuleName() : "",
                        "section", r.getSection() != null ? r.getSection() : "",
                        "status", r.getStatus() != null ? r.getStatus() : "",
                        "ms", nz(r.getMs())))
                .toList());
        return m;
    }

    private static int nz(Integer v)  { return v != null ? v : 0; }
    private static double nz(Double v) { return v != null ? v : 0.0; }
}
