package com.apprisal.qc.service;

import com.apprisal.common.dto.python.PythonQCResponse;
import com.apprisal.common.dto.python.PythonRuleResult;
import com.apprisal.common.entity.*;
import com.apprisal.common.repository.BatchFileRepository;
import com.apprisal.common.repository.BatchRepository;
import com.apprisal.common.repository.ProcessingMetricsRepository;
import com.apprisal.common.repository.QCResultRepository;
import com.apprisal.common.realtime.RealtimeEventPublisher;
import com.apprisal.common.service.FileMatchingService;
import com.apprisal.common.service.FileMatchingService.FilePair;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Lazy;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.CancellationException;
import java.util.Objects;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.time.Instant;
import org.springframework.lang.NonNull;

/**
 * Main service for QC processing workflow.
 * Orchestrates: file matching → Python call → result storage → decision making.
 */
@Service
public class QCProcessingService {

    private static final Logger log = LoggerFactory.getLogger(QCProcessingService.class);

    private final PythonClientService pythonClient;
    private final FileMatchingService fileMatchingService;
    private final QCResultRepository qcResultRepository;
    private final BatchRepository batchRepository;
    private final BatchFileRepository batchFileRepository;
    private final ProcessingMetricsRepository metricsRepository;
    private final ObjectMapper objectMapper;
    private final RealtimeEventPublisher realtimeEventPublisher;
    private final Map<Long, QCProgress> progressByBatch = new ConcurrentHashMap<>();
    private final Map<Long, Thread> runningThreads = new ConcurrentHashMap<>();
    private final Set<Long> activeBatches = ConcurrentHashMap.newKeySet();
    private final Set<Long> cancellationRequests = ConcurrentHashMap.newKeySet();

    /**
     * Self-injection via @Lazy to break the circular proxy dependency.
     *
     * Spring's AOP proxies cannot intercept THIS.method() calls (self-calls).
     * By injecting ourselves through the container, self.processFilePair(pair)
     * goes through the CGLIB proxy, so @Transactional(REQUIRES_NEW) IS applied.
     * Without this, processFilePair's @Transactional is silently skipped —
     * the BatchFile entity is detached in the EM session of qcResultRepository.save()
     * and Hibernate Envers throws when trying to audit a detached relationship.
     */
    @Autowired @Lazy
    private QCProcessingService self;

    public QCProcessingService(
            PythonClientService pythonClient,
            FileMatchingService fileMatchingService,
            QCResultRepository qcResultRepository,
            BatchRepository batchRepository,
            BatchFileRepository batchFileRepository,
            ProcessingMetricsRepository metricsRepository,
            ObjectMapper objectMapper,
            RealtimeEventPublisher realtimeEventPublisher) {
        this.pythonClient = pythonClient;
        this.fileMatchingService = fileMatchingService;
        this.qcResultRepository = qcResultRepository;
        this.batchRepository = batchRepository;
        this.batchFileRepository = batchFileRepository;
        this.metricsRepository = metricsRepository;
        this.objectMapper = objectMapper;
        this.realtimeEventPublisher = realtimeEventPublisher;
    }

    /**
     * Process QC for an entire batch.
     * PIPELINE: runs synchronously — call from a background thread or Celery task for
     * large batches to avoid blocking the HTTP thread.
     *
     * @param batchId The batch to process
     * @return Summary of processing results
     */
    /**
     * Fire-and-forget async wrapper — returns 202 immediately so the HTTP thread is free.
     * Admin polls GET /api/admin/batches/{id}/status to see progress.
     */
    @Async("qcTaskExecutor")
    public CompletableFuture<QCProcessingSummary> processBatchAsync(@NonNull Long batchId) {
        return processBatchAsync(batchId, QCModelConfig.defaults());
    }

