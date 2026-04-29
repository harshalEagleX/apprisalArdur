package com.apprisal.qc.controller.api;

import com.apprisal.common.entity.BatchStatus;
import com.apprisal.common.entity.QCResult;
import com.apprisal.common.repository.BatchRepository;
import com.apprisal.common.repository.QCResultRepository;
import com.apprisal.qc.service.PythonClientService;
import com.apprisal.qc.service.QCProcessingService;
import com.apprisal.qc.service.StuckBatchReconciler;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;
import org.springframework.lang.NonNull;

import java.util.List;
import java.util.Map;

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
    private final StuckBatchReconciler reconciler;

    public QCApiController(
            QCProcessingService qcProcessingService,
            QCResultRepository qcResultRepository,
            PythonClientService pythonClientService,
            BatchRepository batchRepository,
            StuckBatchReconciler reconciler) {
        this.qcProcessingService = qcProcessingService;
        this.qcResultRepository = qcResultRepository;
        this.pythonClientService = pythonClientService;
        this.batchRepository = batchRepository;
        this.reconciler = reconciler;
    }

    /**
     * Trigger async QC processing for a batch.
     * Returns 202 Accepted immediately — admin polls GET /api/admin/batches/{id}/status.
     */
    @PostMapping("/process/{batchId}")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<Map<String, Object>> processBatch(@PathVariable @NonNull Long batchId) {
        log.info("QC processing requested for batch {}", batchId);

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

        // Fire async — returns immediately
        qcProcessingService.processBatchAsync(batchId);

        return ResponseEntity.accepted().body(Map.of(
            "message", "QC processing started",
            "batchId", batchId,
            "pollUrl", "/api/admin/batches/" + batchId + "/status"
        ));
    }

    /**
     * Get QC results for a batch (ADMIN: any, REVIEWER: own assignments).
     */
    @GetMapping("/results/{batchId}")
    @PreAuthorize("hasAnyRole('ADMIN', 'REVIEWER')")
    public ResponseEntity<List<QCResult>> getBatchResults(@PathVariable @NonNull Long batchId) {
        List<QCResult> results = qcResultRepository.findByBatchId(batchId);
        return ResponseEntity.ok(results);
    }

    /**
     * Get QC result and batchFile info for a specific QC result ID.
     * Used by the reviewer verify page to load the PDF file ID.
     */
    @GetMapping("/file/{qcResultId}")
    @PreAuthorize("hasAnyRole('ADMIN', 'REVIEWER')")
    public ResponseEntity<?> getQCResult(@PathVariable @NonNull Long qcResultId) {
        return qcResultRepository.findById(qcResultId)
                .map(r -> ResponseEntity.ok(Map.of(
                        "id", r.getId(),
                        "qcDecision", r.getQcDecision() != null ? r.getQcDecision().name() : null,
                        "batchFile", r.getBatchFile() != null ? Map.of(
                                "id", r.getBatchFile().getId(),
                                "filename", r.getBatchFile().getFilename() != null ? r.getBatchFile().getFilename() : ""
                        ) : null
                )))
                .orElse(ResponseEntity.notFound().build());
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
