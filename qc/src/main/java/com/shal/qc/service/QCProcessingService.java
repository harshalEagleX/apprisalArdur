package com.shal.qc.service;

import com.shal.common.dto.python.PythonQCResponse;
import com.shal.common.dto.python.PythonRuleResult;
import com.shal.common.entity.*;
import com.shal.common.repository.BatchFileRepository;
import com.shal.common.repository.BatchRepository;
import com.shal.common.repository.ProcessingMetricsRepository;
import com.shal.common.repository.QCResultRepository;
import com.shal.common.realtime.RealtimeEventPublisher;
import com.shal.common.service.BusinessEventService;
import com.shal.common.service.FileMatchingService;
import com.shal.common.service.FileMatchingService.FilePair;
import com.shal.common.util.AppTime;
import com.shal.common.util.TimelineLog;
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

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;
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
    /** Wire-contract version this backend was built against. A mismatch from Python's
     *  schema_version is logged (not fatal) so a silent payload drift is caught early. */
    private static final String EXPECTED_PYTHON_SCHEMA_VERSION = "1.0";
    private static final String NOT_PROVIDED = "__NOT_PROVIDED__";
    private static final String NO_APPRAISAL_VALUE = "__NO_APPRAISAL_VALUE__";
    private static final String NO_ENGAGEMENT_VALUE = "__NO_ENGAGEMENT_VALUE__";
    private static final String NO_EXTRACTED_VALUE = "__NO_EXTRACTED_VALUE__";
    private static final String NO_EXPECTED_VALUE = "__NO_EXPECTED_VALUE__";

    private final PythonClientService pythonClient;
    private final FileMatchingService fileMatchingService;
    private final QCResultRepository qcResultRepository;
    private final com.shal.common.repository.QCRuleResultRepository qcRuleResultRepository;
    private final BatchRepository batchRepository;
    private final BatchFileRepository batchFileRepository;
    private final ProcessingMetricsRepository metricsRepository;
    private final com.shal.common.repository.DocStatRepository docStatRepository;
    private final ObjectMapper objectMapper;
    private final RealtimeEventPublisher realtimeEventPublisher;
    private final BusinessEventService businessEventService;
    private final com.shal.common.service.OrderStatusService orderStatusService;
    private final com.shal.common.service.LinkageGateService linkageGateService;
    // Cross-node cancellation signal. Backed by Redis in production (so "Stop QC"
    // reaches a worker on another instance) with a graceful in-memory fallback, so
    // single-host behaviour is unchanged. Best-effort — never throws into the pipeline.
    private final com.shal.common.cluster.ClusterCoordinator clusterCoordinator;
    private final Map<Long, QCProgress> progressByBatch = new ConcurrentHashMap<>();
    private final Map<Long, Thread> runningThreads = new ConcurrentHashMap<>();
    private final Map<Long, Instant> batchQcStartedAt = new ConcurrentHashMap<>();
    private final Set<Long> activeBatches = ConcurrentHashMap.newKeySet();
    private final Set<Long> cancellationRequests = ConcurrentHashMap.newKeySet();

    /**
     * Self-injection via @Lazy to break the circular proxy dependency.
     *
     * Spring's AOP proxies cannot intercept THIS.method() calls (self-calls).
     * By injecting ourselves through the container, calls such as
     * self.persistPythonResult(...) go through the CGLIB proxy, so the short
     * save transaction is applied after the long Python call has finished.
     */
    @Autowired @Lazy
    private QCProcessingService self;

    public QCProcessingService(
            PythonClientService pythonClient,
            FileMatchingService fileMatchingService,
            QCResultRepository qcResultRepository,
            com.shal.common.repository.QCRuleResultRepository qcRuleResultRepository,
            BatchRepository batchRepository,
            BatchFileRepository batchFileRepository,
            ProcessingMetricsRepository metricsRepository,
            com.shal.common.repository.DocStatRepository docStatRepository,
            ObjectMapper objectMapper,
            RealtimeEventPublisher realtimeEventPublisher,
            BusinessEventService businessEventService,
            com.shal.common.cluster.ClusterCoordinator clusterCoordinator,
            com.shal.common.service.OrderStatusService orderStatusService,
            com.shal.common.service.LinkageGateService linkageGateService) {
        this.pythonClient = pythonClient;
        this.fileMatchingService = fileMatchingService;
        this.qcResultRepository = qcResultRepository;
        this.qcRuleResultRepository = qcRuleResultRepository;
        this.batchRepository = batchRepository;
        this.batchFileRepository = batchFileRepository;
        this.metricsRepository = metricsRepository;
        this.docStatRepository = docStatRepository;
        this.objectMapper = objectMapper;
        this.realtimeEventPublisher = realtimeEventPublisher;
        this.businessEventService = businessEventService;
        this.clusterCoordinator = clusterCoordinator;
        this.orderStatusService = orderStatusService;
        this.linkageGateService = linkageGateService;
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
        return processBatchAsync(batchId, modelConfig, null);
    }

    /**
     * Partial re-run: when {@code onlyFileIds} is non-empty, only those appraisal files are
     * reprocessed and superseded; all other files keep their results + reviewer state, and the
     * batch status is recomputed from every active result. Empty/null = full-batch run.
     */
    @Async("qcTaskExecutor")
    public CompletableFuture<QCProcessingSummary> processBatchAsync(@NonNull Long batchId, QCModelConfig modelConfig,
                                                                    java.util.Set<Long> onlyFileIds) {
        long asyncStarted = System.nanoTime();
        QCModelConfig safeModelConfig = modelConfig != null ? modelConfig : QCModelConfig.defaults();
        if (!activeBatches.contains(batchId) && !activeBatches.add(batchId)) {
            log.warn("QC already active for batch {} — ignoring duplicate request", batchId);
            return CompletableFuture.failedFuture(new IllegalStateException("QC is already running for this batch"));
        }
        Thread existingWorker = runningThreads.putIfAbsent(batchId, Thread.currentThread());
        if (existingWorker != null) {
            log.warn("QC already running for batch {} on thread {}", batchId, existingWorker.getName());
            return CompletableFuture.failedFuture(new IllegalStateException("QC is already running for this batch"));
        }
        try {
            updateProgress(batchId, "queued", "QC job queued", 0, 1, true, safeModelConfig);
            QCProcessingSummary result = self.processBatch(batchId, safeModelConfig, onlyFileIds);
            log.info("QC worker complete for batch {} → {} in {} ms",
                    batchId, result.batchStatus(), TimelineLog.elapsedMs(asyncStarted));
            return CompletableFuture.completedFuture(result);
        } catch (CancellationException e) {
            log.warn("Async QC processing cancelled for batch {}: {}", batchId, e.getMessage());
            updateProgress(batchId, "stopped", "QC stopped by admin", 0, 1, false, safeModelConfig);
            return CompletableFuture.failedFuture(e);
        } catch (Exception e) {
            log.error("Async QC processing failed for batch {}: {}", batchId, e.getMessage(), e);
            log.error(TimelineLog.event("admin_batches", "java_qc_async_worker_failed",
                    "batch_id", batchId,
                    "elapsed_ms", TimelineLog.elapsedMs(asyncStarted),
                    "error", e.getMessage()));
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
            batchQcStartedAt.remove(batchId);
            cancellationRequests.remove(batchId);
            clusterCoordinator.clearCancel(batchId); // drop the cross-node cancel flag
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
        int updated = batchRepository.markQcProcessingIfTriggerable(batchId, AppTime.now());
        if (updated > 0) {
            batchQcStartedAt.put(batchId, Instant.now());
            updateProgress(batchId, "queued", "QC job queued with " + safeModelConfig.label(), 0, 1, true, safeModelConfig);
            businessEventService.record("BATCH_QC_QUEUED", null, "java", "QUEUED",
                    "Batch", batchId, batchId, null, null, null, Map.of("model", safeModelConfig.label()));
            log.info("Claimed batch {} for QC processing using {}", batchId, safeModelConfig.label());
            log.info(TimelineLog.event("admin_batches", "java_qc_claimed",
                    "batch_id", batchId,
                    "model", safeModelConfig.label(),
                    "status", "QC_PROCESSING"));
            return true;
        }
        activeBatches.remove(batchId);
        return false;
    }

    public boolean isBatchActive(@NonNull Long batchId) {
        return activeBatches.contains(batchId) || runningThreads.containsKey(batchId);
    }

    @Transactional
    public boolean cancelBatch(@NonNull Long batchId) {
        cancellationRequests.add(batchId);
        // Broadcast cluster-wide so a worker on another instance also stops (best-effort).
        clusterCoordinator.signalCancel(batchId);
        Thread worker = runningThreads.get(batchId);
        if (worker != null) {
            worker.interrupt();
        }

        String message = "QC stopped by admin. Click Run QC to start again.";
        int updated = batchRepository.markUploadedIfQcProcessing(batchId, message, AppTime.now());
        activeBatches.remove(batchId);
        updateProgress(batchId, "stopped", message, 0, 1, false, QCModelConfig.defaults());
        if (updated > 0) {
            businessEventService.record("BATCH_QC_CANCELLED", null, "java", "CANCELLED",
                    "Batch", batchId, batchId, null, null, null, Map.of("message", message));
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
    /** Change an AUTO_PASS result to TO_VERIFY when a supporting document match was a guess. */
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void downgradeToVerifyForLowMatchConfidence(
            @NonNull Long qcResultId, double matchConfidence, String documentType) {
        qcResultRepository.findById(qcResultId).ifPresent(r -> {
            if (r.getQcDecision() == QCDecision.AUTO_PASS) {
                r.setQcDecision(QCDecision.TO_VERIFY);
                r.setVerifyCount((r.getVerifyCount() != null ? r.getVerifyCount() : 0) + 1);
                r.setReviewerNotes(documentType + " match confidence was "
                        + String.format("%.0f%%", matchConfidence * 100)
                        + " — verify the correct " + documentType.toLowerCase()
                        + " was paired before accepting these results.");
                qcResultRepository.save(r);
            }
        });
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void appendIntakeWarning(@NonNull Long batchId, String warning) {
        batchRepository.findById(batchId).ifPresent(b -> {
            String existing = b.getIntakeWarnings();
            b.setIntakeWarnings(existing != null && !existing.isBlank()
                    ? existing + "\n" + warning : warning);
        });
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void markBatchError(@NonNull Long batchId, String errorMessage) {
        batchRepository.findById(batchId).ifPresent(b -> {
            b.setStatus(BatchStatus.ERROR);
            b.setErrorMessage(errorMessage);
            businessEventService.batchEvent("BATCH_QC_FAILED", null, b, "ERROR", Map.of("error_message", errorMessage));
        });
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void markFileError(@NonNull Long batchFileId, String errorMessage) {
        batchFileRepository.findById(batchFileId).ifPresent(file -> {
            file.setStatus(FileStatus.ERROR);
            file.setErrorMessage(errorMessage);
        });
    }

    /**
     * Mark the supporting files (engagement letter, contract) in a pair as
     * COMPLETED after the appraisal has been processed successfully.
     *
     * Supporting files never had their FileStatus updated — they stayed PENDING
     * indefinitely even when successfully sent to and extracted by the Python
     * service. This made workbook reports misleadingly show "PENDING" for
     * engagement letters that were in fact processed, causing auditors to
     * conclude the files were "never extracted."
     *
     * Isolated in REQUIRES_NEW so a failure here never rolls back the already-
     * persisted QCResult for the appraisal.
     */
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void markSupportingFilesProcessed(@NonNull FileMatchingService.FilePair pair) {
        if (pair.hasEngagement() && pair.getEngagement().getId() != null) {
            batchFileRepository.findById(pair.getEngagement().getId()).ifPresent(f -> {
                if (f.getStatus() == FileStatus.PENDING) {
                    f.setStatus(FileStatus.COMPLETED);
                    log.debug("Engagement letter {} marked COMPLETED", f.getFilename());
                }
            });
        }
        if (pair.hasContract() && pair.getContract().getId() != null) {
            batchFileRepository.findById(pair.getContract().getId()).ifPresent(f -> {
                if (f.getStatus() == FileStatus.PENDING) {
                    f.setStatus(FileStatus.COMPLETED);
                    log.debug("Contract file {} marked COMPLETED", f.getFilename());
                }
            });
        }
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void saveFinalBatchStatus(@NonNull Long batchId, @NonNull BatchStatus status, String errorMessage) {
        Batch batch = batchRepository.findById(batchId)
                .orElseThrow(() -> new RuntimeException("Batch not found: " + batchId));
        batch.setStatus(status);
        batch.setErrorMessage(errorMessage);
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void touchBatchActivity(@NonNull Long batchId) {
        batchRepository.touchQcProcessing(batchId, AppTime.now());
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
        return processBatch(batchId, modelConfig, null);
    }

    /**
     * Process (or partially re-process) a batch. When {@code onlyFileIds} is non-empty, only those
     * appraisal files are processed; their prior results are superseded while every other file's
     * results and reviewer state are untouched, and the final batch status is recomputed from ALL
     * active results (not just the processed subset).
     */
    public @NonNull QCProcessingSummary processBatch(@NonNull Long batchId, QCModelConfig modelConfig,
                                                     java.util.Set<Long> onlyFileIds) {
        long batchStarted = System.nanoTime();
        boolean partial = onlyFileIds != null && !onlyFileIds.isEmpty();
        QCModelConfig safeModelConfig = modelConfig != null ? modelConfig : QCModelConfig.defaults();
        batchQcStartedAt.putIfAbsent(batchId, Instant.now());
        log.info("QC started for batch {} using {}", batchId, safeModelConfig.label());
        updateProgress(batchId, "starting", "Starting QC processing with " + safeModelConfig.label(), 0, 1, true, safeModelConfig);
        throwIfCancelled(batchId);

        Batch batch = batchRepository.findById(batchId)
                .orElseThrow(() -> new RuntimeException("Batch not found: " + batchId));

        if (batch.getStatus() != BatchStatus.QC_PROCESSING) {
            self.saveFinalBatchStatus(batchId, BatchStatus.QC_PROCESSING, null);
        }
        businessEventService.batchEvent("BATCH_QC_STARTED", null, batch, "STARTED", Map.of("model", safeModelConfig.label()));
        updateProgress(batchId, "matching", "Matching appraisal, engagement, and contract files", 0, 1, true, safeModelConfig);

        // Linkage gate (G-A): an appraisal whose engagement/contract is sitting
        // unresolved elsewhere in this same batch (content sniff found it as a tied
        // candidate at intake, but couldn't auto-link it) must NOT run QC yet — that
        // would silently record NOT_PROVIDED for a document that is actually present,
        // which is exactly the false cross-doc VERIFY flood this gate exists to stop.
        // An appraisal whose supporting doc is genuinely absent from the batch is not
        // held out; that is the legitimate NOT_PROVIDED path.
        java.util.List<com.shal.common.service.LinkageGateService.HeldOutAppraisal> heldOut =
                linkageGateService.computeHoldOuts(batch);
        Set<Long> heldOutIds = heldOut.stream()
                .map(com.shal.common.service.LinkageGateService.HeldOutAppraisal::appraisalFileId)
                .collect(java.util.stream.Collectors.toSet());
        if (!heldOut.isEmpty()) {
            String note = heldOut.size() + " appraisal(s) held out of this QC run — an unresolved candidate "
                    + "document exists in this batch for them:\n" + heldOut.stream()
                            .map(h -> "\"" + h.appraisalFilename() + "\" — candidate(s): "
                                    + String.join(", ", h.candidateFilenames())
                                    + ". Use the Assign button to link the correct one, then Re-QC.")
                            .collect(java.util.stream.Collectors.joining("\n"));
            try {
                self.appendIntakeWarning(batchId, note);
            } catch (Exception warnEx) {
                log.warn("Could not persist linkage-gate warning for batch {}: {}", batchId, warnEx.getMessage());
            }
        }

        List<FilePair> pairs = fileMatchingService.getMatchedPairs(batchId);
        if (!heldOutIds.isEmpty()) {
            pairs = pairs.stream()
                    .filter(p -> p.getAppraisal() == null || !heldOutIds.contains(p.getAppraisal().getId()))
                    .toList();
        }
        if (partial) {
            pairs = pairs.stream()
                    .filter(p -> p.getAppraisal() != null && onlyFileIds.contains(p.getAppraisal().getId()))
                    .toList();
            if (pairs.isEmpty()) {
                BatchStatus restored = recomputeBatchStatusFromActiveResults(batchId);
                self.saveFinalBatchStatus(batchId, restored, null);
                updateProgress(batchId, "complete", "No matching files to re-run", 0, 1, false, safeModelConfig);
                return new QCProcessingSummary(0, 0, 0, 0, 0, restored);
            }
        }
        log.info("QC batch {} — {} file pair(s) to process", batchId, pairs.size());
        // Surface any ambiguous pairing warnings to the admin batch detail.
        // Warnings are appended (not replaced) so they survive a partial re-run.
        String matchWarnings = fileMatchingService.collectMatchWarnings(batchId);
        if (!matchWarnings.isBlank()) {
            try {
                self.appendIntakeWarning(batchId, matchWarnings);
            } catch (Exception warnEx) {
                log.warn("Could not persist match warnings for batch {}: {}", batchId, warnEx.getMessage());
            }
        }
        updateProgress(batchId, "matched", "Found " + pairs.size() + " appraisal file(s) to process", 0, Math.max(pairs.size(), 1), true, safeModelConfig);

        if (pairs.isEmpty()) {
            if (!heldOutIds.isEmpty()) {
                // Every appraisal in this batch is held out pending manual linkage —
                // not a system error, but BatchStatus's forward-only state machine only
                // allows QC_PROCESSING → {REVIEW_PENDING, COMPLETED, ERROR}, so ERROR is
                // the legal target; the message (surfaced via intakeWarnings above and
                // errorMessage here) makes clear this needs the Assign button, not a rerun.
                log.info("Batch {} — all {} appraisal(s) held out pending linkage resolution", batchId, heldOutIds.size());
                self.markBatchError(batchId, "Held out pending manual document assignment — see warnings for which files to assign, then Re-QC.");
                updateProgress(batchId, "complete", "Held out pending manual document assignment", 0, 1, false, safeModelConfig);
                return new QCProcessingSummary(0, 0, 0, 0, 0, BatchStatus.ERROR);
            }
            log.warn("Batch {} has no matched appraisal-engagement pairs — check folder structure", batchId);
            self.markBatchError(batchId, "No matched appraisal files found");
            updateProgress(batchId, "error", "No matched appraisal files found", 0, 1, false, safeModelConfig);
            return new QCProcessingSummary(0, 0, 0, 0, 0, BatchStatus.ERROR);
        }

        int autoPassCount = 0;
        int toVerifyCount = 0;
        int autoFailCount = 0;
        int errorCount    = 0;
        List<String> fileErrors = new ArrayList<>();

        for (int index = 0; index < pairs.size(); index++) {
            FilePair pair = pairs.get(index);
            long pairStarted = System.nanoTime();
            try {
                throwIfCancelled(batchId);
                // PIPELINE: check if Python service is available before looping
                if (!pythonClient.isHealthy()) {
                    log.error("Python OCR service is down — aborting batch {} after {} pairs", batchId, errorCount);
                    self.markBatchError(batchId, "Python OCR service unavailable — check that ocr-service is running on port 5001");
                    updateProgress(batchId, "error", "Python OCR service unavailable", index, pairs.size(), false, safeModelConfig);
                    throw new RuntimeException("Python OCR service unavailable");
                }

                // Neutral top-level label so it never contradicts the sub-stage (which carries
                // the precise queued/started/running state). "Running OCR" while the sub-stage
                // says "queued — waiting for worker" was the confusing 2%+queued+running display.
                updateProgress(batchId, "python", "Processing " + pair.getAppraisal().getFilename(), index, pairs.size(), true, safeModelConfig);
                log.debug(TimelineLog.event("admin_batches", "java_qc_file_start",
                        "batch_id", batchId,
                        "batch_file_id", pair.getAppraisal().getId(),
                        "file_index", index + 1,
                        "file_total", pairs.size(),
                        "appraisal", pair.getAppraisal().getFilename(),
                        "engagement", pair.hasEngagement() ? pair.getEngagement().getFilename() : "none",
                        "contract", pair.hasContract() ? pair.getContract().getFilename() : "none"));
                // processFilePair intentionally keeps the long Python call outside a DB transaction.
                QCResult result = self.processFilePair(pair, safeModelConfig);
                throwIfCancelled(batchId);
                // Mark engagement letter and contract as COMPLETED now that the pair
                // has been successfully processed. Best-effort: a failure here must
                // not undo the already-persisted QCResult (hence the separate tx).
                try {
                    self.markSupportingFilesProcessed(pair);
                } catch (Exception suppEx) {
                    log.warn("Failed to update supporting-file status for appraisal {}: {}",
                            pair.getAppraisal().getFilename(), suppEx.getMessage());
                }
                switch (result.getQcDecision()) {
                    case AUTO_PASS -> autoPassCount++;
                    case TO_VERIFY -> toVerifyCount++;
                    case AUTO_FAIL -> autoFailCount++;
                    case BLOCKED   -> toVerifyCount++;   // blocked routes to human review
                }
                log.debug(TimelineLog.event("admin_batches", "java_qc_file_complete",
                        "batch_id", batchId,
                        "batch_file_id", pair.getAppraisal().getId(),
                        "qc_result_id", result.getId(),
                        "decision", result.getQcDecision(),
                        "elapsed_ms", TimelineLog.elapsedMs(pairStarted)));
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
                log.error(TimelineLog.event("admin_batches", "java_qc_file_failed",
                        "batch_id", batchId,
                        "batch_file_id", pair.getAppraisal().getId(),
                        "appraisal", pair.getAppraisal().getFilename(),
                        "elapsed_ms", TimelineLog.elapsedMs(pairStarted),
                        "error", e.getMessage()));
                errorCount++;
                String fileError = pair.getAppraisal().getFilename() + ": " + e.getMessage();
                fileErrors.add(fileError);
                try {
                    self.markFileError(pair.getAppraisal().getId(), fileError);
                } catch (Exception saveEx) {
                    log.warn("Failed to persist file error for {}: {}", pair.getAppraisal().getFilename(), saveEx.getMessage());
                }
                updateProgress(batchId, "error", "Error processing " + pair.getAppraisal().getFilename(), index + 1, pairs.size(), true, safeModelConfig);
            }
        }

        // Partial re-run: the processed subset is not the whole batch, so the final status must
        // reflect EVERY file's active result (re-run + untouched), not just the subset counts.
        BatchStatus newStatus = partial
                ? recomputeBatchStatusFromActiveResults(batchId)
                : determineBatchStatus(autoPassCount, toVerifyCount, autoFailCount, errorCount);
        // R2: if a re-run carried a live reviewer lock onto a new result, the batch must stay
        // IN_REVIEW rather than fall back to the grabbable REVIEW_PENDING queue under the holder.
        if (newStatus == BatchStatus.REVIEW_PENDING && anyActiveReviewLock(batchId)) {
            newStatus = BatchStatus.IN_REVIEW;
        }
        String finalError = null;
        if (newStatus == BatchStatus.ERROR) {
            finalError = fileErrors.isEmpty()
                    ? "All appraisal files failed QC processing"
                    : "All appraisal files failed QC processing. First cause: " + fileErrors.get(0);
        }
        self.saveFinalBatchStatus(batchId, newStatus, finalError);
        businessEventService.record("BATCH_QC_COMPLETED", null, "java", newStatus.name(),
                "Batch", batchId, batchId, null, null, null,
                Map.of(
                        "auto_pass_count", autoPassCount,
                        "to_verify_count", toVerifyCount,
                        "auto_fail_count", autoFailCount,
                        "error_count", errorCount,
                        "total_files", pairs.size()
                ));

        log.info("QC batch {} complete in {} ms → {} | pass={} verify={} fail={} errors={}",
                batchId, TimelineLog.elapsedMs(batchStarted), newStatus,
                autoPassCount, toVerifyCount, autoFailCount, errorCount);
        updateProgress(batchId, "complete", "QC complete: " + newStatus.name().replace('_', ' '), pairs.size(), pairs.size(), false, safeModelConfig);

        // Push to the admin notification feed so the bell shows the result
        try {
            Map<String, Object> notif = new LinkedHashMap<>();
            notif.put("type",       "QC_COMPLETED");
            notif.put("batchId",    batchId);
            notif.put("parentBatchId", batch.getParentBatchId());
            notif.put("status",     newStatus.name());
            notif.put("totalFiles", pairs.size());
            notif.put("needsReview", toVerifyCount > 0 || autoFailCount > 0);
            notif.put("occurredAt", java.time.LocalDateTime.now().toString());
            notif.put("message",    "QC complete for \"" + batch.getParentBatchId() + "\" → " +
                    newStatus.name().replace('_', ' '));
            realtimeEventPublisher.publish("/topic/admin/notifications", notif);
        } catch (Exception e) {
            log.debug("Failed to publish QC completion notification for batch {}: {}", batchId, e.getMessage());
        }

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
        return cancellationRequests.contains(batchId)
                || Thread.currentThread().isInterrupted()
                // Cross-node: an admin may have pressed Stop on a different instance.
                || clusterCoordinator.isCancelSignalled(batchId);
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
                Instant.now().toString(),
                null,
                null,
                0.0,
                0L
        ));
        if (running || "saving".equals(stage) || "complete".equals(stage) || "error".equals(stage)) {
            try {
                self.touchBatchActivity(batchId);
            } catch (Exception e) {
                log.debug("Could not update QC heartbeat for batch {}: {}", batchId, e.getMessage());
            }
        }
        realtimeEventPublisher.publish("/topic/qc/batch/" + batchId + "/progress", progressPayload(batchId, progress));
    }

    /**
     * Merge a Python sub-stage update into the existing QCProgress for this
     * batch. Top-level stage / current / total are preserved; only the sub_*
     * fields and updated_at change. Skipped silently if no parent progress
     * exists yet (the worker has not entered the python stage).
     */
    private void updateSubProgress(Long batchId, String subStage, String subMessage, double subPercent, long subElapsedMs) {
        QCProgress merged = progressByBatch.computeIfPresent(batchId, (id, existing) -> new QCProgress(
                existing.stage(),
                existing.message(),
                existing.current(),
                existing.total(),
                existing.running(),
                existing.modelProvider(),
                existing.modelName(),
                existing.visionModel(),
                existing.startedAt(),
                Instant.now().toString(),
                subStage,
                subMessage,
                // Never let sub-progress go backward within the same file. updateProgress()
                // resets subPercent to 0.0 when a new file starts, which is the only valid
                // reset point. Any decrease here is a Python retry resetting its state.
                Math.max(existing.subPercent(), subPercent),
                subElapsedMs
        ));
        if (merged != null) {
            realtimeEventPublisher.publish("/topic/qc/batch/" + batchId + "/progress", progressPayload(batchId, merged));
        }
    }

    private Map<String, Object> progressPayload(Long batchId, QCProgress progress) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("batchId", batchId);
        payload.put("stage", progress.stage());
        payload.put("message", progress.message());
        payload.put("current", progress.current());
        payload.put("total", progress.total());
        payload.put("percent", progress.percent());
        payload.put("smoothedPercent", progress.smoothedPercent());
        payload.put("running", progress.running());
        payload.put("modelProvider", progress.modelProvider());
        payload.put("modelName", progress.modelName());
        payload.put("visionModel", progress.visionModel());
        payload.put("startedAt", progress.startedAt());
        payload.put("updatedAt", progress.updatedAt());
        payload.put("subStage", progress.subStage());
        payload.put("subMessage", progress.subMessage());
        payload.put("subPercent", progress.subPercent());
        payload.put("subElapsedMs", progress.subElapsedMs());
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
    @SuppressWarnings("null")
    public @NonNull QCResult processFilePair(FilePair pair) {
        return processFilePair(pair, QCModelConfig.defaults());
    }

    @SuppressWarnings("null")
    public @NonNull QCResult processFilePair(FilePair pair, QCModelConfig modelConfig) {
        // Keep the long Python/OCR call outside any Java DB transaction. Neon
        // terminates idle transactions during multi-minute OCR jobs, and that
        // rollback can mask the real Python result.
        BatchFile appraisal = batchFileRepository.findWithBatchAndReviewerById(pair.getAppraisal().getId())
                .orElseThrow(() -> new RuntimeException("BatchFile not found: " + pair.getAppraisal().getId()));

        log.debug("Processing pair: appraisal={}, engagement={}",
                appraisal.getFilename(),
                pair.hasEngagement() ? pair.getEngagement().getFilename() : "none");

        // Storage pre-check: confirm the source PDFs are actually readable on disk
        // BEFORE extraction starts. A disk/mount problem must surface as a clear
        // storage error, not a confusing downstream OCR/extraction failure.
        assertFileReadable(pair.getAppraisalPath(), "appraisal");
        assertFileReadable(pair.getEngagementPath(), "engagement");
        assertFileReadable(pair.getContractPath(), "contract");

        // On rerun: supersede the existing active result rather than skipping.
        // Historical results are retained for audit purposes.
        var existingActive = qcResultRepository.findActiveByBatchFileId(appraisal.getId());
        if (existingActive.isPresent()) {
            log.debug("Superseding existing QC result {} for rerun on file {}",
                    existingActive.get().getId(), appraisal.getFilename());
            // The previous active result stays in the DB with supersededAt set.
            // The new result will link back to it via rerunOf.
        }

        Long progressBatchId = appraisal.getBatch().getId();
        String clientId = (appraisal.getBatch().getClient() != null)
                ? String.valueOf(appraisal.getBatch().getClient().getId()) : null;
        Instant pythonStartedAt = Instant.now();
        long queueWaitMs = queueWaitMs(progressBatchId, pythonStartedAt);
        int retryCount = 0;

        // Order (AppraisalTransaction) traceability: threaded to Python via MDC — same
        // mechanism appendProcessingContext already uses for correlationId — so Python's
        // own audit tables can be cross-referenced back to the Java Order without adding
        // a new parameter to every processQC/submitQCJob overload.
        if (appraisal.getOrder() != null) {
            org.slf4j.MDC.put("orderRef", appraisal.getOrder().getTransactionRef());
        }

        PythonQCResponse pythonResponse;
        try {
        if (!pythonClient.isCeleryWorkerRunning()) {
            log.warn("Celery worker is not connected; using synchronous Python QC for batch {} file {}",
                    progressBatchId, appraisal.getFilename());
            updateSubProgress(progressBatchId, "python_sync",
                    "Celery worker unavailable — running OCR directly for " + appraisal.getFilename(), 0.05, 0);
            pythonResponse = runSyncPythonQc(pair, modelConfig, progressBatchId, appraisal, clientId);
            retryCount = pythonClient.getLastRetryCount();
            throwIfCancelled(progressBatchId);
        } else {
            // --- Async queue path (Celery worker) ---
            PythonClientService.JobSubmitResponse job;
            try {
                job = pythonClient.submitQCJob(
                        pair.getAppraisalPath(),
                        pair.getAppraisalXmlPath(),
                        pair.getEngagementPath(),
                        pair.getContractPath(),
                        modelConfig,
                        progressBatchId,
                        appraisal.getId(),
                        null,
                        appraisal.getContentHash(),
                        engagementStatusFor(pair),
                        clientId);

                updateSubProgress(progressBatchId, "queued",
                        "Job queued — waiting for Celery worker (" + appraisal.getFilename() + ")", 0.02, 0);

            } catch (CancellationException ce) {
                throw ce;
            } catch (Exception submitEx) {
                log.warn("Async submit unavailable for batch {} file {} ({}), falling back to sync call",
                        progressBatchId, appraisal.getFilename(), submitEx.getMessage());
                updateSubProgress(progressBatchId, "python_sync",
                        "Running OCR (sync fallback) for " + appraisal.getFilename(), 0.05, 0);
                pythonResponse = pythonClient.processQC(
                        pair.getAppraisalPath(),
                        pair.getAppraisalXmlPath(),
                        pair.getEngagementPath(),
                        pair.getContractPath(),
                        modelConfig,
                        snapshot -> {
                            String subStage   = snapshot.stage()   != null ? snapshot.stage()   : "python";
                            String subMessage = snapshot.message() != null ? snapshot.message()
                                    : "Processing " + appraisal.getFilename();
                            updateSubProgress(progressBatchId, subStage, subMessage,
                                    snapshot.subPercent(), snapshot.elapsedMs());
                        },
                        progressBatchId,
                        appraisal.getId(),
                        null,
                        appraisal.getContentHash(),
                        engagementStatusFor(pair),
                        clientId);
                retryCount = pythonClient.getLastRetryCount();
                throwIfCancelled(progressBatchId);

                QCResult syncFallbackResult = self.persistPythonResult(appraisal.getId(), pythonResponse, modelConfig, queueWaitMs, retryCount);
                self.recordQcEventsAsync(syncFallbackResult, pythonResponse, syncFallbackResult.getQcDecision(), modelConfig);
                return syncFallbackResult;
            }

            Duration timeout = Duration.ofSeconds(Math.max(900, (long) pythonClient.getConfig().getTimeoutSeconds() * 4));
            try {
                pythonResponse = pythonClient.waitForJobResult(
                        job.jobId(),
                        timeout,
                        () -> isCancellationRequested(progressBatchId),
                        snapshot -> {
                            String subStage   = snapshot.stage()   != null ? snapshot.stage()   : "python";
                            String subMessage = snapshot.message() != null ? snapshot.message()
                                    : "Processing " + appraisal.getFilename();
                            updateSubProgress(progressBatchId, subStage, subMessage,
                                    snapshot.subPercent(), snapshot.elapsedMs());
                        });
            } catch (PythonClientService.CeleryWorkerUnavailableException workerEx) {
                log.warn("Queued Python job {} was not picked up by Celery; taking it over synchronously",
                        workerEx.jobId());
                updateSubProgress(progressBatchId, "python_sync",
                        "Celery worker did not pick up queued job — running OCR directly for " + appraisal.getFilename(),
                        0.05, 0);
                pythonResponse = runSyncPythonQc(pair, modelConfig, progressBatchId, appraisal, clientId);
            }
            retryCount = pythonClient.getLastRetryCount();
            throwIfCancelled(progressBatchId);
        }

        QCResult result = self.persistPythonResult(appraisal.getId(), pythonResponse, modelConfig, queueWaitMs, retryCount);
        // Re-fetch so the switch below sees the decision after any match-confidence downgrade
        result = qcResultRepository.findById(result.getId()).orElse(result);

        // Fire QC rule events in the background — user sees REVIEW_PENDING immediately,
        // 137 event inserts happen after the batch status is already unlocked.
        self.recordQcEventsAsync(result, pythonResponse, result.getQcDecision(), modelConfig);
        return result;
        } finally {
            org.slf4j.MDC.remove("orderRef");
        }
    }

    /**
     * Per-document ingestion status forwarded to Python's G-0 gate so it can tell a
     * genuinely-absent engagement (NOT_PROVIDED → N/A) from one that exists but failed
     * or still awaits extraction (PENDING / EXTRACTION_FAILED → HOLD). Returns null
     * when the engagement is present/usable, letting Python extract it normally.
     */
    private static String engagementStatusFor(FilePair pair) {
        if (pair == null || !pair.hasEngagement() || pair.getEngagement() == null) {
            return "NOT_PROVIDED";
        }
        FileStatus s = pair.getEngagement().getStatus();
        if (s == FileStatus.ERROR) return "EXTRACTION_FAILED";
        if (s == FileStatus.PENDING) return "PENDING";
        return null; // COMPLETED → the path is passed and Python will extract it
    }

    private PythonQCResponse runSyncPythonQc(
            FilePair pair,
            QCModelConfig modelConfig,
            Long progressBatchId,
            BatchFile appraisal) {
        return runSyncPythonQc(pair, modelConfig, progressBatchId, appraisal, null);
    }

    private PythonQCResponse runSyncPythonQc(
            FilePair pair,
            QCModelConfig modelConfig,
            Long progressBatchId,
            BatchFile appraisal,
            String clientId) {
        return pythonClient.processQC(
                pair.getAppraisalPath(),
                pair.getAppraisalXmlPath(),
                pair.getEngagementPath(),
                pair.getContractPath(),
                modelConfig,
                snapshot -> {
                    String subStage   = snapshot.stage()   != null ? snapshot.stage()   : "python";
                    String subMessage = snapshot.message() != null ? snapshot.message()
                            : "Processing " + appraisal.getFilename();
                    updateSubProgress(progressBatchId, subStage, subMessage,
                            snapshot.subPercent(), snapshot.elapsedMs());
                },
                progressBatchId,
                appraisal.getId(),
                null,
                appraisal.getContentHash(),
                engagementStatusFor(pair),
                clientId);
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public @NonNull QCResult persistPythonResult(
            Long appraisalId,
            PythonQCResponse pythonResponse,
            QCModelConfig modelConfig,
            long queueWaitMs,
            int retryCount) {
        long persistStarted = System.nanoTime();
        BatchFile appraisal = batchFileRepository.findWithBatchAndReviewerById(appraisalId)
                .orElseThrow(() -> new RuntimeException("BatchFile not found: " + appraisalId));
        Long batchId = appraisal.getBatch() != null ? appraisal.getBatch().getId() : null;
        // Contract-drift guard (non-fatal): a Python build whose wire schema_version
        // differs from what this backend expects may have reshaped a nested payload.
        // We still persist (Jackson ignores unknown fields), but flag it loudly so a
        // mismatched deploy is caught in logs rather than as silent data corruption.
        String pySchema = pythonResponse.schemaVersion();
        if (pySchema != null && !EXPECTED_PYTHON_SCHEMA_VERSION.equals(pySchema)) {
            log.warn("Python QC response schema_version='{}' != expected '{}' (batch_file_id={}). "
                    + "Verify Java/Python are deployed together; nested payloads may have drifted.",
                    pySchema, EXPECTED_PYTHON_SCHEMA_VERSION, appraisal.getId());
        }
        log.debug(TimelineLog.event("admin_batches", "java_qc_result_save_start",
                "batch_id", batchId,
                "batch_file_id", appraisal.getId(),
                "appraisal", appraisal.getFilename(),
                "python_processing_ms", pythonResponse.processingTimeMs(),
                "total_rules", pythonResponse.totalRules()));

        // Re-fetch the active result after the Python call. On a rerun, the
        // pre-call active result will be superseded; on a race from a duplicate
        // worker, the result from the first worker will already be present.
        var activeAfterPython = qcResultRepository.findActiveByBatchFileId(appraisal.getId());
        boolean isRerun = activeAfterPython.isPresent();
        QCResult previousActive = activeAfterPython.orElse(null);

        // Determine decision
        QCDecision decision = determineDecision(pythonResponse);

        // On rerun: mark the previously-active result as superseded so it becomes
        // historical. The new result will reference it via rerunOf.
        if (isRerun && previousActive != null) {
            previousActive.setSupersededAt(Instant.now().atZone(java.time.ZoneId.systemDefault()).toLocalDateTime());
            qcResultRepository.save(previousActive);
            log.debug("QC result {} superseded for file {} (rerun)", previousActive.getId(), appraisal.getFilename());
        }

        // Create QCResult
        QCResult qcResult = QCResult.builder()
                .batchFile(appraisal)
                .qcDecision(decision)
                .pythonResponse(toJson(pythonResponse))
                .totalRules(pythonResponse.totalRules())
                .passedCount(pythonResponse.passed())
                .failedCount(pythonResponse.failed())
                .verifyCount(pythonResponse.verify())
                .errorCount(0)
                .processingTimeMs(pythonResponse.processingTimeMs())
                .extractionMethod(pythonResponse.extractionMethod())
                .ruleEngineVersion(pythonResponse.ruleEngineVersion())
                .pythonDocumentId(pythonResponse.documentId())
                .pythonProcessingJobId(pythonResponse.processingJobId())
                .cacheHit(pythonResponse.cacheHit())
                .missingDocuments(missingDocumentsJson(pythonResponse))
                .subjectAddress(subjectAddressFrom(pythonResponse))
                .sourceDocumentHash(appraisal.getContentHash())
                .sourceDocumentVersion(appraisal.getContentVersion())
                .build();

        // Link to superseded result so the full version chain is traceable.
        if (previousActive != null) {
            qcResult.setRerunOf(previousActive);
        }

        // Create rule results
        if (pythonResponse.ruleResults() != null) {
            for (PythonRuleResult pr : pythonResponse.ruleResults()) {
                String normalizedStatus = normalizePythonStatus(pr.status());
                boolean needsReview = pr.reviewRequired() || needsVerification(normalizedStatus);
                QCRuleResult ruleResult = QCRuleResult.builder()
                        .ruleId(textOr(pr.ruleId(), "UNKNOWN_RULE"))
                        .ruleName(textOr(pr.ruleName(), textOr(pr.ruleId(), "UNKNOWN_RULE")))
                        .section(pr.section())
                        .status(normalizedStatus)
                        .message(textOr(pr.message(), "No rule message provided."))
                        .severity(pr.severity() != null ? pr.severity() : "STANDARD")
                        .details(pr.details() != null ? toJson(pr.details()) : "{}")
                        .actionItem(textOr(pr.actionItem(), textOr(pr.verifyQuestion(), textOr(pr.rejectionText(), "No reviewer action required."))))
                        .needsVerification(needsReview)
                        .reviewRequired(needsReview)
                        .appraisalValue(textOr(pr.appraisalValue(), NO_APPRAISAL_VALUE))
                        .engagementValue(textOr(pr.engagementValue(), NO_ENGAGEMENT_VALUE))
                        .confidenceScore(confidenceFor(pr, normalizedStatus))
                        .extractedValue(pr.extractedValue() != null ? String.valueOf(pr.extractedValue()) : NO_EXTRACTED_VALUE)
                        .expectedValue(pr.expectedValue() != null ? String.valueOf(pr.expectedValue()) : NO_EXPECTED_VALUE)
                        .verifyQuestion(textOr(pr.verifyQuestion(), ""))
                        .rejectionText(textOr(pr.rejectionText(), ""))
                        .evidence(pr.evidence() != null ? toJson(pr.evidence()) : "[]")
                        // Slim finding contract — persisted at eval time so the reviewer
                        // list endpoint is a pure read (no recompute, no LLM on read).
                        .summary(textOr(pr.summary(), textOr(pr.ruleName(), pr.ruleId())))
                        .confidenceTier(textOr(pr.confidenceTier(), "medium"))
                        .highlightedValues(pr.highlightedValues() != null ? toJson(pr.highlightedValues()) : "[]")
                        .targetField(textOr(pr.targetField(), targetFieldFor(pr.ruleId())))
                        .pdfPage(pr.sourcePage() != null ? pr.sourcePage() : 0)
                        .bboxX(pr.bboxX() != null ? pr.bboxX() : 0.0f)
                        .bboxY(pr.bboxY() != null ? pr.bboxY() : 0.0f)
                        .bboxW(pr.bboxW() != null ? pr.bboxW() : 0.0f)
                        .bboxH(pr.bboxH() != null ? pr.bboxH() : 0.0f)
                        .scope(pr.scope())
                        .build();
                qcResult.addRuleResult(ruleResult);
            }
        }

        // Carry the reviewer's prior decisions across a rerun: where a finding
        // recurs with the same rule id, target field AND outcome, the reviewer's
        // Pass/Fail/override is preserved, so a rerun (often a single-field
        // extraction fix) does not silently discard their work. Findings that are
        // new, gone, or whose status changed are left pending and re-queued for
        // re-examination.
        User carriedLockHolder = null;
        if (isRerun && previousActive != null) {
            int carried = migrateReviewerDecisions(previousActive, qcResult);
            if (carried > 0) {
                log.debug("Carried {} reviewer decision(s) from result {} for file {}",
                        carried, previousActive.getId(), appraisal.getFilename());
            }
            carriedLockHolder = carryReviewLock(previousActive, qcResult);
            if (carriedLockHolder != null) {
                log.debug("Carried review lock (held by {}) from result {} for file {}",
                        carriedLockHolder.getUsername(), previousActive.getId(), appraisal.getFilename());
            }
        }

        // Save
        qcResult = Objects.requireNonNull(qcResultRepository.save(qcResult));
        appraisal.setStatus(FileStatus.COMPLETED);
        batchFileRepository.save(appraisal);
        log.debug("QC result saved: file={} decision={} pass={} fail={} verify={}",
                appraisal.getFilename(), decision,
                pythonResponse.passed(), pythonResponse.failed(), pythonResponse.verify());

        // Re-run conflict handling: a reviewer may have the now-superseded result
        // open. Their in-progress decisions on it are preserved (the old result is
        // kept, only stamped supersededAt), but they must be told the results they
        // are looking at have been replaced — push to the OLD result's topic (the
        // one their session is subscribed to) with the new id so the UI can offer
        // to load it. Best-effort: never block persistence (P-6).
        if (isRerun && previousActive != null) {
            try {
                realtimeEventPublisher.publish(
                        "/topic/reviewer/qc/" + previousActive.getId() + "/superseded",
                        Map.of(
                                "supersededResultId", previousActive.getId(),
                                "newResultId", qcResult.getId(),
                                "supersededAt", AppTime.now().toString(),
                                "message", "This report was re-processed by a new QC run. "
                                        + "Your decisions so far are preserved for audit; "
                                        + "load the new results to continue."
                        ));
            } catch (Exception pubEx) {
                log.warn("Failed to publish supersede event for result {}: {}",
                        previousActive.getId(), pubEx.getMessage());
            }
            // A1: durable audit record of the re-run so the audit graph/timeline is never blind
            // to it (the WS event above is transient). One event per superseded file.
            try {
                Map<String, Object> rerunPayload = new LinkedHashMap<>();
                rerunPayload.put("superseded_result_id", previousActive.getId());
                rerunPayload.put("new_result_id", qcResult.getId());
                rerunPayload.put("filename", appraisal.getFilename());
                rerunPayload.put("had_reviewer_decisions", previousActive.getFinalDecision() != null);
                rerunPayload.put("lock_carried_to", carriedLockHolder != null ? carriedLockHolder.getUsername() : null);
                businessEventService.record("QC_RESULT_SUPERSEDED", null, "java", "RERUN",
                        "QCResult", previousActive.getId(), batchId, appraisal.getId(),
                        qcResult.getId(), null, rerunPayload);
            } catch (Exception evEx) {
                log.warn("Failed to record QC_RESULT_SUPERSEDED audit event for result {}: {}",
                        previousActive.getId(), evEx.getMessage());
            }
        }
        log.debug(TimelineLog.event("admin_batches", "java_qc_result_saved",
                "batch_id", batchId,
                "batch_file_id", appraisal.getId(),
                "qc_result_id", qcResult.getId(),
                "decision", decision,
                "passed", pythonResponse.passed(),
                "failed", pythonResponse.failed(),
                "verify", pythonResponse.verify(),
                "total_rules", pythonResponse.totalRules(),
                "rule_rows", qcResult.getRuleResults() != null ? qcResult.getRuleResults().size() : 0,
                "elapsed_ms", TimelineLog.elapsedMs(persistStarted)));

        // Capture processing metrics for analytics
        saveMetrics(qcResult, pythonResponse, appraisal, modelConfig, queueWaitMs, retryCount);

        // Capture per-section / per-rule timing breakdown (docStats)
        saveDocStats(qcResult, pythonResponse, appraisal);

        // If the engagement letter OR contract was matched by filename heuristic or
        // positional guess (confidence < 0.82) and the rules all auto-passed, force
        // review. A confident rule-pass against the wrong document is not a pass.
        // The 0.82 threshold sits above every ambiguous/fallback confidence tier
        // (0.70 single-file, 0.72 multi-fuzzy, 0.78 substring, 0.80 multi-set/orderId)
        // and below the clean tiers (0.90 exact-key, 0.95 sole-in-set, 1.0 orderId).
        if (qcResult.getQcDecision() == QCDecision.AUTO_PASS) {
            final double MATCH_CONFIDENCE_THRESHOLD = 0.82;
            double worstMatchConf = 1.0;
            String worstDocType = null;
            Optional<Double> engConf = fileMatchingService.getEngagementMatchConfidence(appraisal.getId());
            if (engConf.isPresent() && engConf.get() < worstMatchConf) {
                worstMatchConf = engConf.get();
                worstDocType = "Engagement letter";
            }
            Optional<Double> conConf = fileMatchingService.getContractMatchConfidence(appraisal.getId());
            if (conConf.isPresent() && conConf.get() < worstMatchConf) {
                worstMatchConf = conConf.get();
                worstDocType = "Contract";
            }
            if (worstDocType != null && worstMatchConf < MATCH_CONFIDENCE_THRESHOLD) {
                final String docType = worstDocType;
                final double conf = worstMatchConf;
                downgradeToVerifyForLowMatchConfidence(qcResult.getId(), conf, docType);
                qcResult = qcResultRepository.findById(qcResult.getId()).orElse(qcResult);
                log.info("AUTO_PASS downgraded to TO_VERIFY for file {} — {} match confidence={} < {}",
                        appraisal.getFilename(), docType, conf, MATCH_CONFIDENCE_THRESHOLD);
            }
        }

        // Roll this per-file QC result up into its Order's computed lifecycle status.
        // Legacy files ingested before Order resolution existed have no order — skip.
        if (appraisal.getOrder() != null) {
            orderStatusService.recompute(appraisal.getOrder());
        }

        return qcResult;
    }

    /**
     * Persist the real, measured QC timing breakdown reported by Python into the
     * doc_stat tables (the admin docStats feature). The numbers are written
     * verbatim from the engine's perf_counter measurements — never derived or
     * synthesized here. Best-effort: a failure never blocks QC persistence (P-6).
     */
    private void saveDocStats(QCResult qcResult, PythonQCResponse r, BatchFile file) {
        var timings = r.timings();
        if (timings == null) {
            return; // older Python build without timing instrumentation
        }
        try {
            // remove any prior timing for this result (rerun) to avoid duplicates
            docStatRepository.findByQcResultId(qcResult.getId())
                    .ifPresent(docStatRepository::delete);

            var batch = file.getBatch();
            Long batchId = batch != null ? batch.getId() : null;
            Long clientId = (batch != null && batch.getClient() != null) ? batch.getClient().getId() : null;
            String clientName = (batch != null && batch.getClient() != null) ? batch.getClient().getName() : null;

            var slowStage   = (timings.stages()   != null && !timings.stages().isEmpty())   ? timings.stages().get(0)   : null;
            var slowSection = (timings.sections() != null && !timings.sections().isEmpty()) ? timings.sections().get(0) : null;
            var slowRule    = (timings.rules()    != null && !timings.rules().isEmpty())    ? timings.rules().get(0)    : null;
            var llm         = timings.llm();

            DocStat docStat = DocStat.builder()
                    .qcResult(qcResult)
                    .batchFileId(file.getId())
                    .batchId(batchId)
                    .clientId(clientId)
                    .filename(file.getFilename())
                    .clientName(clientName)
                    .qcDecision(qcResult.getQcDecision() != null ? qcResult.getQcDecision().name() : null)
                    .totalMs(timings.totalMs())
                    .ruleEngineMs(timings.ruleEngineMs())
                    .measuredPipelineMs(timings.measuredPipelineMs())
                    .ruleCount(timings.ruleCount())
                    // Store the slowest stage's stable KEY (not a display label); the UI
                    // derives the name from the key (frontend/lib/stageLabels.ts).
                    .slowestStageLabel(slowStage != null ? slowStage.stage() : null)
                    .slowestStageMs(slowStage != null ? slowStage.ms() : null)
                    .slowestSectionLabel(slowSection != null ? slowSection.label() : null)
                    .slowestSectionMs(slowSection != null ? slowSection.ms() : null)
                    .slowestRuleId(slowRule != null ? slowRule.ruleId() : null)
                    .slowestRuleName(slowRule != null ? slowRule.ruleName() : null)
                    .slowestRuleMs(slowRule != null ? slowRule.ms() : null)
                    .llmCalls(llm != null ? llm.totalCalls() : 0)
                    .llmInferenceMs(llm != null ? llm.totalInferenceMs() : 0.0)
                    .llmThrottleWaitMs(llm != null ? llm.totalThrottleWaitMs() : 0.0)
                    .rateLimitHits(llm != null ? llm.rateLimitHits() : 0)
                    .build();

            int i = 0;
            if (timings.stages() != null) {
                for (var s : timings.stages()) {
                    docStat.addStage(new DocStatStage(s.stage(), s.ms(), s.pctOfPipeline(),
                            s.llmCalls(), s.inferenceMs(), s.throttleWaitMs(), i++));
                }
            }
            i = 0;
            if (timings.sections() != null) {
                for (var s : timings.sections()) {
                    docStat.addSection(new DocStatSection(s.section(), s.label(), s.ms(),
                            s.ruleCount(), s.pctOfRules(), i++));
                }
            }
            i = 0;
            if (timings.rules() != null) {
                for (var rule : timings.rules()) {
                    docStat.addRule(new DocStatRule(rule.ruleId(), rule.ruleName(), rule.section(),
                            rule.status(), rule.ms(), rule.confidence(), rule.llmCalls(),
                            rule.llmMs(), rule.throttleMs(), i++));
                }
            }

            docStatRepository.save(docStat);
            log.debug("DocStats saved: file={} rules={} ruleEngineMs={} pipelineMs={}",
                    file.getFilename(), timings.ruleCount(), timings.ruleEngineMs(),
                    timings.measuredPipelineMs());
        } catch (Exception e) {
            log.warn("Failed to save docStats for file {}: {}", file.getFilename(), e.getMessage());
        }
    }

    /**
     * Build and persist all QC events for a single file result in one DB round trip.
     *
     * Runs @Async so the caller (processFilePair) is unblocked immediately after saving
     * the QCResult. The batch status transitions to REVIEW_PENDING before these events land.
     * Previously this fired 137 individual REQUIRES_NEW transactions (≈112s on remote Neon).
     */
    @Async("qcTaskExecutor")
    public void recordQcEventsAsync(QCResult qcResult, PythonQCResponse pythonResponse, QCDecision decision, QCModelConfig modelConfig) {
        try {
            BatchFile file = qcResult.getBatchFile();
            Batch batch = file != null ? file.getBatch() : null;
            Long batchId = batch != null ? batch.getId() : null;
            Long fileId = file != null ? file.getId() : null;

            Map<String, Object> payload = new LinkedHashMap<>();
            payload.put("decision", decision.name());
            payload.put("total_rules", pythonResponse.totalRules());
            payload.put("passed", pythonResponse.passed());
            payload.put("failed", pythonResponse.failed());
            payload.put("verify", pythonResponse.verify());
            payload.put("processing_time_ms", pythonResponse.processingTimeMs());
            payload.put("model_provider", pythonResponse.modelProvider() != null ? pythonResponse.modelProvider() : modelConfig.provider());
            payload.put("model_name", pythonResponse.modelName() != null ? pythonResponse.modelName() : modelConfig.textModel());
            payload.put("vision_model", pythonResponse.visionModel() != null ? pythonResponse.visionModel() : modelConfig.visionModel());
            payload.put("supporting_document_missing", Boolean.TRUE.equals(pythonResponse.supportingDocumentMissing()));
            payload.put("missing_supporting_documents", pythonResponse.missingSupportingDocuments());

            List<BusinessEvent> events = new ArrayList<>();

            // OCR event
            events.add(businessEventService.buildEvent(
                    Boolean.TRUE.equals(pythonResponse.cacheHit()) ? "FILE_OCR_CACHED" : "FILE_OCR_EXTRACTED",
                    null, "java",
                    Boolean.TRUE.equals(pythonResponse.cacheHit()) ? "CACHE_HIT" : "EXTRACTED",
                    "QCResult", qcResult.getId(), batchId, fileId, qcResult.getId(), null, payload));

            // QC completed event
            events.add(businessEventService.buildEvent(
                    "QC_COMPLETED", null, "java", decision.name(),
                    "QCResult", qcResult.getId(), batchId, fileId, qcResult.getId(), null, payload));

            // One event per rule result
            if (qcResult.getRuleResults() != null) {
                for (QCRuleResult ruleResult : qcResult.getRuleResults()) {
                    Map<String, Object> rulePayload = new LinkedHashMap<>();
                    rulePayload.put("rule_id", ruleResult.getRuleId());
                    rulePayload.put("rule_name", ruleResult.getRuleName());
                    rulePayload.put("status", ruleResult.getStatus());
                    rulePayload.put("severity", ruleResult.getSeverity());
                    rulePayload.put("review_required", Boolean.TRUE.equals(ruleResult.getReviewRequired()));
                    rulePayload.put("needs_verification", Boolean.TRUE.equals(ruleResult.getNeedsVerification()));
                    rulePayload.put("confidence_score", ruleResult.getConfidenceScore());
                    rulePayload.put("pdf_page", ruleResult.getPdfPage());
                    events.add(businessEventService.buildEvent(
                            "QC_RULE_EVALUATED", null, "java", ruleResult.getStatus(),
                            "QCRuleResult", ruleResult.getId(), batchId, fileId,
                            qcResult.getId(), ruleResult.getId(), rulePayload));
                }
            }

            // Save all events in a single transaction instead of one per event
            businessEventService.recordAll(events);
        } catch (Exception e) {
            log.error("Async QC event recording failed for qcResult={}: {}", qcResult.getId(), e.getMessage(), e);
        }
    }

    private String missingDocumentsJson(PythonQCResponse pythonResponse) {
        if (!Boolean.TRUE.equals(pythonResponse.supportingDocumentMissing())
                && (pythonResponse.missingSupportingDocuments() == null || pythonResponse.missingSupportingDocuments().isEmpty())) {
            return null;
        }
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("supporting_document_missing", Boolean.TRUE.equals(pythonResponse.supportingDocumentMissing()));
        payload.put("missing_supporting_documents", pythonResponse.missingSupportingDocuments());
        return toJson(payload);
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
        // A HOLD rule blocks the report regardless of the other counts — checked
        // first so the blocking contract holds for every client, not just the UI.
        if (Boolean.TRUE.equals(response.blocking()))                   return QCDecision.BLOCKED;
        if (response.verify()       != null && response.verify()       > 0) return QCDecision.TO_VERIFY;
        if (response.failed()       != null && response.failed()       > 0) return QCDecision.AUTO_FAIL;
        return QCDecision.AUTO_PASS;
    }

    // Known rule-status vocabulary the engine may emit. Used only to detect ENUM
    // DRIFT — an unrecognised value still degrades safely to a needs-review state,
    // but is logged so a new Python status isn't silently swallowed (DB-002).
    private static final Set<String> KNOWN_RULE_STATUSES = Set.of(
            "pass", "fail", "verify", "review", "hold",
            "extraction_failed", "ocr_low_confidence", "system_error",
            "source_missing", "cross_doc_mismatch", "skipped", "not_applicable");

    private String normalizePythonStatus(String status) {
        if (status == null || status.isBlank()) {
            return "verify";
        }
        String normalized = status.trim().toLowerCase();
        if (!KNOWN_RULE_STATUSES.contains(normalized)) {
            // Drift signal: a status the backend doesn't recognise. It is treated as
            // needs-review (safe default) but flagged so the vocabulary can be aligned.
            log.warn("Unknown Python rule status '{}' — treating as review. Align KNOWN_RULE_STATUSES "
                    + "if this is a deliberate new engine status.", normalized);
        }
        return normalized;
    }

    private boolean needsVerification(String normalizedStatus) {
        return "fail".equals(normalizedStatus)
                || "verify".equals(normalizedStatus)
                || "review".equals(normalizedStatus)
                || "extraction_failed".equals(normalizedStatus)
                || "ocr_low_confidence".equals(normalizedStatus)
                || "system_error".equals(normalizedStatus)
                || "source_missing".equals(normalizedStatus)
                || "cross_doc_mismatch".equals(normalizedStatus);
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

    /**
     * Recompute the batch status from EVERY active (non-superseded) result — used after a partial
     * re-run, where the processed subset is not representative of the whole batch. A batch is
     * COMPLETED only when no active result still needs reviewer work; any active non-AUTO_PASS
     * result without a final decision keeps it REVIEW_PENDING (so the untouched files' review work
     * is preserved). No active results at all → ERROR.
     */
    BatchStatus recomputeBatchStatusFromActiveResults(Long batchId) {
        List<QCResult> active = qcResultRepository.findByBatchId(batchId).stream()
                .filter(r -> r.getSupersededAt() == null)
                .toList();
        if (active.isEmpty()) {
            return BatchStatus.ERROR;
        }
        boolean anyPending = active.stream()
                .anyMatch(r -> r.getQcDecision() != QCDecision.AUTO_PASS && r.getFinalDecision() == null);
        if (anyPending) return BatchStatus.REVIEW_PENDING;
        // Do not mark COMPLETED while any appraisal file is still in ERROR — that file
        // produced no QCResult and has no finalDecision to check above. The reviewer
        // cannot act on it, but the admin can retry it (partial re-run) or dismiss it
        // (FileStatus.DISMISSED) to explicitly accept that the file cannot be processed.
        // DISMISSED files do not block completion — they are the terminal "accept failure" state.
        long unreviewedErrors = batchFileRepository.countByBatchIdAndStatus(batchId, FileStatus.ERROR);
        if (unreviewedErrors > 0) return BatchStatus.REVIEW_PENDING;
        return BatchStatus.COMPLETED;
    }

    /**
     * R2: when a re-run supersedes a result that a reviewer is actively holding, carry the lock
     * onto the new result so a <em>different</em> reviewer cannot grab it in the window before the
     * original reviewer reloads. The session token is intentionally NOT carried — the old session
     * lives on the old (now superseded) result; when the same reviewer re-opens the new result,
     * {@code beginReviewSession} mints a fresh token and the lockedBy == reviewer check lets them
     * straight back in. Returns the lock holder if a live lock was carried, else null.
     */
    private User carryReviewLock(QCResult previous, QCResult fresh) {
        if (previous == null) {
            return null;
        }
        User holder = previous.getReviewLockedBy();
        var expiry = previous.getReviewLockExpiresAt();
        boolean activeLock = holder != null && expiry != null && expiry.isAfter(AppTime.now());
        if (!activeLock) {
            return null;
        }
        fresh.setReviewLockedBy(holder);
        fresh.setReviewLockExpiresAt(expiry);
        fresh.setReviewStartedAt(previous.getReviewStartedAt());
        fresh.setReviewLastActiveAt(previous.getReviewLastActiveAt());
        return holder;
    }

    /**
     * True when any active (non-superseded) result in the batch is held by a live reviewer lock.
     * Used after a re-run to keep the batch IN_REVIEW (not back in the grabbable REVIEW_PENDING
     * queue) when a lock was carried onto a new result.
     */
    private boolean anyActiveReviewLock(Long batchId) {
        var now = AppTime.now();
        return qcResultRepository.findByBatchId(batchId).stream()
                .filter(r -> r.getSupersededAt() == null)
                .anyMatch(r -> r.getReviewLockedBy() != null
                        && r.getReviewLockExpiresAt() != null
                        && r.getReviewLockExpiresAt().isAfter(now));
    }

    private void saveMetrics(QCResult qcResult, PythonQCResponse r, BatchFile file, QCModelConfig modelConfig,
            long queueWaitMs, int retryCount) {
        try {
            int total  = Objects.requireNonNullElse(r.totalRules(), 0);
            int passed = Objects.requireNonNullElse(r.passed(), 0);
            double passRate = total > 0 ? (passed * 100.0 / total) : 0.0;

            // Derive OCR confidence from field_confidence map.
            // Python extraction produces confidence as a decimal fraction in [0.0, 1.0]
            // (e.g. 0.88 = 88%). The threshold below must match that scale.
            // BUG FIX: was "v < 70.0" which compared 0.88 against 70, classifying
            // every field as low-confidence and inflating fields_low_confidence to 100%.
            double avgConf = 0.0, minConf = 1.0;
            int lowConfCount = 0;
            if (r.fieldConfidence() != null && !r.fieldConfidence().isEmpty()) {
                var values = r.fieldConfidence().values().stream()
                    .filter(v -> v != null).mapToDouble(Double::doubleValue).toArray();
                if (values.length > 0) {
                    avgConf = java.util.Arrays.stream(values).average().orElse(0);
                    minConf = java.util.Arrays.stream(values).min().orElse(0);
                    // 0.70 = 70% confidence threshold (decimal scale, not percentage scale)
                    lowConfCount = (int) java.util.Arrays.stream(values).filter(v -> v < 0.70).count();
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
                .modelVersion(r.modelName() != null ? r.modelName() : modelConfig.textModel())
                .retryCount(retryCount)
                .queueWaitMs(queueWaitMs)
                .cacheHit(Boolean.TRUE.equals(r.cacheHit()))
                .fileSizeBytes(file.getFileSize())
                .build();

            metricsRepository.save(metrics);
        } catch (Exception e) {
            log.warn("Failed to save processing metrics for file {}: {}", file.getFilename(), e.getMessage());
        }
    }

    private long queueWaitMs(Long batchId, Instant pythonStartedAt) {
        Instant startedAt = batchQcStartedAt.get(batchId);
        if (startedAt == null || pythonStartedAt == null || pythonStartedAt.isBefore(startedAt)) {
            return 0L;
        }
        return Duration.between(startedAt, pythonStartedAt).toMillis();
    }

    private String toJson(Object obj) {
        if (obj == null)
            return "{}";
        try {
            return objectMapper.writeValueAsString(obj);
        } catch (JacksonException e) {
            log.warn("Failed to serialize to JSON: {}", e.getMessage());
            return "{}";
        }
    }

    private String textOr(String value, String fallback) {
        if (value == null || value.isBlank()) {
            return fallback != null ? fallback : NOT_PROVIDED;
        }
        return value;
    }

    /**
     * Carry reviewer decisions from a superseded result onto the new rerun result.
     * A decision is migrated only when a finding recurs with the same rule id +
     * target field AND the same status (outcome) — so a Pass/Fail/override still
     * applies to the same finding. New findings, removed findings, and findings
     * whose status changed are left pending (re-queued) for re-examination.
     *
     * @return how many decisions were carried forward.
     */
    private int migrateReviewerDecisions(QCResult previous, QCResult fresh) {
        Map<String, QCRuleResult> prevByKey = new java.util.HashMap<>();
        for (QCRuleResult prev : qcRuleResultRepository.findByQcResultId(previous.getId())) {
            prevByKey.put(decisionKey(prev), prev);
        }
        int carried = 0;
        for (QCRuleResult cur : fresh.getRuleResults()) {
            QCRuleResult prev = prevByKey.get(decisionKey(cur));
            if (prev == null) {
                continue; // new/unmatched finding → stays pending (re-queued)
            }
            boolean hadDecision = prev.getReviewerVerified() != null
                    || Boolean.TRUE.equals(prev.getOverridePending())
                    || prev.getOverrideApprovedBy() != null;
            if (!hadDecision) {
                continue;
            }
            // Outcome changed → the decision no longer applies; re-examine.
            if (!java.util.Objects.equals(normStatus(cur.getStatus()), normStatus(prev.getStatus()))) {
                continue;
            }
            cur.setReviewerVerified(prev.getReviewerVerified());
            cur.setReviewerComment(prev.getReviewerComment());
            cur.setVerifiedAt(prev.getVerifiedAt());
            cur.setDecisionLatencyMs(prev.getDecisionLatencyMs());
            cur.setAcknowledgedReferences(prev.getAcknowledgedReferences());
            cur.setOverridePending(prev.getOverridePending());
            cur.setOverrideRequestedBy(prev.getOverrideRequestedBy());
            cur.setOverrideRequestedAt(prev.getOverrideRequestedAt());
            cur.setOverrideApprovedBy(prev.getOverrideApprovedBy());
            cur.setOverrideApprovedAt(prev.getOverrideApprovedAt());
            carried++;
        }
        return carried;
    }

    private String decisionKey(QCRuleResult r) {
        return textOr(r.getRuleId(), "?") + "|" + textOr(r.getTargetField(), "");
    }

    /**
     * Compose the subject property's address from the document's extracted fields
     * (content, not filename) so the audit anchors identity on what the appraisal
     * is actually about. Returns null when the address could not be extracted.
     */
    private String subjectAddressFrom(PythonQCResponse response) {
        if (response == null || response.extractedFields() == null) {
            return null;
        }
        Map<String, Object> f = response.extractedFields();
        String street = fieldText(f.get("property_address"));
        if (street == null) {
            return null;
        }
        StringBuilder sb = new StringBuilder(street);
        String city  = fieldText(f.get("city"));
        String state = fieldText(f.get("state"));
        String zip   = fieldText(f.get("zip_code"));
        if (city != null)  sb.append(", ").append(city);
        if (state != null) sb.append(", ").append(state);
        if (zip != null)   sb.append(" ").append(zip);
        return sb.toString();
    }

    /** A non-blank, non-sentinel extracted field value, or null. */
    private static String fieldText(Object value) {
        if (value == null) return null;
        String s = String.valueOf(value).trim();
        if (s.isEmpty() || "null".equalsIgnoreCase(s) || s.matches("^__[A-Z0-9_]+__$")) return null;
        return s;
    }

    /**
     * Verify a source PDF path is a readable regular file before extraction. A
     * provided-but-unreadable path (disk unmounted, file deleted) fails fast with a
     * clear storage error rather than surfacing as a downstream extraction failure.
     * Null paths (genuinely absent optional documents) are left to the matcher.
     */
    private void assertFileReadable(java.nio.file.Path path, String role) {
        if (path == null) {
            return;
        }
        if (!java.nio.file.Files.isRegularFile(path) || !java.nio.file.Files.isReadable(path)) {
            throw new IllegalStateException(
                    "Storage unavailable: the " + role + " PDF could not be read at " + path
                    + " (disk or mount issue). QC was not started for this document.");
        }
    }

    private static String normStatus(String s) {
        return s == null ? "" : s.trim().toLowerCase();
    }

    private double confidenceFor(PythonRuleResult rule, String normalizedStatus) {
        double reported = rule.confidence() != null ? rule.confidence() : 0.0d;
        boolean hasAnyValue = hasRealValue(rule.appraisalValue())
                || hasRealValue(rule.engagementValue())
                || hasRealValue(rule.extractedValue())
                || hasRealValue(rule.expectedValue());

        if (!hasAnyValue && needsVerification(normalizedStatus)) {
            return 0.0d;
        }
        return reported;
    }

    private boolean hasRealValue(Object value) {
        if (value == null) {
            return false;
        }
        String text = String.valueOf(value).trim();
        if (text.isBlank()) {
            return false;
        }
        return !text.equals(NO_APPRAISAL_VALUE)
                && !text.equals(NO_ENGAGEMENT_VALUE)
                && !text.equals(NO_EXTRACTED_VALUE)
                && !text.equals(NO_EXPECTED_VALUE)
                && !text.equals(NOT_PROVIDED)
                && !text.equals("__NOT_FOUND__");
    }

    private String targetFieldFor(String ruleId) {
        String id = textOr(ruleId, "UNKNOWN_RULE").trim().toUpperCase();
        return switch (id) {
            case "S-1" -> "property_address";
            case "S-2" -> "borrower_name";
            case "S-3", "C-3" -> "owner_of_public_record";
            case "S-4" -> "legal_description";
            case "S-5" -> "neighborhood_name";
            case "S-6" -> "census_tract";
            case "S-7" -> "occupant_status";
            case "S-8" -> "special_assessments";
            case "S-9" -> "hoa_dues";
            case "S-10" -> "lender_name";
            case "S-11", "SCA-10" -> "property_rights";
            case "S-12" -> "offered_for_sale_12mo";
            case "C-1" -> "contract_analyzed";
            case "C-2" -> "contract_price";
            case "C-4" -> "financial_assistance";
            case "C-5" -> "personal_property";
            case "N-1", "N-6", "COM-1" -> "neighborhood_description";
            case "N-2", "N-7", "COM-2" -> "market_conditions_commentary";
            case "N-3" -> "one_unit_housing_price_age";
            case "N-4" -> "present_land_use_total";
            case "N-5" -> "neighborhood_boundaries";
            case "ST-1" -> "site_dimensions";
            case "ST-2" -> "site_area";
            case "ST-3" -> "site_shape";
            case "ST-4", "SCA-12" -> "view";
            case "ST-5" -> "zoning_classification";
            case "ST-6" -> "highest_best_use";
            case "ST-7", "I-5", "ST-9" -> "utilities";
            case "ST-8", "M-4" -> "flood_hazard";
            case "I-7", "SCA-17" -> "gla";
            case "I-9", "SCA-16", "PH-6" -> "condition_rating";
            case "SCA-1" -> "comparable_market_summary";
            case "SCA-2" -> "comparable_count";
            case "SCA-5" -> "comparable_data_sources";
            case "R-1" -> "value_reconciliation";
            case "R-2" -> "final_opinion_value";
            case "CA-1", "CA-2", "USDA-1" -> "cost_approach";
            case "IA-1", "MF-1" -> "rent_schedule";
            case "IA-2", "MF-2" -> "operating_income_statement";
            case "PH-1" -> "subject_photos";
            case "PH-2" -> "interior_photos";
            case "PH-5", "SCA-27" -> "comparable_photos";
            case "SK-1" -> "sketch_floor_plan";
            case "M-1" -> "location_map";
            case "M-2" -> "aerial_map";
            case "M-3" -> "plat_map";
            case "DOC-1" -> "appraiser_license";
            case "SIG-1" -> "signature_date";
            case "SIG-2" -> "appraiser_information";
            case "SIG-3" -> "supervisory_appraiser";
            case "SIG-4" -> "email_address";
            case "FHA-2" -> "fha_case_number";
            case "FHA-10" -> "remaining_economic_life";
            default -> id.toLowerCase().replace("-", "_") + "_evidence";
        };
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
            String updatedAt,
            String subStage,
            String subMessage,
            double subPercent,
            long subElapsedMs) {
        public int percent() {
            return total > 0 ? Math.min(100, Math.round((current * 100.0f) / total)) : 0;
        }

        // Smooth percent across the active file using Python-reported sub_percent
        // so the bar moves while a single file is being OCR/LLM/rule processed.
        public int smoothedPercent() {
            if (total <= 0) return 0;
            float perFile = 100.0f / total;
            float base = current * perFile;
            float within = (float) (Math.max(0.0, Math.min(1.0, subPercent)) * perFile);
            return Math.min(100, Math.round(base + within));
        }
    }
}