    @Async("qcTaskExecutor")
    public CompletableFuture<QCProcessingSummary> processBatchAsync(@NonNull Long batchId, QCModelConfig modelConfig) {
        QCModelConfig safeModelConfig = modelConfig != null ? modelConfig : QCModelConfig.defaults();
        if (!activeBatches.contains(batchId) && !activeBatches.add(batchId)) {
            log.warn("QC processing for batch {} is already active; ignoring duplicate async request", batchId);
            return CompletableFuture.failedFuture(new IllegalStateException("QC is already running for this batch"));
        }
        Thread existingWorker = runningThreads.putIfAbsent(batchId, Thread.currentThread());
        if (existingWorker != null) {
            log.warn("QC processing for batch {} is already running on thread {}", batchId, existingWorker.getName());
            return CompletableFuture.failedFuture(new IllegalStateException("QC is already running for this batch"));
        }
        try {
            updateProgress(batchId, "queued", "QC job queued", 0, 1, true, safeModelConfig);
            // Call via self (proxy) so transactional helper calls inside processBatch
            // still go through Spring AOP. processBatch itself intentionally does not
            // keep one transaction open during the long Python OCR call.
            QCProcessingSummary result = self.processBatch(batchId, safeModelConfig);
            return CompletableFuture.completedFuture(result);
        } catch (CancellationException e) {
            log.warn("Async QC processing cancelled for batch {}: {}", batchId, e.getMessage());
            updateProgress(batchId, "stopped", "QC stopped by admin", 0, 1, false, safeModelConfig);
            return CompletableFuture.failedFuture(e);
        } catch (Exception e) {
            log.error("Async QC processing failed for batch {}: {}", batchId, e.getMessage(), e);
            updateProgress(batchId, "error", "QC failed: " + e.getMessage(), 0, 1, false, safeModelConfig);
            try {
                // FIX: use @Transactional helper so the re-fetch and save share one session,
                // avoiding the stale-@Version OptimisticLockingFailureException that occurred
                // when the lambda called findById() (detached) + save() in separate transactions.
                self.markBatchError(batchId, "Processing failed: " + e.getMessage());
            } catch (Exception saveEx) {
                log.error("Failed to persist error status for batch {}: {}", batchId, saveEx.getMessage());
            }
            return CompletableFuture.failedFuture(e);
        } finally {
            runningThreads.remove(batchId);
            activeBatches.remove(batchId);
            cancellationRequests.remove(batchId);
        }
    }

    @Transactional
    public boolean claimBatchForProcessing(@NonNull Long batchId, QCModelConfig modelConfig) {
        QCModelConfig safeModelConfig = modelConfig != null ? modelConfig : QCModelConfig.defaults();
        if (!activeBatches.add(batchId)) {
            log.warn("QC claim rejected for batch {} because another worker is active", batchId);
            return false;
        }
        cancellationRequests.remove(batchId);
        int updated = batchRepository.markQcProcessingIfTriggerable(batchId);
        if (updated > 0) {
            updateProgress(batchId, "queued", "QC job queued with " + safeModelConfig.label(), 0, 1, true, safeModelConfig);
            log.info("Claimed batch {} for QC processing using {}", batchId, safeModelConfig.label());
            return true;
        }
        activeBatches.remove(batchId);
        return false;
    }

    @Transactional
    public boolean cancelBatch(@NonNull Long batchId) {
        cancellationRequests.add(batchId);
        Thread worker = runningThreads.get(batchId);
        if (worker != null) {
            worker.interrupt();
        }

        String message = "QC stopped by admin. Click Run QC to start again.";
        int updated = batchRepository.markUploadedIfQcProcessing(batchId, message);
        activeBatches.remove(batchId);
        updateProgress(batchId, "stopped", message, 0, 1, false, QCModelConfig.defaults());
        if (updated > 0) {
            log.warn("QC stop requested for batch {}{}", batchId, worker != null ? " and worker interrupted" : "");
            return true;
        }
        return worker != null;
    }

