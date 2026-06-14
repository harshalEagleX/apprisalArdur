package com.apprisal.qc.controller.api;

import com.apprisal.common.entity.BatchFile;
import com.apprisal.common.entity.BatchStatus;
import com.apprisal.common.entity.DocumentMatch;
import com.apprisal.common.entity.QCResult;
import com.apprisal.common.entity.Role;
import com.apprisal.common.repository.BatchFileRepository;
import com.apprisal.common.repository.BatchRepository;
import com.apprisal.common.repository.DocumentMatchRepository;
import com.apprisal.common.entity.QCRuleResult;
import com.apprisal.common.repository.QCResultRepository;
import com.apprisal.common.security.UserPrincipal;
import com.apprisal.qc.service.PythonClientService;
import com.apprisal.qc.service.QCModelConfig;
import com.apprisal.qc.service.QCProcessingService;
import com.apprisal.qc.service.StuckBatchReconciler;
import com.apprisal.common.util.TimelineLog;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;
import org.springframework.lang.NonNull;

import java.util.List;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Comparator;

/**
 * REST API for QC processing — ADMIN triggers, REVIEWER+ADMIN reads results.
 */
@RestController
@RequestMapping("/api/qc")
public class QCApiController {

    private static final Logger log = LoggerFactory.getLogger(QCApiController.class);

    private final QCProcessingService qcProcessingService;
    private final QCResultRepository qcResultRepository;
    private final com.apprisal.common.repository.QCRuleResultRepository qcRuleResultRepository;
    private final PythonClientService pythonClientService;
    private final BatchRepository batchRepository;
    private final BatchFileRepository batchFileRepository;
    private final DocumentMatchRepository documentMatchRepository;
    private final StuckBatchReconciler reconciler;

    public QCApiController(
            QCProcessingService qcProcessingService,
            QCResultRepository qcResultRepository,
            com.apprisal.common.repository.QCRuleResultRepository qcRuleResultRepository,
            PythonClientService pythonClientService,
            BatchRepository batchRepository,
            BatchFileRepository batchFileRepository,
            DocumentMatchRepository documentMatchRepository,
            StuckBatchReconciler reconciler) {
        this.qcProcessingService = qcProcessingService;
        this.qcResultRepository = qcResultRepository;
        this.qcRuleResultRepository = qcRuleResultRepository;
        this.pythonClientService = pythonClientService;
        this.batchRepository = batchRepository;
        this.batchFileRepository = batchFileRepository;
        this.documentMatchRepository = documentMatchRepository;
        this.reconciler = reconciler;
    }

