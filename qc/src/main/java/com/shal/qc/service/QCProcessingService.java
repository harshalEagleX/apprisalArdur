package com.shal.qc.service;

import com.shal.common.dto.shalqc.ShalqcResponse;
import com.shal.common.dto.shalqc.ShalqcCard;
import com.shal.common.dto.shalqc.ShalqcInteraction;
import com.shal.common.mapper.ShalqcResponseMapper;
import com.shal.common.entity.*;
import com.shal.common.repository.LLMInteractionRepository;
import com.shal.common.repository.ClientRepository;
import com.shal.common.repository.BatchFileRepository;
import com.shal.common.repository.BatchRepository;
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
import org.springframework.transaction.support.TransactionSynchronizationManager;

import java.time.Duration;
import java.util.ArrayList;
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
    private final LLMInteractionRepository llmInteractionRepository;
    private final ClientRepository clientRepository;
    private final ShalqcResponseMapper shalqcMapper;
    private final BatchRepository batchRepository;
    private final BatchFileRepository batchFileRepository;
    private final ObjectMapper objectMapper;
    private final RealtimeEventPublisher realtimeEventPublisher;
    private final BusinessEventService businessEventService;
    private final com.shal.common.service.OrderStatusService orderStatusService;
    private final com.shal.common.repository.AppraisalTransactionRepository appraisalTransactionRepository;
    private final com.shal.common.repository.DocStatRepository docStatRepository;
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

    // ── Order-keyed QC coordination (the Order is the QC unit; Batch is upload/logistics) ──
    // Kept in separate maps from the batch-keyed state above: batch and order ids are both
    // Long counting from 1, so they must never share a raw-Long keyspace. Progress is
    // published to /topic/qc/order/{orderId}/progress and cluster cancel uses the "order:"
    // namespace so a batch cancel can't stop a same-numbered order.
    private final Map<Long, QCProgress> progressByOrder = new ConcurrentHashMap<>();
    private final Map<Long, Thread> runningThreadsByOrder = new ConcurrentHashMap<>();
    private final Map<Long, Instant> orderQcStartedAt = new ConcurrentHashMap<>();
    private final Set<Long> activeOrders = ConcurrentHashMap.newKeySet();
    private final Set<Long> orderCancellationRequests = ConcurrentHashMap.newKeySet();

    /**
     * Self-injection via @Lazy to break the circular proxy dependency.
     *
     * Spring's AOP proxies cannot intercept THIS.method() calls (self-calls).
     * By injecting ourselves through the container, calls such as
     * self.persistShalqcResult(...) go through the CGLIB proxy, so the short
     * save transaction is applied after the long Python call has finished.
     */
    @Autowired @Lazy
    private QCProcessingService self;

    public QCProcessingService(
            PythonClientService pythonClient,
            FileMatchingService fileMatchingService,
            QCResultRepository qcResultRepository,
            com.shal.common.repository.QCRuleResultRepository qcRuleResultRepository,
            LLMInteractionRepository llmInteractionRepository,
            ClientRepository clientRepository,
            BatchRepository batchRepository,
            BatchFileRepository batchFileRepository,
            ObjectMapper objectMapper,
            RealtimeEventPublisher realtimeEventPublisher,
            BusinessEventService businessEventService,
            com.shal.common.cluster.ClusterCoordinator clusterCoordinator,
            com.shal.common.service.OrderStatusService orderStatusService,
            com.shal.common.repository.AppraisalTransactionRepository appraisalTransactionRepository,
            com.shal.common.repository.DocStatRepository docStatRepository,
            com.shal.common.service.LinkageGateService linkageGateService) {
        this.pythonClient = pythonClient;
        this.fileMatchingService = fileMatchingService;
        this.qcResultRepository = qcResultRepository;
        this.qcRuleResultRepository = qcRuleResultRepository;
        this.llmInteractionRepository = llmInteractionRepository;
        this.clientRepository = clientRepository;
        this.shalqcMapper = new ShalqcResponseMapper(objectMapper);
        this.batchRepository = batchRepository;
        this.batchFileRepository = batchFileRepository;
        this.objectMapper = objectMapper;
        this.realtimeEventPublisher = realtimeEventPublisher;
        this.businessEventService = businessEventService;
        this.clusterCoordinator = clusterCoordinator;
        this.orderStatusService = orderStatusService;
        this.appraisalTransactionRepository = appraisalTransactionRepository;
        this.docStatRepository = docStatRepository;
        this.linkageGateService = linkageGateService;
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
    public void touchBatchActivity(@NonNull Long batchId) {
        batchRepository.touchQcProcessing(batchId, AppTime.now());
    }

    /** Order-grained heartbeat — keeps the Order's updatedAt fresh so the reconciler
     *  does not consider a long-running QC job stuck. Analogue of touchBatchActivity. */
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void touchOrderActivity(@NonNull Long orderId) {
        appraisalTransactionRepository.touchUpdatedAt(orderId, AppTime.now());
    }

    // ════════════════════════════════════════════════════════════════════════
    //  Order-keyed QC path — the Order is the QC coordination unit; the Batch
    //  stays upload/logistics only and its BatchStatus is NEVER flipped here.
    //  Reuses the shared, file-grained processFilePair; only the claim/cancel/
    //  status grain differs from the batch path.
    // ════════════════════════════════════════════════════════════════════════

    /**
     * Claim an Order for QC: takes the authoritative DB claim, then records the local
     * fast-path claim in {@code activeOrders}, then flips the Order's documentStatus to
     * QC_PROCESSING (never the Batch's status). Returns false if the order is already
     * being processed.
     *
     * <p><b>Claim order matters (2026-07-19 incident).</b> The DB row is taken FIRST and
     * {@code activeOrders} second. Previously the in-memory set was added to before the
     * DB call, so anything that made that call fail — or merely BLOCK — left this JVM
     * believing a worker held an order the database still reported as READY_FOR_QC. That
     * is exactly what happened: a claim blocked inside its transaction for four minutes,
     * and every retry in the meantime was refused with "another worker is active" while
     * the UI correctly showed the order as ready. The order was unrunnable until a JVM
     * restart, because nothing but a restart clears a leaked in-memory claim.
     *
     * <p>Taking the DB claim first loses nothing: {@code markProcessing} is an atomic
     * conditional UPDATE and is already the cross-node source of truth, so a genuinely
     * running order is rejected there (its row is QC_PROCESSING) without the set's help.
     * The {@code finally} then guarantees that any failure after the set is touched —
     * exception, rollback, cancel — releases the local claim instead of stranding it.
     */
    @Transactional
    public boolean claimOrderForProcessing(@NonNull Long orderId, QCModelConfig modelConfig) {
        QCModelConfig cfg = modelConfig != null ? modelConfig : QCModelConfig.defaults();
        var orderOpt = appraisalTransactionRepository.findById(orderId);
        if (orderOpt.isEmpty() || !orderStatusService.markProcessing(orderOpt.get())) {
            // Either the order is gone, or the row already says QC_PROCESSING — a real
            // worker holds it. Nothing was claimed here, so there is nothing to release.
            log.warn("QC claim rejected for order {} — the order row is already claimed or missing", orderId);
            return false;
        }
        boolean claimed = false;
        try {
            if (!activeOrders.add(orderId)) {
                // The DB said the order was free but this JVM thinks a worker holds it.
                // That means a previous claim leaked; the DB is authoritative, so take over.
                log.warn("QC claim for order {} found a stale in-memory claim (DB row was free) — taking over", orderId);
            }
            orderCancellationRequests.remove(orderId);
            orderQcStartedAt.put(orderId, Instant.now());
            updateProgress(JobScope.order(orderId), "queued", "QC job queued with " + cfg.label(), 0, 1, true, cfg);
            businessEventService.record("ORDER_QC_QUEUED", null, "java", "QUEUED",
                    "Order", orderId, null, null, null, null, Map.of("model", cfg.label()));
            log.info("Claimed order {} for QC using {}", orderId, cfg.label());
            claimed = true;
            return true;
        } finally {
            if (!claimed) {
                activeOrders.remove(orderId);
                orderQcStartedAt.remove(orderId);
                log.warn("QC claim for order {} failed after the row was claimed — released the local claim", orderId);
            }
        }
    }

    /**
     * Release a local (in-memory) QC claim without touching the order row.
     *
     * <p>Covers the one leak {@link #claimOrderForProcessing}'s own {@code finally} cannot:
     * a transaction that fails at COMMIT, after the method body has already returned true.
     * The caller sees an exception for a claim this JVM still holds, so the caller releases
     * it. Safe to call when nothing is held — it is a set removal.
     */
    public void releaseOrderClaim(@NonNull Long orderId) {
        if (activeOrders.remove(orderId)) {
            orderQcStartedAt.remove(orderId);
            log.warn("Released local QC claim for order {} after a failed start", orderId);
        }
    }

    public boolean isOrderActive(@NonNull Long orderId) {
        return activeOrders.contains(orderId) || runningThreadsByOrder.containsKey(orderId);
    }

    /** Fire-and-forget async QC for one Order. */
    @Async("qcTaskExecutor")
    public CompletableFuture<QCProcessingSummary> processOrderAsync(@NonNull Long orderId, QCModelConfig modelConfig) {
        long asyncStarted = System.nanoTime();
        QCModelConfig cfg = modelConfig != null ? modelConfig : QCModelConfig.defaults();
        Thread existing = runningThreadsByOrder.putIfAbsent(orderId, Thread.currentThread());
        if (existing != null) {
            log.warn("QC already running for order {} on thread {}", orderId, existing.getName());
            return CompletableFuture.failedFuture(new IllegalStateException("QC is already running for this order"));
        }
        try {
            QCProcessingSummary result = self.processOrder(orderId, cfg);
            log.info("QC worker complete for order {} in {} ms", orderId, TimelineLog.elapsedMs(asyncStarted));
            return CompletableFuture.completedFuture(result);
        } catch (CancellationException e) {
            log.warn("Async QC cancelled for order {}: {}", orderId, e.getMessage());
            // Last emit after the worker unwinds, so the progress bar clears to "stopped".
            updateProgress(JobScope.order(orderId), "stopped", "QC stopped by admin", 0, 1, false, cfg);
            return CompletableFuture.failedFuture(e);
        } catch (Exception e) {
            log.error("Async QC processing failed for order {}: {}", orderId, e.getMessage(), e);
            try {
                self.markOrderError(orderId);
            } catch (Exception saveEx) {
                log.error("Failed to persist error status for order {}: {}", orderId, saveEx.getMessage());
            }
            updateProgress(JobScope.order(orderId), "error", "QC failed: " + e.getMessage(), 0, 1, false, cfg);
            return CompletableFuture.failedFuture(e);
        } finally {
            runningThreadsByOrder.remove(orderId);
            activeOrders.remove(orderId);
            orderQcStartedAt.remove(orderId);
            orderCancellationRequests.remove(orderId);
            clusterCoordinator.clearCancel("order:" + orderId);
        }
    }

    /**
     * Process one Order end-to-end: resolve its file pairs, apply the linkage + completeness
     * gates, run each pair through the shared {@link #processFilePair}, then recompute the
     * Order's lifecycle status from its now-active QCResult(s). Never flips BatchStatus.
     */
    public @NonNull QCProcessingSummary processOrder(@NonNull Long orderId, QCModelConfig modelConfig) {
        long orderStarted = System.nanoTime();
        QCModelConfig cfg = modelConfig != null ? modelConfig : QCModelConfig.defaults();
        JobScope orderScope = JobScope.order(orderId);
        AppraisalTransaction order = appraisalTransactionRepository.findById(orderId)
                .orElseThrow(() -> new RuntimeException("Order not found: " + orderId));
        log.info("QC started for order {} ({}) using {}", orderId, order.getTransactionRef(), cfg.label());
        updateProgress(orderScope, "starting", "Starting QC for order " + order.getTransactionRef(), 0, 1, true, cfg);
        businessEventService.record("ORDER_QC_STARTED", null, "java", "STARTED",
                "Order", orderId, null, null, null, null, Map.of("model", cfg.label()));
        throwIfOrderCancelled(orderId);

        List<FilePair> pairs = fileMatchingService.getMatchedPairsForOrder(orderId);

        // Linkage gate (G-A): never QC an appraisal whose engagement/contract/xml is present
        // but unresolved (NEEDS_ASSIGNMENT) in its batch — that records a false NOT_PROVIDED.
        // Reuse the batch-scoped gate on each distinct batch the order's appraisals live in.
        Set<Long> heldOutIds = new java.util.HashSet<>();
        Set<Long> gateBatchIds = pairs.stream()
                .map(p -> p.getAppraisal().getBatch() != null ? p.getAppraisal().getBatch().getId() : null)
                .filter(Objects::nonNull).collect(java.util.stream.Collectors.toSet());
        for (Long bId : gateBatchIds) {
            batchRepository.findWithFilesById(bId).ifPresent(b ->
                    linkageGateService.computeHoldOuts(b).forEach(h -> heldOutIds.add(h.appraisalFileId())));
        }
        if (!heldOutIds.isEmpty()) {
            pairs = pairs.stream().filter(p -> !heldOutIds.contains(p.getAppraisal().getId())).toList();
        }

        // Completeness gate (defense in depth; the QC endpoint already blocks incomplete orders).
        pairs = pairs.stream().filter(p -> {
            java.util.Set<FileType> present = new java.util.HashSet<>();
            if (p.getAppraisal() != null) present.add(FileType.APPRAISAL);
            if (p.hasAppraisalXml()) present.add(FileType.APPRAISAL_XML);
            if (p.hasEngagement()) present.add(FileType.ENGAGEMENT);
            return com.shal.common.service.OrderCompleteness.missingLabels(present).isEmpty();
        }).toList();

        if (pairs.isEmpty()) {
            // Nothing runnable — held out pending assignment, or genuinely incomplete.
            orderStatusService.recompute(order); // reflect the real (UNMATCHED/INCOMPLETE) state
            updateProgress(orderScope, "complete", "No runnable documents for this order", 0, 1, false, cfg);
            log.info("Order {} — no runnable pairs (held out or incomplete)", orderId);
            return new QCProcessingSummary(0, 0, 0, 0, 0, null);
        }

        int autoPass = 0, toVerify = 0, autoFail = 0, errors = 0;
        List<String> fileErrors = new ArrayList<>();
        for (int index = 0; index < pairs.size(); index++) {
            FilePair pair = pairs.get(index);
            throwIfOrderCancelled(orderId);
            if (!pythonClient.isHealthy()) {
                log.error("Python OCR service is down — aborting order {}", orderId);
                self.markOrderError(orderId);
                updateProgress(orderScope, "error", "Python OCR service unavailable", index, pairs.size(), false, cfg);
                throw new RuntimeException("Python OCR service unavailable");
            }
            try {
                updateProgress(orderScope, "python", "Processing " + pair.getAppraisal().getFilename(), index, pairs.size(), true, cfg);
                QCResult result = self.processFilePair(pair, cfg, orderScope);
                throwIfOrderCancelled(orderId);
                try {
                    self.markSupportingFilesProcessed(pair);
                } catch (Exception suppEx) {
                    log.warn("Failed to update supporting-file status for {}: {}",
                            pair.getAppraisal().getFilename(), suppEx.getMessage());
                }
                switch (result.getQcDecision()) {
                    case AUTO_PASS -> autoPass++;
                    case TO_VERIFY -> toVerify++;
                    case AUTO_FAIL -> autoFail++;
                    case BLOCKED   -> toVerify++;
                }
                updateProgress(orderScope, "saving", "Saved QC result for " + pair.getAppraisal().getFilename(), index + 1, pairs.size(), true, cfg);
            } catch (CancellationException e) {
                throw e;
            } catch (Exception e) {
                if (isOrderCancellationRequested(orderId)) {
                    throw new CancellationException("QC stopped by admin");
                }
                log.error("Error processing pair for order {}: appraisal={}, error={}",
                        orderId, pair.getAppraisal().getFilename(), e.getMessage(), e);
                errors++;
                String fileError = pair.getAppraisal().getFilename() + ": " + e.getMessage();
                fileErrors.add(fileError);
                try {
                    self.markFileError(pair.getAppraisal().getId(), fileError);
                } catch (Exception ignore) {
                    log.warn("Failed to persist file error for {}: {}", pair.getAppraisal().getFilename(), ignore.getMessage());
                }
            }
        }

        // Terminal Order status is computed from the now-active QCResult(s).
        orderStatusService.recompute(order);
        AppraisalTransaction fresh = appraisalTransactionRepository.findById(orderId).orElse(order);
        updateProgress(orderScope, "complete",
                "QC complete: " + String.valueOf(fresh.getDocumentStatus()).replace('_', ' '),
                pairs.size(), pairs.size(), false, cfg);
        log.info("QC order {} complete in {} ms → {} | pass={} verify={} fail={} errors={}",
                orderId, TimelineLog.elapsedMs(orderStarted), fresh.getDocumentStatus(),
                autoPass, toVerify, autoFail, errors);
        businessEventService.record("ORDER_QC_COMPLETED", null, "java", String.valueOf(fresh.getDocumentStatus()),
                "Order", orderId, null, null, null, null,
                Map.of("auto_pass_count", autoPass, "to_verify_count", toVerify,
                        "auto_fail_count", autoFail, "error_count", errors, "total_files", pairs.size()));

        // Admin notification feed
        try {
            Map<String, Object> notif = new LinkedHashMap<>();
            notif.put("type", "ORDER_QC_COMPLETED");
            notif.put("orderId", orderId);
            notif.put("transactionRef", fresh.getTransactionRef());
            notif.put("status", String.valueOf(fresh.getDocumentStatus()));
            notif.put("totalFiles", pairs.size());
            notif.put("needsReview", toVerify > 0 || autoFail > 0);
            notif.put("occurredAt", AppTime.now().toString());
            notif.put("message", "QC complete for order \"" + fresh.getTransactionRef() + "\" → " + fresh.getDocumentStatus());
            realtimeEventPublisher.publish("/topic/admin/notifications", notif);
        } catch (Exception e) {
            log.debug("Failed to publish order QC completion notification for order {}: {}", orderId, e.getMessage());
        }

        return new QCProcessingSummary(pairs.size(), autoPass, toVerify, autoFail, errors, null);
    }

    /** Best-effort stop for a running Order QC job. Order analogue of {@link #cancelBatch}. */
    @Transactional
    public boolean cancelOrder(@NonNull Long orderId) {
        orderCancellationRequests.add(orderId);
        clusterCoordinator.signalCancel("order:" + orderId);
        Thread worker = runningThreadsByOrder.get(orderId);
        if (worker != null) {
            worker.interrupt();
        }
        activeOrders.remove(orderId);
        appraisalTransactionRepository.findById(orderId).ifPresent(o -> {
            if (o.getDocumentStatus() == OrderDocumentStatus.QC_PROCESSING) {
                orderStatusService.recompute(o); // fall back to the real pre-run state
            }
        });
        log.warn("QC stop requested for order {}{}", orderId, worker != null ? " and worker interrupted" : "");
        return worker != null;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void markOrderError(@NonNull Long orderId) {
        appraisalTransactionRepository.findById(orderId).ifPresent(orderStatusService::markError);
    }

    public QCProgress getOrderProgress(@NonNull Long orderId) {
        return progressByOrder.get(orderId);
    }

    private boolean isOrderCancellationRequested(Long orderId) {
        return orderCancellationRequests.contains(orderId)
                || Thread.currentThread().isInterrupted()
                || clusterCoordinator.isCancelSignalled("order:" + orderId);
    }

    private void throwIfOrderCancelled(Long orderId) {
        if (isOrderCancellationRequested(orderId)) {
            throw new CancellationException("QC stopped by admin");
        }
    }

    // ── Progress / cancel coordination, generalized over the job grain ──────────
    // A QC run is coordinated at ONE grain: the Batch (legacy) or the Order (target).
    // Both ids are Long, so JobScope carries which grain — it selects the right progress
    // map + cancel set, publishes to the matching /topic, and namespaces the cluster
    // cancel key. The batch-id overloads below keep every existing batch call site
    // (processBatch, processFilePair) working unchanged.
    private enum JobKind { BATCH, ORDER }
    private record JobScope(JobKind kind, Long id) {
        static JobScope batch(Long id) { return new JobScope(JobKind.BATCH, id); }
        static JobScope order(Long id) { return new JobScope(JobKind.ORDER, id); }
        String topic()     { return "/topic/qc/" + (kind == JobKind.ORDER ? "order" : "batch") + "/" + id + "/progress"; }
        String cancelKey() { return (kind == JobKind.ORDER ? "order:" : "batch:") + id; }
        String idKey()     { return kind == JobKind.ORDER ? "orderId" : "batchId"; }
    }
    private Map<Long, QCProgress> progressMapFor(JobScope s) { return s.kind() == JobKind.ORDER ? progressByOrder : progressByBatch; }
    private Set<Long> cancelSetFor(JobScope s) { return s.kind() == JobKind.ORDER ? orderCancellationRequests : cancellationRequests; }
    private Map<Long, Instant> startedAtMapFor(JobScope s) { return s.kind() == JobKind.ORDER ? orderQcStartedAt : batchQcStartedAt; }

    private void throwIfCancelled(JobScope scope) {
        if (isCancellationRequested(scope)) {
            throw new CancellationException("QC stopped by admin");
        }
    }
    private void throwIfCancelled(Long batchId) { throwIfCancelled(JobScope.batch(batchId)); }

    private boolean isCancellationRequested(JobScope scope) {
        return cancelSetFor(scope).contains(scope.id())
                || Thread.currentThread().isInterrupted()
                // Cross-node: an admin may have pressed Stop on a different instance.
                || clusterCoordinator.isCancelSignalled(scope.cancelKey());
    }
    private boolean isCancellationRequested(Long batchId) { return isCancellationRequested(JobScope.batch(batchId)); }

    private void updateProgress(Long batchId, String stage, String message, int current, int total, boolean running) {
        updateProgress(JobScope.batch(batchId), stage, message, current, total, running, QCModelConfig.defaults());
    }
    private void updateProgress(Long batchId, String stage, String message, int current, int total, boolean running, QCModelConfig modelConfig) {
        updateProgress(JobScope.batch(batchId), stage, message, current, total, running, modelConfig);
    }

    private void updateProgress(JobScope scope, String stage, String message, int current, int total, boolean running, QCModelConfig modelConfig) {
        int safeTotal = Math.max(total, 1);
        int safeCurrent = Math.max(0, Math.min(current, safeTotal));
        QCModelConfig safeModelConfig = modelConfig != null ? modelConfig : QCModelConfig.defaults();
        QCProgress progress = progressMapFor(scope).compute(scope.id(), (id, existing) -> new QCProgress(
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
                touchActivity(scope);
            } catch (Exception e) {
                log.debug("Could not update QC heartbeat for {} {}: {}", scope.kind(), scope.id(), e.getMessage());
            }
        }
        realtimeEventPublisher.publish(scope.topic(), progressPayload(scope, progress));
    }

    /**
     * Merge a Python sub-stage update into the existing QCProgress for this job.
     * Top-level stage / current / total are preserved; only the sub_* fields and
     * updated_at change. Skipped silently if no parent progress exists yet (the
     * worker has not entered the python stage).
     */
    private void updateSubProgress(Long batchId, String subStage, String subMessage, double subPercent, long subElapsedMs) {
        updateSubProgress(JobScope.batch(batchId), subStage, subMessage, subPercent, subElapsedMs);
    }
    private void updateSubProgress(JobScope scope, String subStage, String subMessage, double subPercent, long subElapsedMs) {
        QCProgress merged = progressMapFor(scope).computeIfPresent(scope.id(), (id, existing) -> new QCProgress(
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
            realtimeEventPublisher.publish(scope.topic(), progressPayload(scope, merged));
        }
    }

    /**
     * Heartbeat the job's row so the stuck-job reconciler sees it as alive.
     *
     * <p><b>Never heartbeat from inside a transaction (2026-07-19 deadlock).</b> Both
     * touch methods are REQUIRES_NEW, so they run on a SECOND connection. If the calling
     * thread is already in a transaction that has written the same row — which is exactly
     * what {@code claimOrderForProcessing} does, via {@code markProcessing}'s conditional
     * UPDATE — the heartbeat's {@code UPDATE … SET updated_at} blocks on the row lock the
     * caller's own uncommitted transaction holds. The thread then waits for itself, with
     * no lock timeout, forever: the request hangs (the UI gave up at 90s), the order row
     * stays locked, and every retry piles up behind it. Postgres showed it plainly — one
     * session "idle in transaction" holding the row, its sibling "active / Lock" waiting
     * on it, and three more clicks queued behind that.
     *
     * <p>Skipping is not a compromise, it is the correct behavior: if a transaction is
     * open on this thread it is going to commit its own {@code updated_at} anyway, so the
     * heartbeat would add nothing but a second writer for the same row. The long-running
     * worker path ({@code processOrder}) is deliberately NOT transactional, so its
     * heartbeats — the ones the reconciler actually depends on — still fire.
     */
    private void touchActivity(JobScope scope) {
        if (TransactionSynchronizationManager.isActualTransactionActive()) {
            log.debug("Skipping QC heartbeat for {} {} — a transaction is already open on this thread",
                    scope.kind(), scope.id());
            return;
        }
        if (scope.kind() == JobKind.ORDER) self.touchOrderActivity(scope.id());
        else self.touchBatchActivity(scope.id());
    }

    private Map<String, Object> progressPayload(JobScope scope, QCProgress progress) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put(scope.idKey(), scope.id());
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
        return processFilePair(pair, modelConfig, null);
    }

    /**
     * {@code scope} decides where live progress publishes and which cancel flag is checked —
     * the Batch (legacy) or the Order (target). When null it defaults to the file's Batch, so
     * the batch path behaves exactly as before. {@code progressBatchId} (the file's real batch)
     * is still what's sent to Python and stamped on business events regardless of scope — only
     * the progress/cancel grain changes.
     */
    @SuppressWarnings("null")
    public @NonNull QCResult processFilePair(FilePair pair, QCModelConfig modelConfig, JobScope scopeOrNull) {
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
        // Progress/cancel grain: the Order when this run was order-triggered, else the Batch.
        JobScope scope = scopeOrNull != null ? scopeOrNull : JobScope.batch(progressBatchId);
        String clientId = (appraisal.getBatch().getClient() != null)
                ? String.valueOf(appraisal.getBatch().getClient().getId()) : null;
        Instant pythonStartedAt = Instant.now();
        long queueWaitMs = queueWaitMs(scope, pythonStartedAt);
        int retryCount = 0;

        // Order (AppraisalTransaction) traceability: threaded to Python via MDC — same
        // mechanism appendProcessingContext already uses for correlationId — so Python's
        // own audit tables can be cross-referenced back to the Java Order without adding
        // a new parameter to every processQCShalqc overload.
        if (appraisal.getOrder() != null) {
            org.slf4j.MDC.put("orderRef", appraisal.getOrder().getTransactionRef());
        }

        // SHALqc (Approach B, sync-first): the retired ocr-service async/rule-engine
        // flow is replaced by SHALqc's synchronous /qc/process, which returns the
        // native OrderQCResponse (cards + coordinates + llm_interactions), mapped and
        // persisted via ShalqcResponseMapper. The Celery async path below is bypassed.
        {  // SHALqc synchronous /qc/process is the ONLY QC path — the legacy Celery
           // async + ocr-service rule-engine flow was removed 2026-07-15.
            updateSubProgress(scope, "python_sync",
                    "Running SHALqc QC for " + appraisal.getFilename(), 0.05, 0);
            // The client's AMC code selects shalqc's compiled bundle; without it
            // shalqc falls back to the generic _base catalog. Resolve it via the
            // repository (by id) rather than appraisal.getBatch().getClient().getCode(),
            // which lazy-inits the Client proxy outside a Hibernate session and throws.
            String amcCode = null;
            if (clientId != null) {
                try {
                    amcCode = clientRepository.findById(Long.valueOf(clientId))
                            .map(com.shal.common.entity.Client::getCode).orElse(null);
                } catch (Exception ex) {
                    log.warn("Could not resolve AMC code for clientId {}: {}", clientId, ex.getMessage());
                }
            }
            try {
                ShalqcResponse shalqcResponse = pythonClient.processQCShalqc(
                        pair.getAppraisalPath(),
                        pair.getAppraisalXmlPath(),
                        pair.getEngagementPath(),
                        pair.getContractPath(),
                        modelConfig,
                        snapshot -> updateSubProgress(scope,
                                snapshot.stage() != null ? snapshot.stage() : "python",
                                snapshot.message() != null ? snapshot.message() : "Processing " + appraisal.getFilename(),
                                snapshot.subPercent(), snapshot.elapsedMs()),
                        progressBatchId, appraisal.getId(), null,
                        appraisal.getContentHash(), engagementStatusFor(pair), clientId, amcCode);
                retryCount = pythonClient.getLastRetryCount();
                throwIfCancelled(scope);
                return self.persistShalqcResult(appraisal.getId(), shalqcResponse, modelConfig, queueWaitMs, retryCount);
            } finally {
                org.slf4j.MDC.remove("orderRef");
            }
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

    /**
     * Persist a SHALqc native {@link ShalqcResponse} (Approach B) — the ONLY QC
     * persistence path. Sources every field from {@link ShalqcResponseMapper}:
     * cards → QCRuleResult (with bbox coordinates for the reviewer auto-scroll),
     * informational cards → off-queue QCRuleResult rows, llm_interactions →
     * LLMInteraction (keyed by the persisted qcResultId for the drill-in endpoint),
     * summary counts → decision. Re-run supersede, reviewer-decision carry and
     * review-lock carry are preserved.
     */
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public @NonNull QCResult persistShalqcResult(
            Long appraisalId,
            ShalqcResponse response,
            QCModelConfig modelConfig,
            long queueWaitMs,
            int retryCount) {
        BatchFile appraisal = batchFileRepository.findWithBatchAndReviewerById(appraisalId)
                .orElseThrow(() -> new RuntimeException("BatchFile not found: " + appraisalId));
        Long batchId = appraisal.getBatch() != null ? appraisal.getBatch().getId() : null;

        Map<String, Object> summary = response.summary() != null ? response.summary() : Map.of();
        List<ShalqcCard> cards = response.cards() != null ? response.cards() : List.of();

        var activeAfter = qcResultRepository.findActiveByBatchFileId(appraisal.getId());
        boolean isRerun = activeAfter.isPresent();
        QCResult previousActive = activeAfter.orElse(null);

        QCDecision decision = shalqcMapper.decisionFrom(response.status(), summary);

        if (isRerun && previousActive != null) {
            previousActive.setSupersededAt(Instant.now().atZone(java.time.ZoneId.systemDefault()).toLocalDateTime());
            qcResultRepository.save(previousActive);
        }

        String ruleEngineVersion = "shalqc-language";
        if (response.versions() != null) {
            Object jp = response.versions().getOrDefault("judge_prompt",
                    response.versions().getOrDefault("binder_prompt", "shalqc-language"));
            ruleEngineVersion = String.valueOf(jp);
        }

        QCResult qcResult = QCResult.builder()
                .batchFile(appraisal)
                .qcDecision(decision)
                .pythonResponse(toJson(response))
                .totalRules(cards.size())
                .passedCount(shalqcMapper.passed(summary))
                .failedCount(shalqcMapper.failed(summary))
                .verifyCount(shalqcMapper.verify(summary))
                .errorCount(0)
                .extractionMethod("shalqc-language")
                .ruleEngineVersion(ruleEngineVersion)
                .pythonDocumentId(response.orderId())
                .cacheHit(Boolean.TRUE.equals(response.cachedRun()))
                .sourceDocumentHash(appraisal.getContentHash())
                .sourceDocumentVersion(appraisal.getContentVersion())
                .build();

        if (previousActive != null) {
            qcResult.setRerunOf(previousActive);
        }

        // A G-0-blocked order comes back with no cards; surface WHY it was held so the
        // reviewer sees the reason rather than an empty result. (decisionFrom already
        // mapped status=BLOCKED → QCDecision.BLOCKED, keeping it off the auto-pass path.)
        if (decision == QCDecision.BLOCKED && response.holdReasons() != null && !response.holdReasons().isEmpty()) {
            qcResult.setReviewerNotes("QC on hold: " + String.join("; ", response.holdReasons()));
        }

        for (ShalqcCard c : cards) {
            qcResult.addRuleResult(shalqcMapper.toRuleResult(c));
        }
        // Informational items (no reject authority) are persisted too — flagged
        // card_group="informational" with the review flags off — so the reviewer UI
        // can show them in a collapsed tab without them ever entering the queue.
        List<ShalqcCard> informational = response.informationalCards() != null
                ? response.informationalCards() : List.of();
        for (ShalqcCard c : informational) {
            qcResult.addRuleResult(shalqcMapper.toRuleResult(c));
        }

        if (isRerun && previousActive != null) {
            migrateReviewerDecisions(previousActive, qcResult);
            carryReviewLock(previousActive, qcResult);
        }

        qcResult = Objects.requireNonNull(qcResultRepository.save(qcResult));

        // Stored LLM exchanges are keyed by the now-persisted qcResultId so the
        // reviewer drill-in endpoint can fetch them per finding. Best-effort.
        if (response.llmInteractions() != null) {
            for (ShalqcInteraction i : response.llmInteractions()) {
                try {
                    llmInteractionRepository.save(shalqcMapper.toInteraction(i, qcResult.getId()));
                } catch (Exception ex) {
                    log.warn("Failed to persist LLM interaction {} for qcResult {}: {}",
                            i.id(), qcResult.getId(), ex.getMessage());
                }
            }
        }

        appraisal.setStatus(FileStatus.COMPLETED);
        batchFileRepository.save(appraisal);
        log.info("SHALqc QC result saved: file={} order={} decision={} pass={} fail={} verify={} cards={} llm={} batch={}",
                appraisal.getFilename(), response.orderId(), decision,
                shalqcMapper.passed(summary), shalqcMapper.failed(summary), shalqcMapper.verify(summary),
                cards.size(), response.llmInteractions() != null ? response.llmInteractions().size() : 0, batchId);

        // DocStats row: per-order timing + LLM token usage + $ cost, so the admin
        // DocStats page shows "what this document cost to QC". Best-effort — a
        // metrics write must never fail the QC result the reviewer is waiting on.
        try {
            writeDocStat(qcResult, appraisal, batchId, decision, cards.size(), response);
        } catch (Exception ex) {
            log.warn("DocStats write failed for order {} (QC result still saved): {}",
                    response.orderId(), ex.getMessage());
        }

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
            var engConf = fileMatchingService.getEngagementMatchConfidence(appraisal.getId());
            if (engConf.isPresent() && engConf.get() < worstMatchConf) {
                worstMatchConf = engConf.get();
                worstDocType = "Engagement letter";
            }
            var conConf = fileMatchingService.getContractMatchConfidence(appraisal.getId());
            if (conConf.isPresent() && conConf.get() < worstMatchConf) {
                worstMatchConf = conConf.get();
                worstDocType = "Contract";
            }
            if (worstDocType != null && worstMatchConf < MATCH_CONFIDENCE_THRESHOLD) {
                final String docType = worstDocType;
                final double conf = worstMatchConf;
                // Direct self-call (NOT via `self` proxy): must run in THIS transaction so it
                // sees the qcResult just saved above. A REQUIRES_NEW proxy hop would open a
                // separate tx that cannot see the uncommitted row and would silently no-op.
                downgradeToVerifyForLowMatchConfidence(qcResult.getId(), conf, docType);
                qcResult = qcResultRepository.findById(qcResult.getId()).orElse(qcResult);
                log.info("AUTO_PASS downgraded to TO_VERIFY for file {} — {} match confidence={} < {}",
                        appraisal.getFilename(), docType, conf, MATCH_CONFIDENCE_THRESHOLD);
            }
        }

        return qcResult;
    }

    /**
     * Persist one DocStats row for a completed order QC — per-order timing plus
     * the LLM token usage + $ cost from the Python {@code usage} block. This is
     * the ONLY writer of {@link DocStat}; without it the DocStats page stays
     * empty ("0 appraisals measured"). Values absent from an older Python build
     * are simply left null.
     */
    private void writeDocStat(QCResult qcResult, BatchFile appraisal, Long batchId,
                              QCDecision decision, int ruleCount, ShalqcResponse response) {
        Map<String, Object> usage = response.usage() != null ? response.usage() : Map.of();
        Map<String, Object> timings = response.timings() != null ? response.timings() : Map.of();

        Integer promptTok = intOf(usage.get("prompt_tokens"));
        Integer completionTok = intOf(usage.get("completion_tokens"));
        Integer totalTok = intOf(usage.get("total_tokens"));
        Integer billedCalls = intOf(usage.get("billed_calls"));
        Double costUsd = doubleOf(usage.get("cost_usd"));
        String model = usage.get("model") != null ? String.valueOf(usage.get("model")) : null;

        // Python timings are in SECONDS; DocStats stores milliseconds.
        Double totalMs = secToMs(timings.get("total_s"));
        Double judgeMs = secToMs(timings.get("judge_wall_s"));
        Double extractMs = secToMs(timings.get("extract_s"));

        Long clientId = appraisal.getBatch() != null && appraisal.getBatch().getClient() != null
                ? appraisal.getBatch().getClient().getId() : null;
        String clientName = appraisal.getBatch() != null && appraisal.getBatch().getClient() != null
                ? appraisal.getBatch().getClient().getName() : null;

        DocStat stat = DocStat.builder()
                .qcResult(qcResult)
                .batchFileId(appraisal.getId())
                .batchId(batchId)
                .clientId(clientId)
                .filename(appraisal.getFilename())
                .clientName(clientName)
                .qcDecision(decision != null ? decision.name() : null)
                .totalMs(totalMs)
                .measuredPipelineMs(extractMs)
                .ruleEngineMs(judgeMs)     // the judge/LLM phase IS the rule engine in the language pipeline
                .ruleCount(ruleCount)
                .slowestStageLabel(judgeMs != null ? "judging (LLM)" : null)
                .slowestStageMs(judgeMs)
                .llmCalls(billedCalls)
                .llmInferenceMs(judgeMs)
                .promptTokens(promptTok)
                .completionTokens(completionTok)
                .totalTokens(totalTok)
                .llmCostUsd(costUsd)
                .llmModel(model)
                .build();
        docStatRepository.save(stat);
        log.info("DocStats saved: file={} total={}ms tokens={} cost=${} model={}",
                appraisal.getFilename(), totalMs != null ? Math.round(totalMs) : null,
                totalTok, costUsd, model);
    }

    private static Integer intOf(Object v) {
        if (v instanceof Number n) return n.intValue();
        try { return v != null ? (int) Double.parseDouble(String.valueOf(v)) : null; }
        catch (NumberFormatException e) { return null; }
    }

    private static Double doubleOf(Object v) {
        if (v instanceof Number n) return n.doubleValue();
        try { return v != null ? Double.parseDouble(String.valueOf(v)) : null; }
        catch (NumberFormatException e) { return null; }
    }

    private static Double secToMs(Object seconds) {
        Double s = doubleOf(seconds);
        return s != null ? s * 1000.0 : null;
    }

    // Known rule-status vocabulary the engine may emit. Used only to detect ENUM
    // DRIFT — an unrecognised value still degrades safely to a needs-review state,
    // but is logged so a new Python status isn't silently swallowed (DB-002).
    private static final Set<String> KNOWN_RULE_STATUSES = Set.of(
            "pass", "fail", "verify", "review", "hold",
            "extraction_failed", "ocr_low_confidence", "system_error",
            "source_missing", "cross_doc_mismatch", "skipped", "not_applicable");

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

    private long queueWaitMs(JobScope scope, Instant pythonStartedAt) {
        Instant startedAt = startedAtMapFor(scope).get(scope.id());
        if (startedAt == null || pythonStartedAt == null || pythonStartedAt.isBefore(startedAt)) {
            return 0L;
        }
        return Duration.between(startedAt, pythonStartedAt).toMillis();
    }
    private long queueWaitMs(Long batchId, Instant pythonStartedAt) {
        return queueWaitMs(JobScope.batch(batchId), pythonStartedAt);
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
            boolean hadDecision = prev.getReviewerVerified() != null;
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
            carried++;
        }
        return carried;
    }

    private String decisionKey(QCRuleResult r) {
        return textOr(r.getRuleId(), "?") + "|" + textOr(r.getTargetField(), "");
    }

    /** Trimmed non-blank value, or the fallback. */
    private static String textOr(String v, String fallback) {
        return (v == null || v.isBlank()) ? fallback : v;
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