    /**
     * Atomically re-fetch the batch and set it to ERROR in a single transaction.
     * Using a dedicated @Transactional method (instead of a bare lambda) ensures the
     * findById() and save() share one Hibernate session so the @Version field is
     * consistent and no OptimisticLockingFailureException is thrown.
     */
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void markBatchError(@NonNull Long batchId, String errorMessage) {
        batchRepository.findById(batchId).ifPresent(b -> {
            b.setStatus(BatchStatus.ERROR);
            b.setErrorMessage(errorMessage);
        });
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void saveFinalBatchStatus(@NonNull Long batchId, @NonNull BatchStatus status, String errorMessage) {
        Batch batch = batchRepository.findById(batchId)
                .orElseThrow(() -> new RuntimeException("Batch not found: " + batchId));
        batch.setStatus(status);
        batch.setErrorMessage(errorMessage);
    }

    /**
     * Orchestrates the full batch processing pipeline.
     *
     * NOT @Transactional at the outer level — each sub-operation manages its own
     * short transaction (via self.processFilePair REQUIRES_NEW).  This prevents
     * holding a DB connection open for the full 1-3 min Python processing time.
     * Individual DB saves (setQcProcessing, processFilePair, saveFinalStatus) are
     * each handled inside their own proper transaction through the proxy.
     */
    public @NonNull QCProcessingSummary processBatch(@NonNull Long batchId) {
        return processBatch(batchId, QCModelConfig.defaults());
    }

    public @NonNull QCProcessingSummary processBatch(@NonNull Long batchId, QCModelConfig modelConfig) {
        QCModelConfig safeModelConfig = modelConfig != null ? modelConfig : QCModelConfig.defaults();
        log.info("Starting QC processing for batch {}", batchId);
        updateProgress(batchId, "starting", "Starting QC processing with " + safeModelConfig.label(), 0, 1, true, safeModelConfig);
        throwIfCancelled(batchId);

        Batch batch = batchRepository.findById(batchId)
                .orElseThrow(() -> new RuntimeException("Batch not found: " + batchId));

        if (batch.getStatus() != BatchStatus.QC_PROCESSING) {
            self.saveFinalBatchStatus(batchId, BatchStatus.QC_PROCESSING, null); // Python OCR + rules running
        }
        updateProgress(batchId, "matching", "Matching appraisal, engagement, and contract files", 0, 1, true, safeModelConfig);

        // Get matched file pairs
        List<FilePair> pairs = fileMatchingService.getMatchedPairs(batchId);
        log.info("Found {} file pairs to process", pairs.size());
        updateProgress(batchId, "matched", "Found " + pairs.size() + " appraisal file(s) to process", 0, Math.max(pairs.size(), 1), true, safeModelConfig);

        if (pairs.isEmpty()) {
            log.warn("Batch {} has no matched appraisal-engagement pairs — check folder structure", batchId);
            self.markBatchError(batchId, "No matched appraisal files found");
            updateProgress(batchId, "error", "No matched appraisal files found", 0, 1, false, safeModelConfig);
            return new QCProcessingSummary(0, 0, 0, 0, 0, BatchStatus.ERROR);
        }

        int autoPassCount = 0;
        int toVerifyCount = 0;
        int autoFailCount = 0;
        int errorCount    = 0;

        for (int index = 0; index < pairs.size(); index++) {
            FilePair pair = pairs.get(index);
            try {
                throwIfCancelled(batchId);
                // PIPELINE: check if Python service is available before looping
                if (!pythonClient.isHealthy()) {
                    log.error("Python OCR service is down — aborting batch {} after {} pairs", batchId, errorCount);
                    self.markBatchError(batchId, "Python OCR service unavailable — check that ocr-service is running on port 5001");
                    updateProgress(batchId, "error", "Python OCR service unavailable", index, pairs.size(), false, safeModelConfig);
                    throw new RuntimeException("Python OCR service unavailable");
                }

                updateProgress(batchId, "python", "Running OCR and QC rules for " + pair.getAppraisal().getFilename(), index, pairs.size(), true, safeModelConfig);
                // Call via self (proxy) so @Transactional(REQUIRES_NEW) is applied
                QCResult result = self.processFilePair(pair, safeModelConfig);
                throwIfCancelled(batchId);
                switch (result.getQcDecision()) {
                    case AUTO_PASS -> autoPassCount++;
                    case TO_VERIFY -> toVerifyCount++;
                    case AUTO_FAIL -> autoFailCount++;
                }
                updateProgress(batchId, "saving", "Saved QC result for " + pair.getAppraisal().getFilename(), index + 1, pairs.size(), true, safeModelConfig);
            } catch (CancellationException e) {
                log.warn("Batch {} QC cancelled while processing {}", batchId, pair.getAppraisal().getFilename());
                throw e;
            } catch (Exception e) {
                if (isCancellationRequested(batchId)) {
                    throw new CancellationException("QC stopped by admin");
                }
                log.error("Error processing file pair: appraisal={}, error={}",
                        pair.getAppraisal().getFilename(), e.getMessage(), e);
                errorCount++;
                updateProgress(batchId, "error", "Error processing " + pair.getAppraisal().getFilename(), index + 1, pairs.size(), true, safeModelConfig);
            }
        }

        BatchStatus newStatus = determineBatchStatus(autoPassCount, toVerifyCount, autoFailCount, errorCount);
        self.saveFinalBatchStatus(batchId, newStatus, newStatus == BatchStatus.ERROR ? "All appraisal files failed QC processing" : null);

        log.info("Batch {} QC completed: autoPass={}, toVerify={}, autoFail={}, errors={}. New status: {}",
                batchId, autoPassCount, toVerifyCount, autoFailCount, errorCount, newStatus);
        updateProgress(batchId, "complete", "QC complete: " + newStatus.name().replace('_', ' '), pairs.size(), pairs.size(), false, safeModelConfig);

        return new QCProcessingSummary(pairs.size(), autoPassCount, toVerifyCount, autoFailCount, errorCount, newStatus);
    }

    public QCProgress getProgress(@NonNull Long batchId) {
        return progressByBatch.get(batchId);
    }

    private void throwIfCancelled(Long batchId) {
        if (isCancellationRequested(batchId)) {
            throw new CancellationException("QC stopped by admin");
        }
    }

    private boolean isCancellationRequested(Long batchId) {
        return cancellationRequests.contains(batchId) || Thread.currentThread().isInterrupted();
    }

    private void updateProgress(Long batchId, String stage, String message, int current, int total, boolean running) {
        updateProgress(batchId, stage, message, current, total, running, QCModelConfig.defaults());
    }

    private void updateProgress(Long batchId, String stage, String message, int current, int total, boolean running, QCModelConfig modelConfig) {
        int safeTotal = Math.max(total, 1);
        int safeCurrent = Math.max(0, Math.min(current, safeTotal));
        QCModelConfig safeModelConfig = modelConfig != null ? modelConfig : QCModelConfig.defaults();
        QCProgress progress = progressByBatch.compute(batchId, (id, existing) -> new QCProgress(
                stage,
                message,
                safeCurrent,
                safeTotal,
                running,
                safeModelConfig.provider(),
                safeModelConfig.textModel(),
                safeModelConfig.visionModel(),
                existing != null ? existing.startedAt() : Instant.now().toString(),
                Instant.now().toString()
        ));
        realtimeEventPublisher.publish("/topic/qc/batch/" + batchId + "/progress", progressPayload(batchId, progress));
    }

    private Map<String, Object> progressPayload(Long batchId, QCProgress progress) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("batchId", batchId);
        payload.put("stage", progress.stage());
        payload.put("message", progress.message());
        payload.put("current", progress.current());
        payload.put("total", progress.total());
        payload.put("percent", progress.percent());
        payload.put("running", progress.running());
        payload.put("modelProvider", progress.modelProvider());
        payload.put("modelName", progress.modelName());
        payload.put("visionModel", progress.visionModel());
        payload.put("startedAt", progress.startedAt());
        payload.put("updatedAt", progress.updatedAt());
        return payload;
    }

