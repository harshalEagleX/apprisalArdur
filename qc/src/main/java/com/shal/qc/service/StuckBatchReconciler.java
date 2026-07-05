package com.shal.qc.service;

import com.shal.common.entity.AppraisalTransaction;
import com.shal.common.entity.Batch;
import com.shal.common.entity.BatchStatus;
import com.shal.common.repository.AppraisalTransactionRepository;
import com.shal.common.repository.BatchRepository;
import com.shal.common.service.BusinessEventService;
import com.shal.common.service.OrderStatusService;
import com.shal.common.util.AppTime;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
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
    private final AppraisalTransactionRepository orderRepository;
    private final OrderStatusService orderStatusService;
    private final QCProcessingService qcProcessingService;
    private final PythonClientService pythonClientService;
    private final BusinessEventService businessEventService;

    @Value("${qc.reconciler.retry-after-minutes:15}")
    private int retryAfterMinutes;

    @Value("${qc.reconciler.abandon-after-minutes:90}")
    private int abandonAfterMinutes;

    @Value("${qc.reconciler.enabled:true}")
    private boolean enabled;

    public StuckBatchReconciler(BatchRepository batchRepository,
                                AppraisalTransactionRepository orderRepository,
                                OrderStatusService orderStatusService,
                                QCProcessingService qcProcessingService,
                                PythonClientService pythonClientService,
                                BusinessEventService businessEventService) {
        this.batchRepository = batchRepository;
        this.orderRepository = orderRepository;
        this.orderStatusService = orderStatusService;
        this.qcProcessingService = qcProcessingService;
        this.pythonClientService = pythonClientService;
        this.businessEventService = businessEventService;
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
            LocalDateTime now = AppTime.now();
            LocalDateTime retryCutoff  = now.minusMinutes(retryAfterMinutes);
            LocalDateTime abandonCutoff = now.minusMinutes(abandonAfterMinutes);

            // QC is order-grained (the Batch is upload-only), so we reconcile stuck ORDERS.
            // Batch review-lock expiry is still handled below — that is the reviewer flow, not QC.
            List<AppraisalTransaction> stuckOrders = orderRepository.findStuckInQcProcessing(retryCutoff);
            releaseExpiredReviewLocks(now);

            boolean pythonHealthy = pythonClientService.isHealthy();

            if (!stuckOrders.isEmpty()) {
                log.warn("Reconciler: found {} stuck order(s) in QC_PROCESSING", stuckOrders.size());
                for (AppraisalTransaction order : stuckOrders) {
                    reconcileOrder(order, abandonCutoff, pythonHealthy);
                }
            } else {
                log.debug("Reconciler: no stuck orders found");
            }
        } finally {
            MDC.remove("correlationId");
        }
    }

    private void reconcileOrder(AppraisalTransaction order, LocalDateTime abandonCutoff, boolean pythonHealthy) {
        Long orderId = order.getId();
        String ref = order.getTransactionRef();
        LocalDateTime stuckSince = order.getUpdatedAt();

        if (qcProcessingService.isOrderActive(orderId)) {
            log.info("Reconciler: order {} ({}) is still active on this JVM; skipping. Last activity: {}",
                    orderId, ref, stuckSince);
            return;
        }

        boolean shouldAbandon = stuckSince != null && stuckSince.isBefore(abandonCutoff);
        if (shouldAbandon) {
            log.error("Reconciler: abandoning order {} ({}) — stuck since {}", orderId, ref, stuckSince);
            orderStatusService.markError(order);
        } else if (!pythonHealthy) {
            log.warn("Reconciler: order {} ({}) is stuck but Python is unavailable — will retry next run", orderId, ref);
        } else {
            log.info("Reconciler: re-triggering QC for stuck order {} ({}), stuck since {}", orderId, ref, stuckSince);
            qcProcessingService.processOrderAsync(orderId, null);
        }
    }

    private void releaseExpiredReviewLocks(LocalDateTime now) {
        List<Batch> expiredReviewBatches = batchRepository.findExpiredInReviewBatches(now);
        for (Batch batch : expiredReviewBatches) {
            batch.setStatus(BatchStatus.REVIEW_PENDING);
            batchRepository.save(batch);
            businessEventService.batchEvent("REVIEW_LOCK_EXPIRED", batch.getAssignedReviewer(), batch, "RELEASED",
                    Map.of("expired_at", now.toString()));
            log.info("Reconciler: returned batch {} ({}) from IN_REVIEW to REVIEW_PENDING after expired review lock",
                    batch.getId(), batch.getParentBatchId());
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
        List<AppraisalTransaction> stuck = orderRepository.findStuckInQcProcessing(retryCutoff);

        boolean pythonHealthy = pythonClientService.isHealthy();
        int retried = 0, abandoned = 0;

        for (AppraisalTransaction o : stuck) {
            if (qcProcessingService.isOrderActive(o.getId())) {
                continue;
            }
            if (o.getUpdatedAt() != null && o.getUpdatedAt().isBefore(abandonCutoff)) {
                orderStatusService.markError(o);
                abandoned++;
            } else if (pythonHealthy) {
                qcProcessingService.processOrderAsync(o.getId(), null);
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
