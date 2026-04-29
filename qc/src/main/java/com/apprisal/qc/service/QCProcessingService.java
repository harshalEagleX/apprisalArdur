package com.apprisal.qc.service;

import com.apprisal.common.dto.python.PythonQCResponse;
import com.apprisal.common.dto.python.PythonRuleResult;
import com.apprisal.common.entity.*;
import com.apprisal.common.repository.BatchRepository;
import com.apprisal.common.repository.ProcessingMetricsRepository;
import com.apprisal.common.repository.QCResultRepository;
import com.apprisal.common.service.FileMatchingService;
import com.apprisal.common.service.FileMatchingService.FilePair;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.CompletableFuture;
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
    private final ProcessingMetricsRepository metricsRepository;
    private final ObjectMapper objectMapper;

    public QCProcessingService(
            PythonClientService pythonClient,
            FileMatchingService fileMatchingService,
            QCResultRepository qcResultRepository,
            BatchRepository batchRepository,
            ProcessingMetricsRepository metricsRepository,
            ObjectMapper objectMapper) {
        this.pythonClient = pythonClient;
        this.fileMatchingService = fileMatchingService;
        this.qcResultRepository = qcResultRepository;
        this.batchRepository = batchRepository;
        this.metricsRepository = metricsRepository;
        this.objectMapper = objectMapper;
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
        try {
            QCProcessingSummary result = processBatch(batchId);
            return CompletableFuture.completedFuture(result);
        } catch (Exception e) {
            log.error("Async QC processing failed for batch {}: {}", batchId, e.getMessage(), e);
            try {
                batchRepository.findById(batchId).ifPresent(b -> {
                    b.setStatus(BatchStatus.ERROR);
                    b.setErrorMessage("Processing failed: " + e.getMessage());
                    batchRepository.save(b);
                });
            } catch (Exception saveEx) {
                log.error("Failed to persist error status for batch {}: {}", batchId, saveEx.getMessage());
            }
            return CompletableFuture.failedFuture(e);
        }
    }

    @Transactional
    public @NonNull QCProcessingSummary processBatch(@NonNull Long batchId) {
        log.info("Starting QC processing for batch {}", batchId);

        Batch batch = batchRepository.findById(batchId)
                .orElseThrow(() -> new RuntimeException("Batch not found: " + batchId));

        // Guard against concurrent duplicate triggers
        if (batch.getStatus() == BatchStatus.QC_PROCESSING) {
            log.warn("Batch {} is already QC_PROCESSING — ignoring duplicate trigger", batchId);
            return new QCProcessingSummary(0, 0, 0, 0, 0, BatchStatus.QC_PROCESSING);
        }

        // Update batch status
        batch.setStatus(BatchStatus.QC_PROCESSING); // Python OCR + rules running
        batchRepository.save(batch);

        // Get matched file pairs
        List<FilePair> pairs = fileMatchingService.getMatchedPairs(batchId);
        log.info("Found {} file pairs to process", pairs.size());

        if (pairs.isEmpty()) {
            log.warn("Batch {} has no matched appraisal-engagement pairs — check folder structure", batchId);
            batch.setStatus(BatchStatus.ERROR);
            batchRepository.save(batch);
            return new QCProcessingSummary(0, 0, 0, 0, 0, BatchStatus.ERROR);
        }

        int autoPassCount = 0;
        int toVerifyCount = 0;
        int autoFailCount = 0;
        int errorCount    = 0;

        for (FilePair pair : pairs) {
            try {
                // PIPELINE: check if Python service is available before looping
                if (!pythonClient.isHealthy()) {
                    log.error("Python OCR service is down — aborting batch {} after {} pairs", batchId, errorCount);
                    batch.setStatus(BatchStatus.ERROR);
                    batch.setErrorMessage("Python OCR service unavailable — check that ocr-service is running on port 5001");
                    batchRepository.save(batch);
                    throw new RuntimeException("Python OCR service unavailable");
                }

                QCResult result = processFilePair(pair);
                switch (result.getQcDecision()) {
                    case AUTO_PASS -> autoPassCount++;
                    case TO_VERIFY -> toVerifyCount++;
                    case AUTO_FAIL -> autoFailCount++;
                }
            } catch (Exception e) {
                log.error("Error processing file pair: appraisal={}, error={}",
                        pair.getAppraisal().getFilename(), e.getMessage(), e);
                errorCount++;
            }
        }

        BatchStatus newStatus = determineBatchStatus(autoPassCount, toVerifyCount, autoFailCount, errorCount);
        batch.setStatus(newStatus);
        batchRepository.save(batch);

        log.info("Batch {} QC completed: autoPass={}, toVerify={}, autoFail={}, errors={}. New status: {}",
                batchId, autoPassCount, toVerifyCount, autoFailCount, errorCount, newStatus);

        return new QCProcessingSummary(pairs.size(), autoPassCount, toVerifyCount, autoFailCount, errorCount, newStatus);
    }

    /**
     * Process a single file pair through QC.
     */
    @Transactional
    @SuppressWarnings("null")
    public @NonNull QCResult processFilePair(FilePair pair) {
        BatchFile appraisal = pair.getAppraisal();

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
                pair.getContractPath());

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
                .warningCount(pythonResponse.warnings())
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
                QCRuleResult ruleResult = QCRuleResult.builder()
                        .ruleId(pr.ruleId())
                        .ruleName(pr.ruleName())
                        .status(pr.status())
                        .message(pr.message())
                        .severity(pr.severity() != null ? pr.severity() : "STANDARD")
                        .details(toJson(pr.details()))
                        .actionItem(pr.actionItem())
                        .needsVerification(pr.needsVerification())
                        .reviewRequired(pr.reviewRequired() || pr.needsVerification())
                        .appraisalValue(pr.appraisalValue())
                        .engagementValue(pr.engagementValue())
                        .build();
                qcResult.addRuleResult(ruleResult);
            }
        }

        // Save
        qcResult = Objects.requireNonNull(qcResultRepository.save(qcResult));
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
        if (response.verify() > 0)      return QCDecision.TO_VERIFY;
        if (response.failed() > 0)      return QCDecision.TO_VERIFY;
        if (response.warnings() > 0)    return QCDecision.TO_VERIFY;
        if (response.systemErrors() > 0) return QCDecision.TO_VERIFY;
        return QCDecision.AUTO_PASS;
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
            int total  = r.totalRules();
            int passed = r.passed();
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

            ProcessingMetrics metrics = ProcessingMetrics.builder()
                .qcResult(qcResult)
                .correlationId(MDC.get("correlationId"))
                .totalProcessingMs((long) r.processingTimeMs())
                .ocrTimeMs((long) r.processingTimeMs())
                .ocrConfidenceAvg(avgConf)
                .ocrConfidenceMin(minConf)
                .fieldsExtracted(r.fieldConfidence() != null ? r.fieldConfidence().size() : 0)
                .fieldsLowConfidence(lowConfCount)
                .extractionMethod(r.extractionMethod())
                .pagesProcessed(r.totalPages())
                .rulePassRate(passRate)
                .rulesTotal(total)
                .rulesPassed(passed)
                .rulesFailed(r.failed())
                .rulesVerify(r.verify())
                .cacheHit(r.cacheHit())
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
}