    /**
     * Process a single file pair and persist QCResult in its own transaction.
     *
     * REQUIRES_NEW: each file pair gets an isolated transaction so:
     * 1. The BatchFile is freshly loaded from the DB (managed entity, not detached).
     *    Without this, Hibernate Envers fails auditing a detached BatchFile reference.
     * 2. A failure on one pair doesn't roll back previously saved pairs.
     * 3. The long Python call (1-3 min) does NOT hold a DB connection open — only
     *    the DB save at the end (milliseconds) holds the transaction.
     */
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    @SuppressWarnings("null")
    public @NonNull QCResult processFilePair(FilePair pair) {
        return processFilePair(pair, QCModelConfig.defaults());
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    @SuppressWarnings("null")
    public @NonNull QCResult processFilePair(FilePair pair, QCModelConfig modelConfig) {
        // Reload BatchFile in THIS transaction so it is a managed (not detached) entity.
        // The `pair.getAppraisal()` object was loaded in a different transaction and is
        // detached here — Hibernate Envers would throw when auditing a detached reference.
        BatchFile appraisal = batchFileRepository.findById(pair.getAppraisal().getId())
                .orElseThrow(() -> new RuntimeException("BatchFile not found: " + pair.getAppraisal().getId()));

        log.debug("Processing pair: appraisal={}, engagement={}",
                appraisal.getFilename(),
                pair.hasEngagement() ? pair.getEngagement().getFilename() : "none");

        // Check if already processed
        if (qcResultRepository.existsByBatchFileId(appraisal.getId())) {
            log.warn("File {} already has QC result, skipping", appraisal.getFilename());
            return qcResultRepository.findByBatchFileId(appraisal.getId())
                    .orElseThrow(() -> new IllegalStateException("QC Result not found"));
        }

        // Call Python service — send all three document types when available
        PythonQCResponse pythonResponse = pythonClient.processQC(
                pair.getAppraisalPath(),
                pair.getEngagementPath(),
                pair.getContractPath(),
                modelConfig);
        throwIfCancelled(appraisal.getBatch().getId());

        // A duplicate worker can pass the first exists check, spend time in Python,
        // and only then discover that another worker already saved the result.
        // Re-check after the long call so the unique constraint is a backstop, not
        // the normal control flow.
        var existingResult = qcResultRepository.findByBatchFileId(appraisal.getId());
        if (existingResult.isPresent()) {
            log.warn("File {} received a QC result while Python was running, reusing existing result",
                    appraisal.getFilename());
            return existingResult.get();
        }

        // Determine decision
        QCDecision decision = determineDecision(pythonResponse);

        // Create QCResult
        QCResult qcResult = QCResult.builder()
                .batchFile(appraisal)
                .qcDecision(decision)
                .pythonResponse(toJson(pythonResponse))
                .totalRules(pythonResponse.totalRules())
                .passedCount(pythonResponse.passed())
                .failedCount(pythonResponse.failed())
                .verifyCount(pythonResponse.verify())
                .errorCount(pythonResponse.systemErrors())
                .skippedCount(pythonResponse.skipped())
                .processingTimeMs(pythonResponse.processingTimeMs())
                .extractionMethod(pythonResponse.extractionMethod())
                .pythonDocumentId(pythonResponse.documentId())
                .cacheHit(pythonResponse.cacheHit())
                .build();

        // Create rule results
        if (pythonResponse.ruleResults() != null) {
            for (PythonRuleResult pr : pythonResponse.ruleResults()) {
                String normalizedStatus = normalizePythonStatus(pr.status());
                boolean needsReview = pr.reviewRequired() || needsVerification(normalizedStatus);
                QCRuleResult ruleResult = QCRuleResult.builder()
                        .ruleId(pr.ruleId())
                        .ruleName(pr.ruleName())
                        .status(normalizedStatus)
                        .message(pr.message())
                        .severity(pr.severity() != null ? pr.severity() : "STANDARD")
                        .details(toJson(pr.details()))
                        .actionItem(pr.actionItem())
                        .needsVerification(needsReview)
                        .reviewRequired(needsReview)
                        .appraisalValue(pr.appraisalValue())
                        .engagementValue(pr.engagementValue())
                        .confidenceScore(pr.confidence())
                        .extractedValue(pr.extractedValue() != null ? String.valueOf(pr.extractedValue()) : null)
                        .expectedValue(pr.expectedValue() != null ? String.valueOf(pr.expectedValue()) : null)
                        .verifyQuestion(pr.verifyQuestion())
                        .rejectionText(pr.rejectionText())
                        .evidence(pr.evidence() != null ? toJson(pr.evidence()) : null)
                        .pdfPage(pr.sourcePage())
                        .bboxX(pr.bboxX())
                        .bboxY(pr.bboxY())
                        .bboxW(pr.bboxW())
                        .bboxH(pr.bboxH())
                        .build();
                qcResult.addRuleResult(ruleResult);
            }
        }

        // Save
        qcResult = Objects.requireNonNull(qcResultRepository.save(qcResult));
        appraisal.setStatus(FileStatus.COMPLETED);
        batchFileRepository.save(appraisal);
        log.info("Saved QC result for file {}: decision={}", appraisal.getFilename(), decision);

        // Capture processing metrics for analytics
        saveMetrics(qcResult, pythonResponse, appraisal);

        return qcResult;
    }

    /**
     * Determine QC decision based on Python response.
     * 
     * NEW PHILOSOPHY:
     * - VERIFY items (OCR uncertain) → TO_VERIFY (human review)
     * - FAIL with no OCR errors → AUTO_FAIL (confident rejection)
     * - FAIL with OCR errors → TO_VERIFY (needs human verification)
     * - All PASS → AUTO_PASS
     */
    private QCDecision determineDecision(PythonQCResponse response) {
        if (response.verify()       != null && response.verify()       > 0) return QCDecision.TO_VERIFY;
        if (response.failed()       != null && response.failed()       > 0) return QCDecision.AUTO_FAIL;
        if (response.systemErrors() != null && response.systemErrors() > 0) return QCDecision.TO_VERIFY;
        return QCDecision.AUTO_PASS;
    }

    private String normalizePythonStatus(String status) {
        if (status == null || status.isBlank()) {
            return "verify";
        }
        return status.trim().toLowerCase();
    }

    private boolean needsVerification(String normalizedStatus) {
        return "fail".equals(normalizedStatus)
                || "verify".equals(normalizedStatus)
                || "system_error".equals(normalizedStatus);
    }

    /**
     * Determine batch status from file-level outcomes.
     *
     * ERROR — every file failed (Python was unreachable or all files are corrupt).
     *         Admin must investigate. Do NOT put this in REVIEW_PENDING because
     *         there are no QCResults for the reviewer to act on.
     *
     * COMPLETED — every file passed all 136 rules automatically.
     *
     * REVIEW_PENDING — at least one file has rules needing human verification.
     *                  This is the normal case for any non-trivial appraisal.
     */
    private BatchStatus determineBatchStatus(int autoPass, int toVerify, int autoFail, int errors) {
        int total = autoPass + toVerify + autoFail + errors;

        // All files errored — Python was down or all files corrupt. Show ERROR so admin
        // gets a visible failure signal instead of an empty REVIEW_PENDING queue.
        if (total > 0 && errors == total) {
            return BatchStatus.ERROR;
        }

        // Everything passed cleanly — no reviewer needed
        if (autoPass > 0 && toVerify == 0 && autoFail == 0 && errors == 0) {
            return BatchStatus.COMPLETED;
        }

        // Mixed results or partial errors — send to reviewer
        return BatchStatus.REVIEW_PENDING;
    }

    private void saveMetrics(QCResult qcResult, PythonQCResponse r, BatchFile file) {
        try {
            int total  = Objects.requireNonNullElse(r.totalRules(), 0);
            int passed = Objects.requireNonNullElse(r.passed(), 0);
            double passRate = total > 0 ? (passed * 100.0 / total) : 0.0;

            // Derive OCR confidence from field_confidence map
            double avgConf = 0.0, minConf = 100.0;
            int lowConfCount = 0;
            if (r.fieldConfidence() != null && !r.fieldConfidence().isEmpty()) {
                var values = r.fieldConfidence().values().stream()
                    .filter(v -> v != null).mapToDouble(Double::doubleValue).toArray();
                if (values.length > 0) {
                    avgConf = java.util.Arrays.stream(values).average().orElse(0);
                    minConf = java.util.Arrays.stream(values).min().orElse(0);
                    lowConfCount = (int) java.util.Arrays.stream(values).filter(v -> v < 70.0).count();
                }
            }

            long procMs = Objects.requireNonNullElse(r.processingTimeMs(), 0);
            ProcessingMetrics metrics = ProcessingMetrics.builder()
                .qcResult(qcResult)
                .correlationId(MDC.get("correlationId"))
                .totalProcessingMs(procMs)
                .ocrTimeMs(procMs)
                .ocrConfidenceAvg(avgConf)
                .ocrConfidenceMin(minConf)
                .fieldsExtracted(r.fieldConfidence() != null ? r.fieldConfidence().size() : 0)
                .fieldsLowConfidence(lowConfCount)
                .extractionMethod(r.extractionMethod())
                .pagesProcessed(Objects.requireNonNullElse(r.totalPages(), 0))
                .rulePassRate(passRate)
                .rulesTotal(total)
                .rulesPassed(passed)
                .rulesFailed(Objects.requireNonNullElse(r.failed(), 0))
                .rulesVerify(Objects.requireNonNullElse(r.verify(), 0))
                .cacheHit(Boolean.TRUE.equals(r.cacheHit()))
                .fileSizeBytes(file.getFileSize())
                .build();

            metricsRepository.save(metrics);
        } catch (Exception e) {
            log.warn("Failed to save processing metrics for file {}: {}", file.getFilename(), e.getMessage());
        }
    }

    private String toJson(Object obj) {
        if (obj == null)
            return null;
        try {
            return objectMapper.writeValueAsString(obj);
        } catch (JacksonException e) {
            log.warn("Failed to serialize to JSON: {}", e.getMessage());
            return null;
        }
    }

    /**
     * Summary of QC processing results.
     */
    public record QCProcessingSummary(
            int totalFiles,
            int autoPassCount,
            int toVerifyCount,
            int autoFailCount,
            int errorCount,
            BatchStatus batchStatus) {
        public boolean isFullyPassed() {
            return autoPassCount == totalFiles && toVerifyCount == 0 && autoFailCount == 0 && errorCount == 0;
        }

        public boolean needsReview() {
            return toVerifyCount > 0 || errorCount > 0;
        }
    }

    public record QCProgress(
            String stage,
            String message,
            int current,
            int total,
            boolean running,
            String modelProvider,
            String modelName,
            String visionModel,
            String startedAt,
            String updatedAt) {
        public int percent() {
            return total > 0 ? Math.min(100, Math.round((current * 100.0f) / total)) : 0;
        }
    }
}
