package com.apprisal.qc.controller.api;

import com.apprisal.common.entity.QCResult;
import com.apprisal.common.repository.QCResultRepository;
import com.apprisal.qc.service.PythonClientService;
import com.apprisal.qc.service.QCProcessingService;
import com.apprisal.qc.service.QCProcessingService.QCProcessingSummary;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;
import org.springframework.lang.NonNull;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * REST API controller for QC processing operations.
 */
@RestController
@RequestMapping("/api/qc")
public class QCApiController {

    private static final Logger log = LoggerFactory.getLogger(QCApiController.class);

    private final QCProcessingService qcProcessingService;
    private final QCResultRepository qcResultRepository;
    private final PythonClientService pythonClientService;

    public QCApiController(
            QCProcessingService qcProcessingService,
            QCResultRepository qcResultRepository,
            PythonClientService pythonClientService) {
        this.qcProcessingService = qcProcessingService;
        this.qcResultRepository = qcResultRepository;
        this.pythonClientService = pythonClientService;
    }

    /**
     * Trigger QC processing for a batch.
     * POST /api/qc/process/{batchId}
     */
    @PostMapping("/process/{batchId}")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<Map<String, Object>> processBatch(@PathVariable @NonNull Long batchId) {
        log.info("QC processing requested for batch {}", batchId);

        try {
            QCProcessingSummary summary = qcProcessingService.processBatch(batchId);

            Map<String, Object> response = new HashMap<>();
            response.put("success", true);
            response.put("batchId", batchId);
            response.put("totalFiles", summary.totalFiles());
            response.put("autoPass", summary.autoPassCount());
            response.put("toVerify", summary.toVerifyCount());
            response.put("autoFail", summary.autoFailCount());
            response.put("errors", summary.errorCount());
            response.put("batchStatus", summary.batchStatus().name());
            response.put("needsReview", summary.needsReview());

            return ResponseEntity.ok(response);

        } catch (Exception e) {
            log.error("QC processing failed for batch {}: {}", batchId, e.getMessage(), e);

            Map<String, Object> error = new HashMap<>();
            error.put("success", false);
            error.put("error", e.getMessage());
            return ResponseEntity.internalServerError().body(error);
        }
    }

    /**
     * Get QC results for a batch.
     * GET /api/qc/results/{batchId}
     */
    @GetMapping("/results/{batchId}")
    @PreAuthorize("hasAnyRole('ADMIN', 'REVIEWER')")
    public ResponseEntity<List<QCResult>> getBatchResults(@PathVariable @NonNull Long batchId) {
        List<QCResult> results = qcResultRepository.findByBatchId(batchId);
        return ResponseEntity.ok(results);
    }

    /**
     * Get QC result for a specific file.
     * GET /api/qc/file/{fileId}
     */
    @GetMapping("/file/{fileId}")
    @PreAuthorize("hasAnyRole('ADMIN', 'REVIEWER')")
    public ResponseEntity<?> getFileResult(@PathVariable @NonNull Long fileId) {
        return qcResultRepository.findByBatchFileId(fileId)
                .map(ResponseEntity::ok)
                .orElse(ResponseEntity.notFound().build());
    }

    /**
     * Check Python service health.
     * GET /api/qc/health
     */
    @GetMapping("/health")
    public ResponseEntity<Map<String, Object>> checkHealth() {
        boolean healthy = pythonClientService.isHealthy();

        Map<String, Object> response = new HashMap<>();
        response.put("pythonService", healthy ? "healthy" : "unavailable");

        if (healthy) {
            return ResponseEntity.ok(response);
        } else {
            return ResponseEntity.status(503).body(response);
        }
    }

    /**
     * Get available QC rules from Python.
     * GET /api/qc/rules
     */
    @GetMapping("/rules")
    public ResponseEntity<String> getRules() {
        String rules = pythonClientService.getRules();
        if (rules != null) {
            return ResponseEntity.ok(rules);
        }
        return ResponseEntity.status(503).body("{\"error\": \"Python service unavailable\"}");
    }
}
