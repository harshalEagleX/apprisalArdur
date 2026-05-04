package com.apprisal.qc.service;

import com.apprisal.common.entity.Batch;
import com.apprisal.common.entity.BatchStatus;
import com.apprisal.common.repository.BatchRepository;
import com.apprisal.common.util.AppTime;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;
import java.util.UUID;

/**
 * Reconciler for batches stranded in QC_PROCESSING after a JVM crash or timeout.
 *
 * Consistency model:
 *   Java is the system of record for QC outcomes and reviewer decisions.
 *   Python is operational data only (OCR cache, ML training signals).
 *   Python's file_hash cache makes re-triggering cheap — no re-OCR occurs for the same file.
 *
 * Two recovery strategies based on how long a batch has been stuck:
 *
 *   RETRY window  (stuck > retryAfterMinutes AND < abandonAfterMinutes)
 *     → Re-trigger async processing. Python returns cached results.
 *     → Works for: JVM killed mid-batch, OOM crash, deployment restart.
 *
 *   ABANDON window (stuck > abandonAfterMinutes)
 *     → Set status=ERROR with an explanatory message visible to the admin.
 *     → Admin can delete the batch and re-upload, or investigate logs.
 *     → Works for: persistent Python outage, disk full, corrupt PDF.
 */
@Component
public class StuckBatchReconciler {

    private static final Logger log = LoggerFactory.getLogger(StuckBatchReconciler.class);

    private final BatchRepository batchRepository;
    private final QCProcessingService qcProcessingService;
    private final PythonClientService pythonClientService;

    @Value("${qc.reconciler.retry-after-minutes:15}")
    private int retryAfterMinutes;

    @Value("${qc.reconciler.abandon-after-minutes:90}")
    private int abandonAfterMinutes;

    @Value("${qc.reconciler.enabled:true}")
    private boolean enabled;

    public StuckBatchReconciler(BatchRepository batchRepository,
                                QCProcessingService qcProcessingService,
                                PythonClientService pythonClientService) {
        this.batchRepository = batchRepository;
        this.qcProcessingService = qcProcessingService;
        this.pythonClientService = pythonClientService;
    }

    /**
     * Runs every 10 minutes. Finds batches stuck in QC_PROCESSING and either
     * re-triggers them (if Python is healthy) or marks them ERROR (if not).
     *
     * initialDelay: 5 minutes after startup — lets the app warm up before scanning.
     * fixedDelay:  10 minutes between each run (not fixedRate, so overlapping runs are impossible).
     */
    @Scheduled(initialDelay = 300_000, fixedDelay = 600_000)
    @Transactional
    public void reconcile() {
        if (!enabled) return;

        String correlationId = "reconcile-" + UUID.randomUUID().toString().substring(0, 8);
        MDC.put("correlationId", correlationId);

        try {
            // Find all batches stuck for longer than retryAfterMinutes
            LocalDateTime now = AppTime.now();
            LocalDateTime retryCutoff  = now.minusMinutes(retryAfterMinutes);
            LocalDateTime abandonCutoff = now.minusMinutes(abandonAfterMinutes);

            List<Batch> stuckBatches = batchRepository.findStuckInQcProcessing(retryCutoff);

            if (stuckBatches.isEmpty()) {
                log.debug("Reconciler: no stuck batches found");
                return;
            }

            log.warn("Reconciler: found {} stuck batch(es) in QC_PROCESSING", stuckBatches.size());

            boolean pythonHealthy = pythonClientService.isHealthy();

            for (Batch batch : stuckBatches) {
                reconcileBatch(batch, abandonCutoff, pythonHealthy);
            }
        } finally {
            MDC.remove("correlationId");
        }
    }

    private void reconcileBatch(Batch batch, LocalDateTime abandonCutoff, boolean pythonHealthy) {
        Long batchId = batch.getId();
        String batchRef = batch.getParentBatchId();
        LocalDateTime stuckSince = batch.getUpdatedAt();

        if (qcProcessingService.isBatchActive(batchId)) {
            log.info("Reconciler: batch {} ({}) is still active on this JVM; skipping stuck check. Last activity: {}",
                    batchId, batchRef, stuckSince);
            return;
        }

        boolean shouldAbandon = stuckSince != null && stuckSince.isBefore(abandonCutoff);

        if (shouldAbandon) {
            // Stuck too long — give up and let admin decide
            String msg = String.format(
                "Processing exceeded %d minute limit. Last activity: %s. Re-upload to retry.",
                abandonAfterMinutes, stuckSince
            );
            log.error("Reconciler: abandoning batch {} ({}): {}", batchId, batchRef, msg);
            batch.setStatus(BatchStatus.ERROR);
            batch.setErrorMessage(msg);
            batchRepository.save(batch);

        } else if (!pythonHealthy) {
            // Python is down — can't retry now, but don't abandon yet.
            // The batch stays QC_PROCESSING and will be retried next reconciliation run.
            log.warn("Reconciler: batch {} ({}) is stuck but Python service is unavailable — will retry next run",
                    batchId, batchRef);

        } else {
            // Python is healthy and batch hasn't been stuck too long — re-trigger
            log.info("Reconciler: re-triggering async QC for stuck batch {} ({}), stuck since {}",
                    batchId, batchRef, stuckSince);

            // Reset updatedAt so the next reconciler run doesn't immediately re-trigger again
            // (processBatchAsync sets status to QC_PROCESSING which updates updatedAt via @PreUpdate)
            qcProcessingService.processBatchAsync(batchId);
        }
    }

    /**
     * Manual trigger for testing or admin use.
     * Returns a summary of what was found and actioned.
     */
    @Transactional
    public ReconciliationReport runManually() {
        LocalDateTime now = AppTime.now();
        LocalDateTime retryCutoff   = now.minusMinutes(retryAfterMinutes);
        LocalDateTime abandonCutoff = now.minusMinutes(abandonAfterMinutes);
        List<Batch> stuck = batchRepository.findStuckInQcProcessing(retryCutoff);

        boolean pythonHealthy = pythonClientService.isHealthy();
        int retried = 0, abandoned = 0;

        for (Batch b : stuck) {
            if (qcProcessingService.isBatchActive(b.getId())) {
                continue;
            }
            if (b.getUpdatedAt() != null && b.getUpdatedAt().isBefore(abandonCutoff)) {
                b.setStatus(BatchStatus.ERROR);
                b.setErrorMessage("Manually reconciled: exceeded " + abandonAfterMinutes + " minute limit.");
                batchRepository.save(b);
                abandoned++;
            } else if (pythonHealthy) {
                qcProcessingService.processBatchAsync(b.getId());
                retried++;
            }
        }

        return new ReconciliationReport(stuck.size(), retried, abandoned, pythonHealthy);
    }

    public record ReconciliationReport(
        int stuckFound,
        int retried,
        int abandoned,
        boolean pythonWasHealthy
    ) {}
}
