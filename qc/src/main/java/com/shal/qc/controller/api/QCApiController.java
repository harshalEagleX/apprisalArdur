package com.shal.qc.controller.api;

import com.shal.common.entity.BatchFile;
import com.shal.common.entity.BatchStatus;
import com.shal.common.entity.DocumentMatch;
import com.shal.common.entity.QCResult;
import com.shal.common.entity.Role;
import com.shal.common.repository.BatchFileRepository;
import com.shal.common.repository.BatchRepository;
import com.shal.common.repository.DocumentMatchRepository;
import com.shal.common.entity.QCRuleResult;
import com.shal.common.repository.QCResultRepository;
import com.shal.common.security.UserPrincipal;
import com.shal.qc.service.PythonClientService;
import com.shal.qc.service.QCModelConfig;
import com.shal.qc.service.QCProcessingService;
import com.shal.qc.service.StuckBatchReconciler;
import com.shal.common.service.EnversAuditService;
import com.shal.common.util.TimelineLog;
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
    private final com.shal.common.repository.QCRuleResultRepository qcRuleResultRepository;
    private final PythonClientService pythonClientService;
    private final BatchRepository batchRepository;
    private final BatchFileRepository batchFileRepository;
    private final DocumentMatchRepository documentMatchRepository;
    private final com.shal.common.repository.AppraisalTransactionRepository orderRepository;
    private final StuckBatchReconciler reconciler;
    private final EnversAuditService enversAuditService;
    private final com.shal.common.repository.BusinessEventRepository businessEventRepository;

    public QCApiController(
            QCProcessingService qcProcessingService,
            QCResultRepository qcResultRepository,
            com.shal.common.repository.QCRuleResultRepository qcRuleResultRepository,
            PythonClientService pythonClientService,
            BatchRepository batchRepository,
            BatchFileRepository batchFileRepository,
            DocumentMatchRepository documentMatchRepository,
            com.shal.common.repository.AppraisalTransactionRepository orderRepository,
            StuckBatchReconciler reconciler,
            EnversAuditService enversAuditService,
            com.shal.common.repository.BusinessEventRepository businessEventRepository) {
        this.qcProcessingService = qcProcessingService;
        this.qcResultRepository = qcResultRepository;
        this.qcRuleResultRepository = qcRuleResultRepository;
        this.pythonClientService = pythonClientService;
        this.batchRepository = batchRepository;
        this.batchFileRepository = batchFileRepository;
        this.documentMatchRepository = documentMatchRepository;
        this.orderRepository = orderRepository;
        this.reconciler = reconciler;
        this.enversAuditService = enversAuditService;
        this.businessEventRepository = businessEventRepository;
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

        // Pre-flight: confirm the Python OCR/QC service is reachable BEFORE we claim
        // the batch. Without this, triggering while Python is down would transition
        // the batch to QC_PROCESSING and leave it stuck until the reconciler fires.
        // A fast /live check lets us reject synchronously with a clear message and
        // leave the batch exactly as it was.
        if (!pythonClientService.isHealthy()) {
            log.warn(TimelineLog.event("admin_batches", "java_qc_trigger_rejected",
                    "batch_id", batchId,
                    "reason", "python_service_unavailable",
                    "elapsed_ms", TimelineLog.elapsedMs(started)));
            return ResponseEntity.status(503).body(Map.of(
                "message", "QC service is unavailable — the OCR/QC engine is not responding. "
                        + "The batch was not started; try again once the service is back.",
                "batchId", batchId,
                "status", batch.getStatus() != null ? batch.getStatus().name() : "UNKNOWN",
                "serviceAvailable", false
            ));
        }

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
     * Partial re-run: re-process ONLY the given appraisal files (by BatchFile id). Their prior
     * results are superseded; every other file in the batch keeps its results and reviewer state.
     * Use this to fix a few files in a large batch without wiping review work on the rest.
     */
    @PostMapping("/process/{batchId}/files")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<Map<String, Object>> processFiles(
            @PathVariable @NonNull Long batchId,
            @RequestBody Map<String, Object> body) {
        // Parse the requested appraisal file ids.
        java.util.Set<Long> fileIds = new java.util.LinkedHashSet<>();
        Object raw = body != null ? body.get("fileIds") : null;
        if (raw instanceof java.util.List<?> list) {
            for (Object o : list) {
                try { fileIds.add(Long.valueOf(String.valueOf(o))); } catch (NumberFormatException ignore) { }
            }
        }
        if (fileIds.isEmpty()) {
            return ResponseEntity.badRequest().body(Map.of(
                "message", "fileIds is required — a non-empty list of appraisal file ids to re-run."));
        }
        QCModelConfig modelConfig = new QCModelConfig(
                body.get("provider") instanceof String p ? p : null,
                body.get("textModel") instanceof String t ? t : null,
                body.get("visionModel") instanceof String v ? v : null);

        var batchOpt = batchRepository.findById(batchId);
        if (batchOpt.isEmpty()) {
            return ResponseEntity.notFound().build();
        }
        if (batchOpt.get().getStatus() == BatchStatus.QC_PROCESSING) {
            return ResponseEntity.ok(Map.of(
                "message", "Batch is already being processed", "batchId", batchId, "status", "QC_PROCESSING",
                "pollUrl", "/api/admin/batches/" + batchId + "/status"));
        }

        // Validate every requested file ID belongs to this batch before claiming it.
        // A non-existent or cross-batch ID would silently no-op; return 400 instead.
        List<Long> invalidIds = fileIds.stream()
                .filter(fid -> !batchFileRepository.existsByIdAndBatchId(fid, batchId))
                .collect(java.util.stream.Collectors.toList());
        if (!invalidIds.isEmpty()) {
            return ResponseEntity.badRequest().body(Map.of(
                "error",          "File ID(s) not found in batch " + batchId + ": " + invalidIds,
                "invalidFileIds", invalidIds,
                "batchId",        batchId));
        }

        // Same pre-flight as a full run: reject if Python is down BEFORE claiming the batch.
        if (!pythonClientService.isHealthy()) {
            return ResponseEntity.status(503).body(Map.of(
                "message", "QC service is unavailable — the re-run was not started.", "batchId", batchId,
                "serviceAvailable", false));
        }
        if (!qcProcessingService.claimBatchForProcessing(batchId, modelConfig)) {
            return ResponseEntity.ok(Map.of(
                "message", "Batch could not be claimed for QC", "batchId", batchId,
                "pollUrl", "/api/admin/batches/" + batchId + "/status"));
        }
        long activeReviewSignals = qcRuleResultRepository.countActiveReviewPresenceForBatch(
                batchId, java.time.LocalDateTime.now().minusMinutes(30));
        qcProcessingService.processBatchAsync(batchId, modelConfig, fileIds);
        log.info(TimelineLog.event("admin_batches", "java_qc_partial_rerun_accepted",
                "batch_id", batchId, "file_count", fileIds.size(), "reviewer_active", activeReviewSignals > 0));
        return ResponseEntity.accepted().body(Map.of(
            "message", "Partial QC re-run started", "batchId", batchId, "fileCount", fileIds.size(),
            "reviewerActive", activeReviewSignals > 0,
            "pollUrl", "/api/admin/batches/" + batchId + "/status"));
    }

    /**
     * Run QC for a single Order. Resolves the order to its active appraisal document(s)
     * and re-runs QC on just those files via the same partial-run path a batch uses —
     * so QC is a first-class Order action, not only a batch action.
     */
    @PostMapping("/process/order/{orderId}")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<Map<String, Object>> processOrder(
            @PathVariable @NonNull Long orderId,
            @RequestBody(required = false) Map<String, String> modelRequest) {
        if (!orderRepository.existsById(orderId)) {
            return ResponseEntity.notFound().build();
        }
        return runQcForOrders(List.of(orderId), modelConfigFrom(modelRequest));
    }

    /**
     * Run QC for several selected Orders at once (bulk from the Order view). Each order's
     * active appraisal file is resolved and grouped by batch so every affected batch is
     * claimed once and its files re-run together.
     */
    @PostMapping("/process/orders")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<Map<String, Object>> processOrders(@RequestBody Map<String, Object> body) {
        java.util.LinkedHashSet<Long> orderIds = new java.util.LinkedHashSet<>();
        Object raw = body != null ? body.get("orderIds") : null;
        if (raw instanceof List<?> list) {
            for (Object o : list) {
                try { orderIds.add(Long.valueOf(String.valueOf(o))); } catch (NumberFormatException ignore) { }
            }
        }
        if (orderIds.isEmpty()) {
            return ResponseEntity.badRequest().body(Map.of(
                "message", "orderIds is required — a non-empty list of order ids to run QC on."));
        }
        QCModelConfig modelConfig = new QCModelConfig(
                body.get("provider") instanceof String p ? p : null,
                body.get("textModel") instanceof String t ? t : null,
                body.get("visionModel") instanceof String v ? v : null);
        return runQcForOrders(new java.util.ArrayList<>(orderIds), modelConfig);
    }

    private QCModelConfig modelConfigFrom(Map<String, String> modelRequest) {
        return new QCModelConfig(
                modelRequest != null ? modelRequest.get("provider") : null,
                modelRequest != null ? modelRequest.get("textModel") : null,
                modelRequest != null ? modelRequest.get("visionModel") : null);
    }

    /**
     * Shared engine for single- and bulk-order QC. Resolves each order to its active
     * appraisal file(s), groups by batch, and fires one partial re-run per batch. Never
     * silently no-ops: orders with no runnable appraisal and batches that were already
     * processing are reported back so the caller knows exactly what ran.
     */
    private ResponseEntity<Map<String, Object>> runQcForOrders(List<Long> orderIds, QCModelConfig modelConfig) {
        // Group each order's active appraisal file(s) under their owning batch.
        Map<Long, java.util.LinkedHashSet<Long>> filesByBatch = new LinkedHashMap<>();
        List<Long> ordersWithoutAppraisal = new java.util.ArrayList<>();
        List<Map<String, Object>> incompleteOrders = new java.util.ArrayList<>();
        int resolvedOrders = 0;
        for (Long orderId : orderIds) {
            List<BatchFile> appraisals = batchFileRepository.findActiveByOrderIdAndFileType(
                    orderId, com.shal.common.entity.FileType.APPRAISAL);
            if (appraisals.isEmpty()) {
                ordersWithoutAppraisal.add(orderId);
                continue;
            }
            // Hard completeness gate — an order is NEVER QC'd unless it has all three
            // required documents: appraisal PDF, appraisal XML, and engagement letter.
            List<String> missing = missingRequiredDocs(orderId);
            if (!missing.isEmpty()) {
                Map<String, Object> m = new LinkedHashMap<>();
                m.put("orderId", orderId);
                m.put("missing", missing);
                incompleteOrders.add(m);
                continue;
            }
            resolvedOrders++;
            for (BatchFile appraisal : appraisals) {
                if (appraisal.getBatch() == null) continue;
                filesByBatch.computeIfAbsent(appraisal.getBatch().getId(), k -> new java.util.LinkedHashSet<>())
                        .add(appraisal.getId());
            }
        }

        if (filesByBatch.isEmpty()) {
            String message = !incompleteOrders.isEmpty()
                    ? "QC was not started — the selected order(s) are missing required documents. "
                            + "Appraisal PDF, Appraisal XML, and Engagement letter are ALL required before QC can run."
                    : "No runnable appraisal document was found for the selected order(s). "
                            + "An order needs an active appraisal file before QC can run.";
            return ResponseEntity.badRequest().body(Map.of(
                "message", message,
                "ordersWithoutAppraisal", ordersWithoutAppraisal,
                "incompleteOrders", incompleteOrders));
        }

        // Reject up-front if Python is down — do not claim any batch.
        if (!pythonClientService.isHealthy()) {
            return ResponseEntity.status(503).body(Map.of(
                "message", "QC service is unavailable — the OCR/QC engine is not responding. Nothing was started.",
                "serviceAvailable", false));
        }

        List<Long> startedBatches = new java.util.ArrayList<>();
        List<Long> alreadyRunningBatches = new java.util.ArrayList<>();
        for (Map.Entry<Long, java.util.LinkedHashSet<Long>> e : filesByBatch.entrySet()) {
            Long batchId = e.getKey();
            var batchOpt = batchRepository.findById(batchId);
            if (batchOpt.isPresent() && batchOpt.get().getStatus() == BatchStatus.QC_PROCESSING) {
                alreadyRunningBatches.add(batchId);
                continue;
            }
            if (!qcProcessingService.claimBatchForProcessing(batchId, modelConfig)) {
                alreadyRunningBatches.add(batchId);
                continue;
            }
            qcProcessingService.processBatchAsync(batchId, modelConfig, e.getValue());
            startedBatches.add(batchId);
        }

        log.info(TimelineLog.event("admin_orders", "java_qc_order_run",
                "orders_requested", orderIds.size(),
                "orders_resolved", resolvedOrders,
                "batches_started", startedBatches.size(),
                "batches_already_running", alreadyRunningBatches.size()));

        Map<String, Object> resp = new LinkedHashMap<>();
        resp.put("message", startedBatches.isEmpty()
                ? "No QC run was started — the selected order(s) are already being processed."
                : "QC processing started for " + resolvedOrders + " order(s).");
        resp.put("ordersRequested", orderIds.size());
        resp.put("ordersResolved", resolvedOrders);
        resp.put("startedBatchIds", startedBatches);
        resp.put("alreadyRunningBatchIds", alreadyRunningBatches);
        resp.put("ordersWithoutAppraisal", ordersWithoutAppraisal);
        resp.put("incompleteOrders", incompleteOrders);
        return startedBatches.isEmpty()
                ? ResponseEntity.ok(resp)
                : ResponseEntity.accepted().body(resp);
    }

    /**
     * Required documents for QC. An order is NEVER QC'd unless it has an active
     * appraisal PDF, appraisal XML, and engagement letter. Returns the labels of
     * whichever are missing (empty list = complete). Contract is optional.
     */
    private List<String> missingRequiredDocs(Long orderId) {
        List<String> missing = new java.util.ArrayList<>();
        if (batchFileRepository.findActiveByOrderIdAndFileType(
                orderId, com.shal.common.entity.FileType.APPRAISAL).isEmpty()) {
            missing.add("Appraisal PDF");
        }
        if (batchFileRepository.findActiveByOrderIdAndFileType(
                orderId, com.shal.common.entity.FileType.APPRAISAL_XML).isEmpty()) {
            missing.add("Appraisal XML");
        }
        if (batchFileRepository.findActiveByOrderIdAndFileType(
                orderId, com.shal.common.entity.FileType.ENGAGEMENT).isEmpty()) {
            missing.add("Engagement letter");
        }
        return missing;
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
    public ResponseEntity<List<Map<String, Object>>> getBatchResults(
            @PathVariable @NonNull Long batchId,
            @AuthenticationPrincipal UserPrincipal principal) {
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
        // Project to plain maps inside the @Transactional boundary so Jackson never
        // encounters the LAZY associations (ruleResults, rerunOf, reviewedBy,
        // reviewLockedBy) after the session closes (open-in-view is disabled).
        // batchFile is JOIN FETCH'd by findActiveByBatchIdWithBatchFile.
        List<Map<String, Object>> results = qcResultRepository.findActiveByBatchIdWithBatchFile(batchId)
                .stream()
                .map(r -> {
                    Map<String, Object> m = new java.util.LinkedHashMap<>();
                    m.put("id",               r.getId());
                    m.put("qcDecision",       r.getQcDecision() != null ? r.getQcDecision().name() : null);
                    m.put("finalDecision",    r.getFinalDecision() != null ? r.getFinalDecision().name() : null);
                    m.put("totalRules",       r.getTotalRules());
                    m.put("passedCount",      r.getPassedCount());
                    m.put("failedCount",      r.getFailedCount());
                    m.put("verifyCount",      r.getVerifyCount());
                    m.put("manualPassCount",  r.getManualPassCount());
                    m.put("errorCount",       r.getErrorCount());
                    m.put("score",            null); // no score field on entity
                    m.put("ruleEngineVersion", r.getRuleEngineVersion());
                    m.put("missingDocuments",   r.getMissingDocuments());
                    m.put("rejectionCategory",  r.getRejectionCategory());
                    m.put("rejectionNote",       r.getRejectionNote());
                    m.put("reviewerNotes",       r.getReviewerNotes());
                    m.put("processedAt",        r.getProcessedAt() != null ? r.getProcessedAt().toString() : null);
                    m.put("reviewedAt",         r.getReviewedAt() != null ? r.getReviewedAt().toString() : null);
                    m.put("batchFile", r.getBatchFile() != null
                            ? Map.of("id", r.getBatchFile().getId(),
                                     "filename", r.getBatchFile().getFilename() != null ? r.getBatchFile().getFilename() : "")
                            : null);
                    return m;
                })
                .collect(java.util.stream.Collectors.toList());
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
            idle.put("modelProvider", QCModelConfig.defaults().provider());
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
                        String propertySetName = primary.getPropertySetName();
                        // Multi-property batches store more than one order/engagement/contract
                        // set under the same batch — scope to this file's own set so the
                        // reviewer only sees documents and quality flags for THIS property.
                        // Flat (single-property) batches have a null propertySetName, so fall
                        // back to the whole batch.
                        documents = propertySetName != null
                                ? batchFileRepository.findByBatchIdAndPropertySetName(batchId, propertySetName)
                                : batchFileRepository.findByBatchId(batchId);
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

    /**
     * Per-file event history / audit timeline.
     * Returns all BusinessEvents for a specific BatchFile, plus the active QCResult
     * summary for convenience. Powers the "File History" drawer in the batch detail view.
     */
    @GetMapping("/file-history/{batchFileId}")
    @PreAuthorize("hasRole('ADMIN')")
    @Transactional(readOnly = true)
    public ResponseEntity<Map<String, Object>> getFileHistory(
            @PathVariable @NonNull Long batchFileId) {
        var fileOpt = batchFileRepository.findWithBatchAndReviewerById(batchFileId);
        if (fileOpt.isEmpty()) {
            return ResponseEntity.notFound().build();
        }
        var file = fileOpt.get();

        var events = businessEventRepository.findByBatchFileId(batchFileId);

        List<Map<String, Object>> eventDtos = events.stream().map(e -> {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("id",          e.getId());
            m.put("eventType",   e.getEventType());
            m.put("outcome",     e.getOutcome());
            m.put("sourceLayer", e.getSourceLayer());
            m.put("occurredAt",  e.getOccurredAt() != null ? e.getOccurredAt().toString() : null);
            return m;
        }).collect(java.util.stream.Collectors.toList());

        var activeResult = qcResultRepository.findActiveByBatchFileId(batchFileId);
        Map<String, Object> qcSummary = null;
        if (activeResult.isPresent()) {
            var r = activeResult.get();
            qcSummary = new LinkedHashMap<>();
            qcSummary.put("id",              r.getId());
            qcSummary.put("qcDecision",      r.getQcDecision() != null ? r.getQcDecision().name() : null);
            qcSummary.put("finalDecision",   r.getFinalDecision() != null ? r.getFinalDecision().name() : null);
            qcSummary.put("rejectionCategory", r.getRejectionCategory());
            qcSummary.put("rejectionNote",   r.getRejectionNote());
            qcSummary.put("reviewerNotes",   r.getReviewerNotes());
            qcSummary.put("totalRules",      r.getTotalRules());
            qcSummary.put("passedCount",     r.getPassedCount());
            qcSummary.put("failedCount",     r.getFailedCount());
            qcSummary.put("processedAt",     r.getProcessedAt() != null ? r.getProcessedAt().toString() : null);
            qcSummary.put("reviewedAt",      r.getReviewedAt() != null ? r.getReviewedAt().toString() : null);
            qcSummary.put("rerunOfId",       r.getRerunOf() != null ? r.getRerunOf().getId() : null);
        }

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("batchFileId",    file.getId());
        body.put("filename",       file.getFilename());
        body.put("fileType",       file.getFileType() != null ? file.getFileType().name() : null);
        body.put("status",         file.getStatus() != null ? file.getStatus().name() : null);
        body.put("propertySetName", file.getPropertySetName());
        body.put("events",         eventDtos);
        body.put("activeQcResult", qcSummary);
        return ResponseEntity.ok(body);
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
    @Transactional(readOnly = true)
    public ResponseEntity<List<Map<String, Object>>> getQCHistoryForFile(
            @PathVariable @NonNull Long batchFileId) {
        List<com.shal.common.entity.QCResult> history =
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
    @Transactional(readOnly = true)
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

        // Envers field-level revision trail for this QCResult — shows when qcDecision,
        // passedCount, reviewedAt etc. changed and who changed them. Complements the
        // rule-level diff above (which compares QCRuleResult rows across two separate
        // QC runs) with the entity-level audit history of the current run.
        body.put("auditTrail", enversAuditService.getQCResultRevisions(qcResultId));

        return ResponseEntity.ok(body);
    }

    /**
     * Structured findings export for a batch — JSON by default, {@code ?format=csv}
     * for a flat row-per-finding sheet. This is the artifact an admin downloads and
     * sends to the AMC manually (there is no email path). Per finding it emits:
     * <ul>
     *   <li>the effective status, reflecting any admin override — an approved
     *       override surfaces as WAIVED with the approver and reason, not the
     *       original FAIL;</li>
     *   <li>a revision message with a generic fallback, so a finding is never
     *       dropped just because its template produced no text;</li>
     *   <li>the reviewer's final decision where one was made.</li>
     * </ul>
     * Only active (non-superseded) results are included — the current picture.
     */
    @GetMapping("/findings/{batchId}")
    @PreAuthorize("hasRole('ADMIN')")
    @Transactional(readOnly = true)
    public ResponseEntity<?> exportFindings(
            @PathVariable @NonNull Long batchId,
            @RequestParam(name = "format", defaultValue = "json") String format) {
        var batch = batchRepository.findById(batchId).orElse(null);
        if (batch == null) {
            return ResponseEntity.notFound().build();
        }

        // findActiveByBatchIdWithBatchFile: supersededAt IS NULL + JOIN FETCH batchFile —
        // eliminates both the in-memory superseded-filter race and the batchFile N+1.
        List<QCResult> results = qcResultRepository.findActiveByBatchIdWithBatchFile(batchId);

        List<Map<String, Object>> documents = new java.util.ArrayList<>();
        int totalFindings = 0, totalFail = 0, totalWaived = 0;
        for (QCResult r : results) {
            List<Map<String, Object>> findings = new java.util.ArrayList<>();
            for (QCRuleResult rr : qcRuleResultRepository.findByQcResultId(r.getId())) {
                Map<String, Object> f = findingExport(rr);
                findings.add(f);
                totalFindings++;
                if (Boolean.TRUE.equals(f.get("waived"))) {
                    totalWaived++;
                } else if ("FAIL".equals(f.get("finalStatus"))) {
                    totalFail++;
                }
            }
            Map<String, Object> doc = new LinkedHashMap<>();
            doc.put("qcResultId", r.getId());
            doc.put("filename", r.getBatchFile() != null ? r.getBatchFile().getFilename() : null);
            doc.put("ruleEngineVersion", r.getRuleEngineVersion());
            doc.put("qcDecision", r.getQcDecision() != null ? r.getQcDecision().name() : null);
            doc.put("finalDecision", r.getFinalDecision() != null ? r.getFinalDecision().name() : null);
            doc.put("processedAt", r.getProcessedAt() != null ? r.getProcessedAt().toString() : null);
            doc.put("findings", findings);
            documents.add(doc);
        }

        if ("csv".equalsIgnoreCase(format)) {
            String csv = findingsCsv(batch, documents);
            return ResponseEntity.ok()
                    .header("Content-Type", "text/csv; charset=utf-8")
                    .header("Content-Disposition",
                            "attachment; filename=\"findings_" + batch.getParentBatchId() + ".csv\"")
                    .body(csv);
        }

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("batchId", batch.getId());
        body.put("parentBatchId", batch.getParentBatchId());
        body.put("client", batch.getClient() != null ? batch.getClient().getName() : null);
        body.put("exportedAt", java.time.LocalDateTime.now().toString());
        body.put("summary", Map.of(
                "documents", documents.size(),
                "findings", totalFindings,
                "fail", totalFail,
                "waived", totalWaived));
        body.put("documents", documents);
        return ResponseEntity.ok(body);
    }

    /** Build the per-finding export map, reflecting overrides and message fallback. */
    private Map<String, Object> findingExport(QCRuleResult rr) {
        boolean waived = rr.getOverrideApprovedBy() != null;
        String finalStatus;
        if (waived) {
            finalStatus = "WAIVED";
        } else if (rr.getReviewerVerified() != null) {
            finalStatus = rr.getReviewerVerified() ? "PASS" : "FAIL";
        } else {
            finalStatus = outStatus(rr.getStatus());
        }
        String revision = firstNonBlank(rr.getRejectionText(), rr.getActionItem(), rr.getMessage(),
                "Finding recorded; no revision message available.");

        Map<String, Object> f = new LinkedHashMap<>();
        f.put("ruleId", rr.getRuleId());
        f.put("ruleName", rr.getRuleName());
        f.put("section", rr.getSection());
        f.put("targetField", rr.getTargetField());
        f.put("severity", rr.getSeverity());
        f.put("engineStatus", outStatus(rr.getStatus()));
        f.put("finalStatus", finalStatus);
        f.put("waived", waived);
        f.put("active", "FAIL".equals(finalStatus)); // a finding the AMC must address
        f.put("revisionMessage", revision);
        f.put("appraisalValue", cleanValue(rr.getAppraisalValue()));
        f.put("engagementValue", cleanValue(rr.getEngagementValue()));
        if (waived) {
            f.put("overrideBy", userName(rr.getOverrideApprovedBy()));
            f.put("overrideAt", rr.getOverrideApprovedAt() != null ? rr.getOverrideApprovedAt().toString() : null);
            f.put("overrideReason", emptyToNull(rr.getReviewerComment()));
        }
        return f;
    }

    private String findingsCsv(com.shal.common.entity.Batch batch, List<Map<String, Object>> documents) {
        String client = batch.getClient() != null ? batch.getClient().getName() : "";
        StringBuilder sb = new StringBuilder();
        sb.append("parentBatchId,client,qcResultId,filename,ruleId,ruleName,section,targetField,")
          .append("severity,engineStatus,finalStatus,waived,active,revisionMessage,")
          .append("appraisalValue,engagementValue,overrideBy,overrideReason\n");
        for (Map<String, Object> doc : documents) {
            Object qcResultId = doc.get("qcResultId");
            Object filename = doc.get("filename");
            @SuppressWarnings("unchecked")
            List<Map<String, Object>> findings = (List<Map<String, Object>>) doc.get("findings");
            for (Map<String, Object> f : findings) {
                sb.append(csv(batch.getParentBatchId())).append(',')
                  .append(csv(client)).append(',')
                  .append(csv(qcResultId)).append(',')
                  .append(csv(filename)).append(',')
                  .append(csv(f.get("ruleId"))).append(',')
                  .append(csv(f.get("ruleName"))).append(',')
                  .append(csv(f.get("section"))).append(',')
                  .append(csv(f.get("targetField"))).append(',')
                  .append(csv(f.get("severity"))).append(',')
                  .append(csv(f.get("engineStatus"))).append(',')
                  .append(csv(f.get("finalStatus"))).append(',')
                  .append(csv(f.get("waived"))).append(',')
                  .append(csv(f.get("active"))).append(',')
                  .append(csv(f.get("revisionMessage"))).append(',')
                  .append(csv(f.get("appraisalValue"))).append(',')
                  .append(csv(f.get("engagementValue"))).append(',')
                  .append(csv(f.get("overrideBy"))).append(',')
                  .append(csv(f.get("overrideReason"))).append('\n');
            }
        }
        return sb.toString();
    }

    /** RFC-4180 CSV cell: quote and double embedded quotes. */
    private static String csv(Object value) {
        if (value == null) {
            return "";
        }
        String s = String.valueOf(value);
        if (s.contains("\"") || s.contains(",") || s.contains("\n") || s.contains("\r")) {
            return "\"" + s.replace("\"", "\"\"") + "\"";
        }
        return s;
    }

    private static String outStatus(String status) {
        return status == null || status.isBlank() ? "UNKNOWN" : status.trim().toUpperCase();
    }

    private static String firstNonBlank(String... values) {
        for (String v : values) {
            if (v != null && !v.isBlank()) {
                return v;
            }
        }
        return "";
    }

    private static String emptyToNull(String s) {
        return (s == null || s.isBlank()) ? null : s;
    }

    /** Strip internal sentinel placeholders (e.g. __NO_ENGAGEMENT_VALUE__) from the AMC-facing export. */
    private static String cleanValue(String s) {
        if (s == null || s.isBlank() || s.matches("^__[A-Z_]+__$")) {
            return null;
        }
        return s;
    }

    private static String userName(com.shal.common.entity.User u) {
        if (u == null) {
            return null;
        }
        return u.getFullName() != null && !u.getFullName().isBlank() ? u.getFullName() : u.getUsername();
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