    /**
     * Trigger async QC processing for a batch.
     * Returns 202 Accepted immediately — admin polls GET /api/admin/batches/{id}/status.
     */
    @PostMapping("/process/{batchId}")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<Map<String, Object>> processBatch(
            @PathVariable @NonNull Long batchId,
            @RequestBody(required = false) Map<String, String> modelRequest) {
        long started = System.nanoTime();
        QCModelConfig modelConfig = new QCModelConfig(
                modelRequest != null ? modelRequest.get("provider") : null,
                modelRequest != null ? modelRequest.get("textModel") : null,
                modelRequest != null ? modelRequest.get("visionModel") : null);
        log.info(TimelineLog.event("admin_batches", "java_qc_trigger_received",
                "batch_id", batchId,
                "model", modelConfig.label()));
        log.info("QC processing requested for batch {} using {}", batchId, modelConfig.label());

        // Validate batch exists and is in a triggerable state
        var batchOpt = batchRepository.findById(batchId);
        if (batchOpt.isEmpty()) {
            log.warn(TimelineLog.event("admin_batches", "java_qc_trigger_rejected",
                    "batch_id", batchId,
                    "reason", "batch_not_found",
                    "elapsed_ms", TimelineLog.elapsedMs(started)));
            return ResponseEntity.notFound().build();
        }
        var batch = batchOpt.get();

        if (batch.getStatus() == BatchStatus.QC_PROCESSING) {
            log.info(TimelineLog.event("admin_batches", "java_qc_trigger_already_running",
                    "batch_id", batchId,
                    "elapsed_ms", TimelineLog.elapsedMs(started)));
            return ResponseEntity.ok(Map.of(
                "message", "Batch is already being processed",
                "batchId", batchId,
                "status", "QC_PROCESSING",
                "pollUrl", "/api/admin/batches/" + batchId + "/status"
            ));
        }

        // COMPLETED / REVIEW_PENDING / IN_REVIEW batches can be re-processed.
        // The previous QCResults are superseded (not deleted) so history is preserved.
        // Only block if QC is already actively running for this batch.

        if (!qcProcessingService.claimBatchForProcessing(batchId, modelConfig)) {
            var latestStatus = batchRepository.findById(batchId)
                    .map(b -> b.getStatus() != null ? b.getStatus().name() : "UNKNOWN")
                    .orElse("NOT_FOUND");
            log.warn(TimelineLog.event("admin_batches", "java_qc_trigger_claim_failed",
                    "batch_id", batchId,
                    "status", latestStatus,
                    "elapsed_ms", TimelineLog.elapsedMs(started)));
            return ResponseEntity.ok(Map.of(
                "message", "Batch could not be claimed for QC",
                "batchId", batchId,
                "status", latestStatus,
                "pollUrl", "/api/admin/batches/" + batchId + "/status"
            ));
        }

        // Pre-flight: is a reviewer actively reviewing the result this re-run will
        // replace? Computed BEFORE the async run supersedes it. We do NOT block —
        // the reviewer is notified live and their decisions are preserved — but the
        // admin is told so the re-run is never a silent override.
        long activeReviewSignals = qcRuleResultRepository.countActiveReviewPresenceForBatch(
                batchId, java.time.LocalDateTime.now().minusMinutes(30));
        boolean reviewerActive = activeReviewSignals > 0;
        if (reviewerActive) {
            log.info(TimelineLog.event("admin_batches", "java_qc_rerun_reviewer_active",
                    "batch_id", batchId,
                    "active_review_signals", activeReviewSignals));
        }

        // Fire async — returns immediately
        qcProcessingService.processBatchAsync(batchId, modelConfig);

        log.info(TimelineLog.event("admin_batches", "java_qc_trigger_accepted",
                "batch_id", batchId,
                "model", modelConfig.label(),
                "elapsed_ms", TimelineLog.elapsedMs(started),
                "poll_url", "/api/admin/batches/" + batchId + "/status"));
        return ResponseEntity.accepted().body(Map.of(
            "message", "QC processing started",
            "batchId", batchId,
            "modelProvider", modelConfig.provider(),
            "modelName", modelConfig.textModel(),
            "reviewerActive", reviewerActive,
            "pollUrl", "/api/admin/batches/" + batchId + "/status"
        ));
    }

    /**
     * Best-effort stop for a running QC job.
     * If Python is already processing a request, Java interrupts the worker and
     * prevents any late result from being saved when control returns.
     */
    @PostMapping("/cancel/{batchId}")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<Map<String, Object>> cancelBatch(@PathVariable @NonNull Long batchId) {
        if (!batchRepository.existsById(batchId)) {
            return ResponseEntity.notFound().build();
        }

        boolean cancelled = qcProcessingService.cancelBatch(batchId);
        return ResponseEntity.ok(Map.of(
            "message", cancelled ? "QC stop requested" : "QC is not running for this batch",
            "batchId", batchId,
            "cancelled", cancelled,
            "status", cancelled ? "UPLOADED" : batchRepository.findById(batchId)
                    .map(b -> b.getStatus() != null ? b.getStatus().name() : "UNKNOWN")
                    .orElse("NOT_FOUND")
        ));
    }

    /**
     * Get QC results for a batch (ADMIN: any, REVIEWER: own assignments).
     *
     * Returns 404 when the batch itself does not exist.
     * Returns 200 + empty array when the batch exists but QC has not run yet
     * (these are semantically different — the frontend polling loop should stop
     * retrying on 404, but continue on an empty array).
     *
     * @Transactional(readOnly=true) keeps the Hibernate session open while
     * Spring's Jackson converter serialises the lazy associations on QCResult,
     * preventing LazyInitializationException (open-in-view is disabled).
     */
    @GetMapping("/results/{batchId}")
    @PreAuthorize("hasAnyRole('ADMIN', 'REVIEWER')")
    @Transactional(readOnly = true)
    public ResponseEntity<List<QCResult>> getBatchResults(
            @PathVariable @NonNull Long batchId,
            @AuthenticationPrincipal UserPrincipal principal) {
        // FIX: distinguish "batch not found" (404) from "no results yet" (200 + [])
        if (!batchRepository.existsById(batchId)) {
            return ResponseEntity.notFound().build();
        }
        if (principal == null) {
            return ResponseEntity.status(401).build();
        }
        if (principal.getUser().getRole() == Role.REVIEWER
                && !batchRepository.isReviewerAssigned(batchId, principal.getUser().getId())) {
            return ResponseEntity.status(403).build();
        }
        List<QCResult> results = qcResultRepository.findByBatchId(batchId);
        return ResponseEntity.ok(results);
    }

