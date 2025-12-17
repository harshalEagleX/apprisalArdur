package com.apprisal.service;

import com.apprisal.dto.python.PythonQCResponse;
import com.apprisal.dto.python.PythonRuleResult;
import com.apprisal.entity.*;
import com.apprisal.repository.BatchRepository;
import com.apprisal.repository.QCResultRepository;
import com.apprisal.service.FileMatchingService.FilePair;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.Objects;
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
    private final ObjectMapper objectMapper;

    public QCProcessingService(
            PythonClientService pythonClient,
            FileMatchingService fileMatchingService,
            QCResultRepository qcResultRepository,
            BatchRepository batchRepository,
            ObjectMapper objectMapper) {
        this.pythonClient = pythonClient;
        this.fileMatchingService = fileMatchingService;
        this.qcResultRepository = qcResultRepository;
        this.batchRepository = batchRepository;
        this.objectMapper = objectMapper;
    }

    /**
     * Process QC for an entire batch.
     * 
     * @param batchId The batch to process
     * @return Summary of processing results
     */
    @Transactional
    public @NonNull QCProcessingSummary processBatch(@NonNull Long batchId) {
        log.info("Starting QC processing for batch {}", batchId);

        Batch batch = batchRepository.findById(batchId)
                .orElseThrow(() -> new RuntimeException("Batch not found: " + batchId));

        // Update batch status
        batch.setStatus(BatchStatus.QC_PROCESSING);
        batchRepository.save(batch);

        // Get matched file pairs
        List<FilePair> pairs = fileMatchingService.getMatchedPairs(batchId);
        log.info("Found {} file pairs to process", pairs.size());

        int autoPassCount = 0;
        int toVerifyCount = 0;
        int autoFailCount = 0;
        int errorCount = 0;

        // Process each pair
        for (FilePair pair : pairs) {
            try {
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

        // Determine batch status based on results
        BatchStatus newStatus = determineBatchStatus(autoPassCount, toVerifyCount, autoFailCount, errorCount);
        batch.setStatus(newStatus);
        batchRepository.save(batch);

        log.info("Batch {} QC completed: autoPass={}, toVerify={}, autoFail={}, errors={}. New status: {}",
                batchId, autoPassCount, toVerifyCount, autoFailCount, errorCount, newStatus);

        return new QCProcessingSummary(pairs.size(), autoPassCount, toVerifyCount, autoFailCount, errorCount,
                newStatus);
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

        // Call Python service
        PythonQCResponse pythonResponse = pythonClient.processQC(
                pair.getAppraisalPath(),
                pair.getEngagementPath());

        // Determine decision
        QCDecision decision = determineDecision(pythonResponse);

        // Create QCResult
        QCResult qcResult = QCResult.builder()
                .batchFile(appraisal)
                .qcDecision(decision)
                .pythonResponse(toJson(pythonResponse))
                .totalRules(pythonResponse.getTotalRules())
                .passedCount(pythonResponse.getPassed())
                .failedCount(pythonResponse.getFailed())
                .verifyCount(pythonResponse.getVerify()) // NEW: items needing human verification
                .warningCount(pythonResponse.getWarnings())
                .errorCount(pythonResponse.getSystemErrors())
                .skippedCount(pythonResponse.getSkipped())
                .processingTimeMs(pythonResponse.getProcessingTimeMs())
                .extractionMethod(pythonResponse.getExtractionMethod())
                .build();

        // Create rule results
        if (pythonResponse.getRuleResults() != null) {
            for (PythonRuleResult pr : pythonResponse.getRuleResults()) {
                QCRuleResult ruleResult = QCRuleResult.builder()
                        .ruleId(pr.getRuleId())
                        .ruleName(pr.getRuleName())
                        .status(pr.getStatus())
                        .message(pr.getMessage())
                        .details(toJson(pr.getDetails()))
                        .actionItem(pr.getActionItem())
                        .needsVerification(pr.needsVerification())
                        .reviewRequired(pr.isReviewRequired() || pr.needsVerification())
                        .appraisalValue(pr.getAppraisalValue())
                        .engagementValue(pr.getEngagementValue())
                        .build();
                qcResult.addRuleResult(ruleResult);
            }
        }

        // Save
        qcResult = Objects.requireNonNull(qcResultRepository.save(qcResult));
        log.info("Saved QC result for file {}: decision={}", appraisal.getFilename(), decision);

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
        // If there are VERIFY items, route to human review
        if (response.getVerify() > 0) {
            return QCDecision.TO_VERIFY;
        }

        // If there are failures, check if OCR is confident enough
        if (response.getFailed() > 0) {
            // If there are also errors (OCR issues), route to review instead of auto-reject
            if (response.getSystemErrors() > 0) {
                return QCDecision.TO_VERIFY;
            }
            // High confidence failure - but still route to review, never auto-reject
            return QCDecision.TO_VERIFY; // Changed from AUTO_FAIL
        }

        // Warnings and errors need human review
        if (response.getWarnings() > 0 || response.getSystemErrors() > 0) {
            return QCDecision.TO_VERIFY;
        }

        return QCDecision.AUTO_PASS;
    }

    /**
     * Determine batch status based on file decisions.
     * 
     * NEW PHILOSOPHY: Never auto-reject. All issues go to REVIEW_PENDING.
     */
    private BatchStatus determineBatchStatus(int autoPass, int toVerify, int autoFail, int errors) {
        // If everything passed, mark as completed
        if (autoPass > 0 && toVerify == 0 && autoFail == 0 && errors == 0) {
            return BatchStatus.COMPLETED;
        }

        // Any issues → route to human review, never auto-reject
        return BatchStatus.REVIEW_PENDING;
    }

    private String toJson(Object obj) {
        if (obj == null)
            return null;
        try {
            return objectMapper.writeValueAsString(obj);
        } catch (JsonProcessingException e) {
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
