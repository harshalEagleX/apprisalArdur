package com.apprisal.qc.controller.api;

import com.apprisal.common.entity.BatchFile;
import com.apprisal.common.entity.BatchStatus;
import com.apprisal.common.entity.QCResult;
import com.apprisal.common.repository.BatchFileRepository;
import com.apprisal.common.repository.BatchRepository;
import com.apprisal.common.repository.QCResultRepository;
import com.apprisal.qc.service.PythonClientService;
import com.apprisal.qc.service.QCModelConfig;
import com.apprisal.qc.service.QCProcessingService;
import com.apprisal.qc.service.StuckBatchReconciler;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
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
    private final PythonClientService pythonClientService;
    private final BatchRepository batchRepository;
    private final BatchFileRepository batchFileRepository;
    private final StuckBatchReconciler reconciler;

    public QCApiController(
            QCProcessingService qcProcessingService,
            QCResultRepository qcResultRepository,
            PythonClientService pythonClientService,
            BatchRepository batchRepository,
            BatchFileRepository batchFileRepository,
            StuckBatchReconciler reconciler) {
        this.qcProcessingService = qcProcessingService;
        this.qcResultRepository = qcResultRepository;
        this.pythonClientService = pythonClientService;
        this.batchRepository = batchRepository;
        this.batchFileRepository = batchFileRepository;
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
        QCModelConfig modelConfig = new QCModelConfig(
                modelRequest != null ? modelRequest.get("provider") : null,
                modelRequest != null ? modelRequest.get("textModel") : null,
                modelRequest != null ? modelRequest.get("visionModel") : null);
        log.info("QC processing requested for batch {} using {}", batchId, modelConfig.label());

        // Validate batch exists and is in a triggerable state
        var batchOpt = batchRepository.findById(batchId);
        if (batchOpt.isEmpty()) {
            return ResponseEntity.notFound().build();
        }
        var batch = batchOpt.get();

        if (batch.getStatus() == BatchStatus.QC_PROCESSING) {
            return ResponseEntity.ok(Map.of(
                "message", "Batch is already being processed",
                "batchId", batchId,
                "status", "QC_PROCESSING",
                "pollUrl", "/api/admin/batches/" + batchId + "/status"
            ));
        }

        if (batch.getStatus() == BatchStatus.COMPLETED) {
            return ResponseEntity.ok(Map.of(
                "message", "Batch already completed — delete and re-upload to reprocess",
                "batchId", batchId,
                "status", "COMPLETED"
            ));
        }

        if (!qcProcessingService.claimBatchForProcessing(batchId, modelConfig)) {
            var latestStatus = batchRepository.findById(batchId)
                    .map(b -> b.getStatus() != null ? b.getStatus().name() : "UNKNOWN")
                    .orElse("NOT_FOUND");
            return ResponseEntity.ok(Map.of(
                "message", "Batch could not be claimed for QC",
                "batchId", batchId,
                "status", latestStatus,
                "pollUrl", "/api/admin/batches/" + batchId + "/status"
            ));
        }

        // Fire async — returns immediately
        qcProcessingService.processBatchAsync(batchId, modelConfig);

        return ResponseEntity.accepted().body(Map.of(
            "message", "QC processing started",
            "batchId", batchId,
            "modelProvider", modelConfig.provider(),
            "modelName", modelConfig.textModel(),
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
    public ResponseEntity<List<QCResult>> getBatchResults(@PathVariable @NonNull Long batchId) {
        // FIX: distinguish "batch not found" (404) from "no results yet" (200 + [])
        if (!batchRepository.existsById(batchId)) {
            return ResponseEntity.notFound().build();
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
        return ResponseEntity.ok(body);
    }

    /**
     * Get QC result and batchFile info for a specific QC result ID.
     * Used by the reviewer verify page to load the PDF file ID.
     */
    @GetMapping("/file/{qcResultId}")
    @PreAuthorize("hasAnyRole('ADMIN', 'REVIEWER')")
    @Transactional(readOnly = true)
    public ResponseEntity<?> getQCResult(@PathVariable @NonNull Long qcResultId) {
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

                    Map<String, Object> body = new LinkedHashMap<>();
                    body.put("id", r.getId());
                    body.put("qcDecision", r.getQcDecision() != null ? r.getQcDecision().name() : null);
                    body.put("batchFile", primary != null ? toBatchFileDto(primary) : null);
                    body.put("documents", documentDtos);
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
}