    /**
     * Live QC progress for the admin batch table.
     *
     * This reflects the backend pipeline stage while QC is running: queueing,
     * file matching, Python OCR/rules, saving results, and completion.
     */
    @GetMapping("/progress/{batchId}")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<?> getBatchProgress(@PathVariable @NonNull Long batchId) {
        long started = System.nanoTime();
        if (!batchRepository.existsById(batchId)) {
            return ResponseEntity.notFound().build();
        }

        var progress = qcProcessingService.getProgress(batchId);
        if (progress == null) {
            Map<String, Object> idle = new LinkedHashMap<>();
            idle.put("stage", "idle");
            idle.put("message", "QC has not started");
            idle.put("current", 0);
            idle.put("total", 1);
            idle.put("percent", 0);
            idle.put("smoothedPercent", 0);
            idle.put("running", false);
            idle.put("modelProvider", "ollama");
            idle.put("modelName", QCModelConfig.defaults().textModel());
            idle.put("visionModel", QCModelConfig.defaults().visionModel());
            idle.put("subStage", null);
            idle.put("subMessage", null);
            idle.put("subPercent", 0.0);
            idle.put("subElapsedMs", 0L);
            return ResponseEntity.ok(idle);
        }

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("stage", progress.stage());
        body.put("message", progress.message());
        body.put("current", progress.current());
        body.put("total", progress.total());
        body.put("percent", progress.percent());
        body.put("smoothedPercent", progress.smoothedPercent());
        body.put("running", progress.running());
        body.put("modelProvider", progress.modelProvider());
        body.put("modelName", progress.modelName());
        body.put("visionModel", progress.visionModel());
        body.put("startedAt", progress.startedAt());
        body.put("updatedAt", progress.updatedAt());
        body.put("subStage", progress.subStage());
        body.put("subMessage", progress.subMessage());
        body.put("subPercent", progress.subPercent());
        body.put("subElapsedMs", progress.subElapsedMs());
        log.info(TimelineLog.event("admin_batches", "java_progress_served",
                "batch_id", batchId,
                "stage", progress.stage(),
                "current", progress.current(),
                "total", progress.total(),
                "percent", progress.percent(),
                "running", progress.running(),
                "elapsed_ms", TimelineLog.elapsedMs(started)));
        return ResponseEntity.ok(body);
    }

    /**
     * Get QC result and batchFile info for a specific QC result ID.
     * Used by the reviewer verify page to load the PDF file ID.
     */
    @GetMapping("/file/{qcResultId}")
    @PreAuthorize("hasAnyRole('ADMIN', 'REVIEWER')")
    @Transactional(readOnly = true)
    public ResponseEntity<?> getQCResult(
            @PathVariable @NonNull Long qcResultId,
            @AuthenticationPrincipal UserPrincipal principal) {
        if (principal == null) {
            return ResponseEntity.status(401).build();
        }
        if (principal.getUser().getRole() == Role.REVIEWER
                && !qcResultRepository.isReviewerAssigned(qcResultId, principal.getUser().getId())) {
            return ResponseEntity.status(403).build();
        }
        return qcResultRepository.findWithBatchFileAndBatchById(qcResultId)
                .map(r -> {
                    BatchFile primary = r.getBatchFile();
                    List<BatchFile> documents = List.of();
                    if (primary != null && primary.getBatch() != null) {
                        Long batchId = primary.getBatch().getId();
                        documents = batchFileRepository.findByBatchId(batchId);
                    }

                    List<Map<String, Object>> documentDtos = documents.stream()
                            .sorted(Comparator
                                    .comparing((BatchFile f) -> f.getFileType() != null ? f.getFileType().ordinal() : 99)
                                    .thenComparing(f -> f.getFilename() != null ? f.getFilename() : ""))
                            .map(this::toBatchFileDto)
                            .toList();
                    List<Map<String, Object>> matchDtos = primary != null
                            ? documentMatchRepository.findByAppraisalFile_Id(primary.getId()).stream()
                                    .map(this::toDocumentMatchDto)
                                    .toList()
                            : List.of();

                    Map<String, Object> body = new LinkedHashMap<>();
                    body.put("id", r.getId());
                    body.put("qcDecision", r.getQcDecision() != null ? r.getQcDecision().name() : null);
                    body.put("missingDocuments", r.getMissingDocuments());
                    body.put("batchFile", primary != null ? toBatchFileDto(primary) : null);
                    body.put("documents", documentDtos);
                    body.put("documentMatches", matchDtos);
                    return ResponseEntity.ok(body);
                })
                .orElse(ResponseEntity.notFound().build());
    }

    private Map<String, Object> toBatchFileDto(BatchFile file) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("id", file.getId());
        body.put("filename", file.getFilename() != null ? file.getFilename() : "");
        body.put("fileType", file.getFileType() != null ? file.getFileType().name() : "");
        body.put("documentQualityFlags", file.getDocumentQualityFlags());
        return body;
    }

    private Map<String, Object> toDocumentMatchDto(DocumentMatch match) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("id", match.getId());
        body.put("appraisalFileId", match.getAppraisalFile() != null ? match.getAppraisalFile().getId() : null);
        body.put("supportingFileId", match.getSupportingFile() != null ? match.getSupportingFile().getId() : null);
        body.put("supportingFileType", match.getSupportingFileType() != null ? match.getSupportingFileType().name() : null);
        body.put("supportingFilename", match.getSupportingFile() != null ? match.getSupportingFile().getFilename() : null);
        body.put("matchType", match.getMatchType());
        body.put("confidenceScore", match.getConfidenceScore());
        body.put("matchReason", match.getMatchReason());
        body.put("ambiguousCandidatesJson", match.getAmbiguousCandidatesJson());
        body.put("rejectedCandidatesJson", match.getRejectedCandidatesJson());
        body.put("matchedAt", match.getMatchedAt() != null ? match.getMatchedAt().toString() : null);
        return body;
    }

    /** Python service health check. */
    @GetMapping("/health")
    public ResponseEntity<Map<String, Object>> checkHealth() {
        boolean healthy = pythonClientService.isHealthy();
        return healthy
            ? ResponseEntity.ok(Map.of("pythonService", "healthy"))
            : ResponseEntity.status(503).body(Map.of("pythonService", "unavailable"));
    }

    /** Get available QC rules from Python. */
    @GetMapping("/rules")
    public ResponseEntity<String> getRules() {
        String rules = pythonClientService.getRules();
        return rules != null
            ? ResponseEntity.ok(rules)
            : ResponseEntity.status(503).body("{\"error\": \"Python service unavailable\"}");
    }

    /**
     * Manually trigger stuck-batch reconciliation.
     * Useful when admin notices a batch stuck in QC_PROCESSING.
     * Scheduled reconciler runs automatically every 10 minutes.
     */
    @PostMapping("/reconcile")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<Map<String, Object>> reconcileStuckBatches() {
        log.info("Manual reconciliation triggered by admin");
        var report = reconciler.runManually();
        return ResponseEntity.ok(Map.of(
            "stuckFound",      report.stuckFound(),
            "retried",         report.retried(),
            "abandoned",       report.abandoned(),
            "pythonHealthy",   report.pythonWasHealthy(),
            "message",         report.stuckFound() == 0
                ? "No stuck batches found"
                : report.retried() + " retried, " + report.abandoned() + " abandoned"
        ));
    }

    // ── QC history / versioning ───────────────────────────────────────────────

    /**
     * QC version history for a batch file — active result first, all superseded
     * historical results after, ordered newest to oldest.
     *
     * Used by the frontend "QC History" panel to show what changed across reruns.
     */
    @GetMapping("/history/file/{batchFileId}")
    @PreAuthorize("hasAnyRole('ADMIN','REVIEWER')")
    public ResponseEntity<List<Map<String, Object>>> getQCHistoryForFile(
            @PathVariable @NonNull Long batchFileId) {
        List<com.apprisal.common.entity.QCResult> history =
                qcResultRepository.findAllByBatchFileIdOrderByProcessedAtDesc(batchFileId);
        if (history.isEmpty()) {
            return ResponseEntity.ok(List.of());
        }
        List<Map<String, Object>> body = history.stream().map(r -> {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("id",            r.getId());
            m.put("qcDecision",    r.getQcDecision() != null ? r.getQcDecision().name() : null);
            m.put("finalDecision", r.getFinalDecision() != null ? r.getFinalDecision().name() : null);
            m.put("totalRules",    r.getTotalRules());
            m.put("passedCount",   r.getPassedCount());
            m.put("failedCount",   r.getFailedCount());
            m.put("verifyCount",   r.getVerifyCount());
            m.put("processedAt",   r.getProcessedAt() != null ? r.getProcessedAt().toString() : null);
            m.put("supersededAt",  r.getSupersededAt() != null ? r.getSupersededAt().toString() : null);
            m.put("isActive",      !r.isSuperseded());
            m.put("rerunOfId",     r.getRerunOf() != null ? r.getRerunOf().getId() : null);
            m.put("cacheHit",      r.getCacheHit());
            m.put("extractionMethod", r.getExtractionMethod());
            m.put("ruleEngineVersion", r.getRuleEngineVersion());
            return m;
        }).toList();
        return ResponseEntity.ok(body);
    }

    /**
     * Diff a QC result against the run it replaced (its rerunOf): which findings
     * appeared, disappeared, or changed status/severity between the two versions,
     * keyed by rule id + target field. Stamped with both rule-engine versions so a
     * delta is attributable to a rule change vs a report change. Powers the admin
     * "what changed across reruns" view and the audit/dispute export.
     */
    @GetMapping("/history/diff/{qcResultId}")
    @PreAuthorize("hasAnyRole('ADMIN','REVIEWER')")
    public ResponseEntity<Map<String, Object>> getQCResultDiff(
            @PathVariable @NonNull Long qcResultId) {
        var current = qcResultRepository.findById(qcResultId).orElse(null);
        if (current == null) {
            return ResponseEntity.notFound().build();
        }
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("resultId", current.getId());
        body.put("ruleEngineVersion", current.getRuleEngineVersion());
        var previous = current.getRerunOf();
        if (previous == null) {
            body.put("hasPrevious", false);
            body.put("message", "This is the first QC run for the file — nothing to diff against.");
            return ResponseEntity.ok(body);
        }
        body.put("hasPrevious", true);
        body.put("previousResultId", previous.getId());
        body.put("previousRuleEngineVersion", previous.getRuleEngineVersion());
        body.put("ruleEngineChanged",
                !java.util.Objects.equals(current.getRuleEngineVersion(), previous.getRuleEngineVersion()));

        // Key each finding by rule id + target field so the same rule on two
        // different fields (e.g. two comparables) is diffed independently.
        var curByKey = indexFindings(current.getId());
        var prevByKey = indexFindings(previous.getId());

        List<Map<String, Object>> added = new java.util.ArrayList<>();
        List<Map<String, Object>> removed = new java.util.ArrayList<>();
        List<Map<String, Object>> changed = new java.util.ArrayList<>();
        int unchanged = 0;

        for (var e : curByKey.entrySet()) {
            QCRuleResult cur = e.getValue();
            QCRuleResult prev = prevByKey.get(e.getKey());
            if (prev == null) {
                added.add(findingSummary(cur, null));
            } else if (!sameOutcome(cur, prev)) {
                changed.add(findingSummary(cur, prev));
            } else {
                unchanged++;
            }
        }
        for (var e : prevByKey.entrySet()) {
            if (!curByKey.containsKey(e.getKey())) {
                removed.add(findingSummary(e.getValue(), null));
            }
        }

        body.put("added", added);
        body.put("removed", removed);
        body.put("changed", changed);
        body.put("unchangedCount", unchanged);
        body.put("summary", Map.of(
                "added", added.size(), "removed", removed.size(),
                "changed", changed.size(), "unchanged", unchanged));
        return ResponseEntity.ok(body);
    }

    private Map<String, QCRuleResult> indexFindings(Long resultId) {
        Map<String, QCRuleResult> byKey = new LinkedHashMap<>();
        for (QCRuleResult r : qcRuleResultRepository.findByQcResultId(resultId)) {
            byKey.put(textOr(r.getRuleId(), "?") + "|" + textOr(r.getTargetField(), ""), r);
        }
        return byKey;
    }

    private boolean sameOutcome(QCRuleResult a, QCRuleResult b) {
        return java.util.Objects.equals(norm(a.getStatus()), norm(b.getStatus()))
                && java.util.Objects.equals(norm(a.getSeverity()), norm(b.getSeverity()));
    }

    private Map<String, Object> findingSummary(QCRuleResult r, QCRuleResult prev) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("ruleId", r.getRuleId());
        m.put("ruleName", r.getRuleName());
        m.put("section", r.getSection());
        m.put("targetField", r.getTargetField());
        m.put("status", r.getStatus());
        m.put("severity", r.getSeverity());
        if (prev != null) {
            m.put("previousStatus", prev.getStatus());
            m.put("previousSeverity", prev.getSeverity());
        }
        return m;
    }

    private static String norm(String s) { return s == null ? "" : s.trim().toLowerCase(); }
    private static String textOr(String v, String fallback) { return (v == null || v.isBlank()) ? fallback : v; }
}
