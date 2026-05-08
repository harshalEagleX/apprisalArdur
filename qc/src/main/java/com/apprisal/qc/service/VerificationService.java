package com.apprisal.qc.service;

import com.apprisal.common.entity.*;
import com.apprisal.common.repository.BatchRepository;
import com.apprisal.common.repository.OperatorSessionRepository;
import com.apprisal.common.repository.ProcessingMetricsRepository;
import com.apprisal.common.repository.QCResultRepository;
import com.apprisal.common.repository.QCRuleResultRepository;
import com.apprisal.common.service.AuditLogService;
import com.apprisal.common.service.BusinessEventService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Duration;
import java.time.LocalDateTime;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import java.util.Locale;
import org.springframework.lang.NonNull;

/**
 * Service for handling reviewer verification of QC results.
 * Processes reviewer PASS/FAIL decisions and updates final decision.
 */
@Service
public class VerificationService {

    private static final Logger log = LoggerFactory.getLogger(VerificationService.class);
    private static final Duration REVIEW_LOCK_TTL = Duration.ofMinutes(30);
    private static final long MIN_VERIFY_DECISION_MS = 8_000L;
    private static final int MIN_FAIL_OVERRIDE_REASON_CHARS = 20;

    private final QCResultRepository qcResultRepository;
    private final QCRuleResultRepository qcRuleResultRepository;
    private final BatchRepository batchRepository;
    private final ProcessingMetricsRepository processingMetricsRepository;
    private final OperatorSessionRepository operatorSessionRepository;
    private final AuditLogService auditLogService;
    private final BusinessEventService businessEventService;

    public VerificationService(QCResultRepository qcResultRepository,
            QCRuleResultRepository qcRuleResultRepository,
            BatchRepository batchRepository,
            ProcessingMetricsRepository processingMetricsRepository,
            OperatorSessionRepository operatorSessionRepository,
            AuditLogService auditLogService,
            BusinessEventService businessEventService) {
        this.qcResultRepository = qcResultRepository;
        this.qcRuleResultRepository = qcRuleResultRepository;
        this.batchRepository = batchRepository;
        this.processingMetricsRepository = processingMetricsRepository;
        this.operatorSessionRepository = operatorSessionRepository;
        this.auditLogService = auditLogService;
        this.businessEventService = businessEventService;
    }

    @Transactional
    public QCResult beginReviewSession(@NonNull Long qcResultId, @NonNull User reviewer,
            boolean acknowledgeExistingLock, String ipAddress, String userAgent) {
        QCResult qcResult = getForVerification(qcResultId);
        assertDocumentCurrent(qcResult);
        LocalDateTime now = LocalDateTime.now();
        User lockedBy = qcResult.getReviewLockedBy();
        boolean activeLock = lockedBy != null
                && qcResult.getReviewLockExpiresAt() != null
                && qcResult.getReviewLockExpiresAt().isAfter(now);
        int priorActionCount = priorActionCount(qcResultId);

        if (activeLock && !Objects.equals(lockedBy.getId(), reviewer.getId())) {
            throw new IllegalStateException("This report is currently being reviewed by "
                    + displayName(lockedBy) + ". You can wait for the session to expire before continuing.");
        }

        if (!activeLock && priorActionCount > 0 && !acknowledgeExistingLock) {
            throw new IllegalStateException("This report has " + priorActionCount
                    + " server-saved decision(s) from a previous review session. Review those decisions before continuing.");
        }

        if (!activeLock || !Objects.equals(lockedBy != null ? lockedBy.getId() : null, reviewer.getId())) {
            qcResult.setReviewSessionToken(UUID.randomUUID().toString());
            qcResult.setReviewStartedAt(now);
            qcResult.setReviewLockAcknowledged(activeLock && acknowledgeExistingLock);
        } else if (qcResult.getReviewSessionToken() == null || qcResult.getReviewSessionToken().isBlank()) {
            qcResult.setReviewSessionToken(UUID.randomUUID().toString());
        }

        qcResult.setReviewLockedBy(reviewer);
        qcResult.setReviewLastActiveAt(now);
        qcResult.setReviewLockExpiresAt(now.plus(REVIEW_LOCK_TTL));

        Batch batch = qcResult.getBatchFile() != null ? qcResult.getBatchFile().getBatch() : null;
        if (batch != null && batch.getStatus() == BatchStatus.REVIEW_PENDING) {
            batch.setStatus(BatchStatus.IN_REVIEW);
            batchRepository.save(batch);
        }
        QCResult saved = qcResultRepository.save(qcResult);

        markItemsPresented(qcResultId, saved.getReviewSessionToken());
        auditLogService.log(reviewer, "REVIEW_SESSION_STARTED", "QCResult", qcResultId,
                "sessionToken=" + saved.getReviewSessionToken(), ipAddress, userAgent);
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("session_token", saved.getReviewSessionToken());
        payload.put("lock_expires_at", saved.getReviewLockExpiresAt() != null ? saved.getReviewLockExpiresAt().toString() : null);
        payload.put("prior_action_count", priorActionCount);
        businessEventService.qcEvent("REVIEW_OPENED", reviewer, saved, "STARTED", payload);
        return saved;
    }

    @Transactional(readOnly = true)
    public int priorActionCount(@NonNull Long qcResultId) {
        return (int) qcRuleResultRepository.findVerificationItemsForQcResult(qcResultId).stream()
                .filter(item -> item.getReviewerVerified() != null || Boolean.TRUE.equals(item.getOverridePending()))
                .count();
    }

    @Transactional
    public QCResult heartbeatReviewSession(@NonNull Long qcResultId, @NonNull String sessionToken) {
        QCResult qcResult = getForVerification(qcResultId);
        assertDocumentCurrent(qcResult);
        assertSessionOwnsQcResult(qcResult, sessionToken);
        LocalDateTime now = LocalDateTime.now();
        qcResult.setReviewLastActiveAt(now);
        qcResult.setReviewLockExpiresAt(now.plus(REVIEW_LOCK_TTL));
        return qcResultRepository.save(qcResult);
    }

    @Transactional
    public void releaseReviewSession(@NonNull Long qcResultId, @NonNull String sessionToken) {
        QCResult qcResult = getForVerification(qcResultId);
        if (sessionToken.equals(qcResult.getReviewSessionToken())) {
            qcResult.setReviewLockExpiresAt(LocalDateTime.now());
            qcResultRepository.save(qcResult);
            Batch batch = qcResult.getBatchFile() != null ? qcResult.getBatchFile().getBatch() : null;
            if (batch != null && batch.getStatus() == BatchStatus.IN_REVIEW && qcResult.getFinalDecision() == null) {
                batch.setStatus(BatchStatus.REVIEW_PENDING);
                batchRepository.save(batch);
                businessEventService.qcEvent("REVIEW_RELEASED", qcResult.getReviewLockedBy(), qcResult, "RELEASED",
                        Map.of("session_token", sessionToken));
            }
        }
    }

    @Transactional
    public void markItemsPresented(@NonNull Long qcResultId, @NonNull String sessionToken) {
        LocalDateTime now = LocalDateTime.now();
        for (QCRuleResult item : qcRuleResultRepository.findPendingVerificationForQcResult(qcResultId)) {
            if (item.getFirstPresentedAt() == null) {
                item.setFirstPresentedAt(now);
            }
            if (item.getReviewSessionToken() == null || item.getReviewSessionToken().isBlank()) {
                item.setReviewSessionToken(sessionToken);
            }
            qcRuleResultRepository.save(item);
        }
    }

    /**
     * Get QC result for verification.
     */
    @Transactional(readOnly = true)
    public QCResult getForVerification(@NonNull Long qcResultId) {
        return qcResultRepository.findById(qcResultId)
                .orElseThrow(() -> new RuntimeException("QC Result not found: " + qcResultId));
    }

    /**
     * Get items that need verification for a QC result.
     */
    @Transactional(readOnly = true)
    public List<QCRuleResult> getVerificationItems(Long qcResultId) {
        return qcRuleResultRepository.findVerificationItemsForQcResult(qcResultId);
    }

    /**
     * Get pending (unverified) items for a QC result.
     */
    @Transactional(readOnly = true)
    public List<QCRuleResult> getPendingItems(Long qcResultId) {
        return qcRuleResultRepository.findPendingVerificationForQcResult(qcResultId);
    }

    /**
     * Get ALL rule results for a QC result (for full rule visibility UI).
     */
    @Transactional(readOnly = true)
    public List<QCRuleResult> getAllRuleResults(Long qcResultId) {
        return qcRuleResultRepository.findByQcResultId(qcResultId);
    }

    @Transactional
    public void recordRuleFocused(@NonNull Long ruleResultId, @NonNull String sessionToken, @NonNull User reviewer) {
        QCRuleResult ruleResult = qcRuleResultRepository.findById(ruleResultId)
                .orElseThrow(() -> new RuntimeException("Rule result not found: " + ruleResultId));
        QCResult qcResult = ruleResult.getQcResult();
        assertDocumentCurrent(qcResult);
        assertSessionOwnsQcResult(qcResult, sessionToken);

        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("rule_id", ruleResult.getRuleId());
        payload.put("rule_name", ruleResult.getRuleName());
        payload.put("status", ruleResult.getStatus());
        payload.put("severity", ruleResult.getSeverity());
        payload.put("pdf_page", ruleResult.getPdfPage());
        payload.put("has_bbox", ruleResult.getBboxX() != null && ruleResult.getBboxY() != null
                && ruleResult.getBboxW() != null && ruleResult.getBboxH() != null);

        Long batchId = qcResult != null && qcResult.getBatchFile() != null && qcResult.getBatchFile().getBatch() != null
                ? qcResult.getBatchFile().getBatch().getId()
                : null;
        Long batchFileId = qcResult != null && qcResult.getBatchFile() != null ? qcResult.getBatchFile().getId() : null;
        businessEventService.record("REVIEW_RULE_FOCUSED", reviewer, "frontend", "FOCUSED",
                "QCRuleResult", ruleResult.getId(), batchId, batchFileId,
                qcResult != null ? qcResult.getId() : null, ruleResult.getId(), payload);
        touchOperatorSession(reviewer);
    }

    /**
     * Save a single decision (for auto-save AJAX calls).
     * 
     * @param ruleResultId The rule result to update
     * @param decision     "PASS" or "FAIL"
     * @param comment      Optional reviewer comment
     * @return Updated rule result
     */
    @Transactional
    public QCRuleResult saveDecision(@NonNull Long ruleResultId, @NonNull String decision, String comment,
            @NonNull String sessionToken, Long decisionLatencyMs, Boolean acknowledged, @NonNull User reviewer,
            String ipAddress, String userAgent) {
        QCRuleResult ruleResult = qcRuleResultRepository.findByIdForUpdate(ruleResultId)
                .orElseThrow(() -> new RuntimeException("Rule result not found: " + ruleResultId));
        QCResult qcResult = ruleResult.getQcResult();
        assertDocumentCurrent(qcResult);
        assertSessionOwnsQcResult(qcResult, sessionToken);
        if (isDuplicateSubmission(ruleResult, decision, comment, sessionToken)) {
            return ruleResult;
        }
        validateFreshDecision(ruleResult, sessionToken);
        validateEngagement(ruleResult, decisionLatencyMs, acknowledged);

        boolean passed = isPassDecision(decision);
        String originalStatus = normalizedStatus(ruleResult.getStatus());
        boolean wasOverridePending = Boolean.TRUE.equals(ruleResult.getOverridePending());

        if (passed && "fail".equals(originalStatus)) {
            handleFailOverride(ruleResult, comment, reviewer, sessionToken);
        } else {
            ruleResult.setReviewerVerified(passed);
            ruleResult.setReviewerComment(comment);
            ruleResult.setVerifiedAt(LocalDateTime.now());
            ruleResult.setOverridePending(false);

            if (passed) {
                ruleResult.setStatus("MANUAL_PASS");
            } else {
                ruleResult.setStatus("FAIL");
            }
        }

        ruleResult.setReviewSessionToken(sessionToken);
        ruleResult.setDecisionLatencyMs(decisionLatencyMs);
        ruleResult.setAcknowledgedReferences(Boolean.TRUE.equals(acknowledged));

        qcRuleResultRepository.saveAndFlush(ruleResult);

        // Recalculate parent QCResult counters
        recalculateCounters(Objects.requireNonNull(qcResult.getId()));
        auditLogService.log(reviewer, "REVIEW_DECISION_SAVED", "QCRuleResult", ruleResultId,
                "ruleId=" + ruleResult.getRuleId()
                        + ", decision=" + decision
                        + ", status=" + ruleResult.getStatus()
                        + ", overridePending=" + Boolean.TRUE.equals(ruleResult.getOverridePending())
                        + ", latencyMs=" + decisionLatencyMs,
                ipAddress, userAgent);
        recordRuleDecisionEvent(ruleResult, reviewer, decision, decisionLatencyMs, acknowledged, originalStatus, wasOverridePending);

        log.info("Decision saved: ruleResultId={}, decision={}, newStatus={}",
                ruleResultId, decision, ruleResult.getStatus());

        return ruleResult;
    }

    /**
     * Submit verification for a single rule result.
     *
     * @param ruleResultId The rule result to verify
     * @param accepted     true = pass, false = fail
     * @param comment      Reviewer comment
     * @param reviewer     The reviewer making the decision
     */
    @Transactional
    public QCRuleResult verifyRuleItem(@NonNull Long ruleResultId, boolean accepted, String comment, User reviewer) {
        QCRuleResult ruleResult = qcRuleResultRepository.findById(ruleResultId)
                .orElseThrow(() -> new RuntimeException("Rule result not found: " + ruleResultId));

        ruleResult.setReviewerVerified(accepted);
        ruleResult.setReviewerComment(comment);
        ruleResult.setVerifiedAt(LocalDateTime.now());

        qcRuleResultRepository.save(ruleResult);
        log.info("Rule {} verified: passed={}, comment={}", ruleResult.getRuleId(), accepted, comment);

        return ruleResult;
    }

    /**
     * Submit all verifications and compute final decision.
     *
     * @param qcResultId   The QC result
     * @param decisions    List of decisions (ruleResultId -> accepted)
     * @param comments     List of comments (ruleResultId -> comment)
     * @param reviewer     The reviewer
     * @param overallNotes Overall reviewer notes
     */
    @Transactional
    public QCResult submitVerification(@NonNull Long qcResultId,
            @NonNull java.util.Map<Long, Boolean> decisions,
            java.util.Map<Long, String> comments,
            @NonNull User reviewer,
            String overallNotes) {
        QCResult qcResult = getForVerification(qcResultId);

        // Update each rule result
        for (java.util.Map.Entry<Long, Boolean> entry : decisions.entrySet()) {
            Long ruleId = entry.getKey();
            if (ruleId == null)
                continue;
            boolean accepted = Objects.requireNonNull(entry.getValue());
            String comment = comments != null ? comments.get(ruleId) : null;
            verifyRuleItem(ruleId, accepted, comment, reviewer);
        }

        // Compute final decision
        // If any item is failed, final decision is FAIL.
        // If all items are passed, final decision is PASS.
        List<QCRuleResult> verifiedItems = qcRuleResultRepository.findVerificationItemsForQcResult(qcResultId);
        boolean anyFailed = verifiedItems.stream()
                .anyMatch(item -> Boolean.FALSE.equals(item.getReviewerVerified()));

        FinalDecision finalDecision = anyFailed ? FinalDecision.FAIL : FinalDecision.PASS;

        qcResult.setFinalDecision(finalDecision);
        qcResult.setReviewedBy(reviewer);
        qcResult.setReviewedAt(LocalDateTime.now());
        qcResult.setReviewerNotes(overallNotes);

        QCResult saved = qcResultRepository.save(qcResult);
        completeBatchIfReviewFinished(saved);
        recordReviewSubmitted(saved, reviewer, "submitVerification");

        log.info("QC Result {} verification complete: finalDecision={}, reviewedBy={}",
                qcResultId, finalDecision, reviewer.getUsername());

        return saved;
    }

    /**
     * Quick pass all items.
     */
    @Transactional
    public QCResult acceptAll(@NonNull Long qcResultId, @NonNull User reviewer, String notes) {
        QCResult qcResult = getForVerification(qcResultId);
        List<QCRuleResult> items = getVerificationItems(qcResultId);

        for (QCRuleResult item : items) {
            item.setReviewerVerified(true);
            item.setReviewerComment("Bulk passed");
            item.setVerifiedAt(LocalDateTime.now());
            qcRuleResultRepository.save(item);
        }

        qcResult.setFinalDecision(FinalDecision.PASS);
        qcResult.setReviewedBy(reviewer);
        qcResult.setReviewedAt(LocalDateTime.now());
        qcResult.setReviewerNotes(notes);

        QCResult saved = qcResultRepository.save(qcResult);
        completeBatchIfReviewFinished(saved);
        recordReviewSubmitted(saved, reviewer, "acceptAll");
        return saved;
    }

    /**
     * Fail entire QC result.
     */
    @Transactional
    public QCResult rejectAll(@NonNull Long qcResultId, @NonNull User reviewer, String reason) {
        QCResult qcResult = getForVerification(qcResultId);

        qcResult.setFinalDecision(FinalDecision.FAIL);
        qcResult.setReviewedBy(reviewer);
        qcResult.setReviewedAt(LocalDateTime.now());
        qcResult.setReviewerNotes(reason);

        QCResult saved = qcResultRepository.save(qcResult);
        completeBatchIfReviewFinished(saved);
        recordReviewSubmitted(saved, reviewer, "rejectAll");
        return saved;
    }

    /**
     * Complete a review from decisions that were already auto-saved.
     */
    @Transactional
    public QCResult completeSavedVerification(@NonNull Long qcResultId, @NonNull User reviewer, String notes) {
        QCResult qcResult = getForVerification(qcResultId);
        assertDocumentCurrent(qcResult);
        List<QCRuleResult> verificationItems = qcRuleResultRepository.findVerificationItemsForQcResult(qcResultId);

        boolean hasPending = verificationItems.stream()
                .anyMatch(item -> item.getReviewerVerified() == null || Boolean.TRUE.equals(item.getOverridePending()));
        if (hasPending) {
            throw new IllegalStateException("All review items must be marked Pass or Fail, and FAIL overrides must be second-approved, before submitting.");
        }

        boolean anyFailed = verificationItems.stream()
                .anyMatch(item -> Boolean.FALSE.equals(item.getReviewerVerified()));

        qcResult.setFinalDecision(anyFailed ? FinalDecision.FAIL : FinalDecision.PASS);
        qcResult.setReviewedBy(reviewer);
        qcResult.setReviewedAt(LocalDateTime.now());
        qcResult.setReviewerNotes(notes);

        QCResult saved = qcResultRepository.save(qcResult);
        completeBatchIfReviewFinished(saved);
        recordReviewSubmitted(saved, reviewer, "completeSavedVerification");
        return saved;
    }

    /**
     * IDOR guard: throw SecurityException if reviewer is not assigned to the batch
     * containing this QC result.
     */
    @Transactional(readOnly = true)
    public void assertReviewerOwnsQcResult(@NonNull Long qcResultId, @NonNull Long reviewerId) {
        boolean owns = qcResultRepository.isReviewerAssigned(qcResultId, reviewerId);
        if (!owns) {
            throw new SecurityException("Reviewer " + reviewerId + " is not assigned to QC result " + qcResultId);
        }
    }

    /**
     * IDOR guard: throw SecurityException if reviewer is not assigned to the batch
     * containing the rule result.
     */
    @Transactional(readOnly = true)
    public void assertReviewerOwnsRuleResult(@NonNull Long ruleResultId, @NonNull Long reviewerId) {
        QCRuleResult rule = qcRuleResultRepository.findById(ruleResultId)
                .orElseThrow(() -> new RuntimeException("Rule result not found: " + ruleResultId));
        assertReviewerOwnsQcResult(rule.getQcResult().getId(), reviewerId);
    }

    /**
     * Recalculate all counters for a QC result based on current rule statuses.
     * Called after every reviewer decision to keep counters accurate.
     *
     * Uses a JPQL UPDATE rather than load-mutate-save: loading the parent
     * QCResult forces Hibernate to dirty-check its 138-item @OneToMany rule
     * list, and saving it produces a QCResult_AUD row via Envers — combined
     * cost was ~1-2s per decision. The bulk UPDATE bypasses both and runs in
     * a few ms.
     */
    private void recalculateCounters(@NonNull Long qcResultId) {
        int passCount = 0;
        int failCount = 0;
        int manualPassCount = 0;

        for (Object[] row : qcRuleResultRepository.countByStatusForQcResult(qcResultId)) {
            String status = row[0] != null ? row[0].toString().trim().toLowerCase(Locale.ROOT) : "";
            int count = row[1] instanceof Number ? ((Number) row[1]).intValue() : 0;
            if ("pass".equals(status)) {
                passCount = count;
            } else if ("fail".equals(status)) {
                failCount = count;
            } else if ("manual_pass".equals(status)) {
                manualPassCount = count;
            }
        }
        int verifyCount = 0;
        Object[] progressCounts = firstProgressRow(qcResultId);
        if (progressCounts != null && progressCounts.length >= 3 && progressCounts[2] instanceof Number pending) {
            verifyCount = pending.intValue();
        }

        qcResultRepository.updateCounters(qcResultId, passCount, failCount, verifyCount, manualPassCount);

        log.debug("Recalculated counters for QCResult {}: pass={}, fail={}, verify={}, manualPass={}",
                qcResultId, passCount, failCount, verifyCount, manualPassCount);
    }

    private void completeBatchIfReviewFinished(QCResult qcResult) {
        BatchFile batchFile = qcResult.getBatchFile();
        if (batchFile == null || batchFile.getBatch() == null) {
            return;
        }

        Batch batch = batchFile.getBatch();
        boolean hasPendingReviewerWork = qcResultRepository.findByBatchId(batch.getId()).stream()
                .anyMatch(result -> result.getQcDecision() != QCDecision.AUTO_PASS
                        && result.getFinalDecision() == null);
        if (hasPendingReviewerWork || batch.getStatus() == BatchStatus.COMPLETED) {
            return;
        }

        batch.setStatus(BatchStatus.COMPLETED);
        batch.setErrorMessage(null);
        batchRepository.save(batch);
        businessEventService.batchEvent("BATCH_COMPLETED", qcResult.getReviewedBy(), batch, "COMPLETED",
                Map.of("qc_result_id", qcResult.getId()));
        log.info("Batch {} completed after reviewer verification", batch.getId());
    }

    private void recordRuleDecisionEvent(QCRuleResult ruleResult, User reviewer, String decision,
            Long decisionLatencyMs, Boolean acknowledged, String originalStatus, boolean wasOverridePending) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("rule_id", ruleResult.getRuleId());
        payload.put("decision", decision);
        payload.put("original_status", originalStatus);
        payload.put("new_status", ruleResult.getStatus());
        payload.put("latency_ms", decisionLatencyMs);
        payload.put("acknowledged", Boolean.TRUE.equals(acknowledged));
        payload.put("override_pending", Boolean.TRUE.equals(ruleResult.getOverridePending()));
        QCResult qcResult = ruleResult.getQcResult();
        Long batchId = qcResult != null && qcResult.getBatchFile() != null && qcResult.getBatchFile().getBatch() != null
                ? qcResult.getBatchFile().getBatch().getId()
                : null;
        Long batchFileId = qcResult != null && qcResult.getBatchFile() != null ? qcResult.getBatchFile().getId() : null;
        businessEventService.record("REVIEW_RULE_DECIDED", reviewer, "java", ruleResult.getStatus(),
                "QCRuleResult", ruleResult.getId(), batchId, batchFileId,
                qcResult != null ? qcResult.getId() : null, ruleResult.getId(), payload);
        recordReviewerDecisionActivity(reviewer, originalStatus, ruleResult.getStatus());

        if ("fail".equals(originalStatus) && "PASS".equalsIgnoreCase(decision)) {
            String eventType = wasOverridePending ? "OVERRIDE_APPROVED" : "OVERRIDE_REQUESTED";
            String outcome = wasOverridePending ? "APPROVED" : "PENDING";
            businessEventService.record(eventType, reviewer, "java", outcome,
                    "QCRuleResult", ruleResult.getId(), batchId, batchFileId,
                    qcResult != null ? qcResult.getId() : null, ruleResult.getId(), payload);
        } else if (wasOverridePending && "FAIL".equalsIgnoreCase(decision)) {
            businessEventService.record("OVERRIDE_REJECTED", reviewer, "java", "REJECTED",
                    "QCRuleResult", ruleResult.getId(), batchId, batchFileId,
                    qcResult != null ? qcResult.getId() : null, ruleResult.getId(), payload);
        }
    }

    private void recordReviewSubmitted(QCResult qcResult, User reviewer, String source) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("source", source);
        payload.put("final_decision", qcResult.getFinalDecision() != null ? qcResult.getFinalDecision().name() : null);
        payload.put("reviewed_at", qcResult.getReviewedAt() != null ? qcResult.getReviewedAt().toString() : null);
        payload.put("reviewer_notes_present", qcResult.getReviewerNotes() != null && !qcResult.getReviewerNotes().isBlank());
        attachOperatorSessionToMetrics(qcResult, reviewer);
        businessEventService.qcEvent("REVIEW_SUBMITTED", reviewer, qcResult,
                qcResult.getFinalDecision() != null ? qcResult.getFinalDecision().name() : "UNKNOWN",
                payload);
    }

    private void recordReviewerDecisionActivity(User reviewer, String originalStatus, String newStatus) {
        activeSession(reviewer).ifPresent(session -> {
            session.setLastActiveAt(LocalDateTime.now());
            session.setStatus(OperatorSession.Status.ACTIVE);
            if (!Objects.equals(normalizedStatus(originalStatus), normalizedStatus(newStatus))) {
                session.setCorrectionsMade(Objects.requireNonNullElse(session.getCorrectionsMade(), 0) + 1);
            }
            operatorSessionRepository.save(session);
        });
    }

    private void touchOperatorSession(User reviewer) {
        activeSession(reviewer).ifPresent(session -> {
            session.setLastActiveAt(LocalDateTime.now());
            session.setStatus(OperatorSession.Status.ACTIVE);
            operatorSessionRepository.save(session);
        });
    }

    private void attachOperatorSessionToMetrics(QCResult qcResult, User reviewer) {
        activeSession(reviewer).ifPresent(session -> {
            processingMetricsRepository.findByQcResultId(qcResult.getId()).ifPresent(metrics -> {
                metrics.setOperatorSessionId(session.getId());
                processingMetricsRepository.save(metrics);
            });
            session.setFilesProcessed(Objects.requireNonNullElse(session.getFilesProcessed(), 0) + 1);
            session.setLastActiveAt(LocalDateTime.now());
            session.setStatus(OperatorSession.Status.ACTIVE);
            operatorSessionRepository.save(session);
        });
    }

    private java.util.Optional<OperatorSession> activeSession(User reviewer) {
        if (reviewer == null || reviewer.getId() == null) {
            return java.util.Optional.empty();
        }
        List<OperatorSession> active = operatorSessionRepository.findByUserIdAndStatus(reviewer.getId(), OperatorSession.Status.ACTIVE);
        if (!active.isEmpty()) {
            return java.util.Optional.of(active.get(0));
        }
        List<OperatorSession> idle = operatorSessionRepository.findByUserIdAndStatus(reviewer.getId(), OperatorSession.Status.IDLE);
        return idle.stream().findFirst();
    }

    private boolean isPassDecision(String decision) {
        String normalized = decision == null ? "" : decision.trim().toUpperCase();
        if ("PASS".equals(normalized)) {
            return true;
        }
        if ("FAIL".equals(normalized)) {
            return false;
        }
        throw new IllegalArgumentException("decision must be PASS or FAIL");
    }

    private void assertSessionOwnsQcResult(QCResult qcResult, String sessionToken) {
        if (sessionToken == null || sessionToken.isBlank()) {
            throw new IllegalStateException("Review session token is required.");
        }
        if (!sessionToken.equals(qcResult.getReviewSessionToken())) {
            throw new IllegalStateException("This review session is stale. Reload the report before saving decisions.");
        }
        if (qcResult.getReviewLockExpiresAt() == null || qcResult.getReviewLockExpiresAt().isBefore(LocalDateTime.now())) {
            throw new IllegalStateException("This review session has timed out. Resume the report before saving decisions.");
        }
    }

    private void assertDocumentCurrent(QCResult qcResult) {
        if (qcResult == null || qcResult.getBatchFile() == null) {
            return;
        }
        String processedHash = qcResult.getSourceDocumentHash();
        String currentHash = qcResult.getBatchFile().getContentHash();
        Long processedVersion = qcResult.getSourceDocumentVersion();
        Long currentVersion = qcResult.getBatchFile().getContentVersion();
        boolean hashMismatch = processedHash != null && currentHash != null && !processedHash.equals(currentHash);
        boolean versionMismatch = processedVersion != null && currentVersion != null && currentVersion > processedVersion;
        if (hashMismatch || versionMismatch) {
            throw new IllegalStateException("A newer version of this appraisal was submitted after these QC results were generated. Restart QC review from the latest version.");
        }
    }

    private void validateFreshDecision(QCRuleResult ruleResult, String sessionToken) {
        if (ruleResult.getReviewerVerified() != null
                && ruleResult.getReviewSessionToken() != null
                && !sessionToken.equals(ruleResult.getReviewSessionToken())
                && !Boolean.TRUE.equals(ruleResult.getOverridePending())) {
            throw new IllegalStateException("This review item was already decided in another session. Refresh the page to see the latest saved decision.");
        }
    }

    private void validateEngagement(QCRuleResult ruleResult, Long decisionLatencyMs, Boolean acknowledged) {
        String status = normalizedStatus(ruleResult.getStatus());
        if ("verify".equals(status)) {
            long clientLatency = decisionLatencyMs == null ? 0L : decisionLatencyMs;
            long serverLatency = ruleResult.getFirstPresentedAt() == null
                    ? 0L
                    : Duration.between(ruleResult.getFirstPresentedAt(), LocalDateTime.now()).toMillis();
            long latency = Math.max(clientLatency, serverLatency);
            if (latency < MIN_VERIFY_DECISION_MS) {
                throw new IllegalStateException("Please review the referenced sections before saving this decision.");
            }
            if (isHighSeverity(ruleResult) && !Boolean.TRUE.equals(acknowledged)) {
                throw new IllegalStateException("High-severity VERIFY items require acknowledgement before decision.");
            }
        }
    }

    private void handleFailOverride(QCRuleResult ruleResult, String comment, User reviewer, String sessionToken) {
        String reason = comment == null ? "" : comment.trim();
        if (reason.length() < MIN_FAIL_OVERRIDE_REASON_CHARS) {
            throw new IllegalStateException("FAIL override requires a specific reason of at least 20 characters.");
        }

        if (Boolean.TRUE.equals(ruleResult.getOverridePending())) {
            User requestedBy = ruleResult.getOverrideRequestedBy();
            if (requestedBy != null && Objects.equals(requestedBy.getId(), reviewer.getId())) {
                throw new IllegalStateException("FAIL override requires approval from a second reviewer.");
            }
            ruleResult.setReviewerVerified(true);
            ruleResult.setStatus("MANUAL_PASS");
            ruleResult.setOverridePending(false);
            ruleResult.setOverrideApprovedBy(reviewer);
            ruleResult.setOverrideApprovedAt(LocalDateTime.now());
            ruleResult.setVerifiedAt(LocalDateTime.now());
            ruleResult.setReviewerComment(reason);
            return;
        }

        ruleResult.setReviewerVerified(null);
        ruleResult.setReviewerComment(reason);
        ruleResult.setReviewSessionToken(sessionToken);
        ruleResult.setOverridePending(true);
        ruleResult.setOverrideRequestedBy(reviewer);
        ruleResult.setOverrideRequestedAt(LocalDateTime.now());
        ruleResult.setVerifiedAt(LocalDateTime.now());
    }

    private boolean isHighSeverity(QCRuleResult ruleResult) {
        String severity = ruleResult.getSeverity() == null ? "" : ruleResult.getSeverity().trim().toUpperCase();
        return "BLOCKING".equals(severity);
    }

    private Object[] firstProgressRow(Long qcResultId) {
        List<Object[]> rows = qcRuleResultRepository.progressCountsForQcResult(qcResultId);
        if (rows == null || rows.isEmpty() || rows.get(0) == null) {
            return new Object[] {0L, 0L, 0L};
        }
        return rows.get(0);
    }

    private boolean isDuplicateSubmission(QCRuleResult ruleResult, String decision, String comment, String sessionToken) {
        if (!Objects.equals(ruleResult.getReviewSessionToken(), sessionToken)) {
            return false;
        }

        String normalizedDecision = decision == null ? "" : decision.trim().toUpperCase(Locale.ROOT);
        String normalizedComment = comment == null ? "" : comment.trim();
        String currentStatus = normalizedStatus(ruleResult.getStatus());
        String currentComment = ruleResult.getReviewerComment() == null ? "" : ruleResult.getReviewerComment().trim();

        if ("PASS".equals(normalizedDecision)
                && Boolean.TRUE.equals(ruleResult.getOverridePending())
                && normalizedComment.equals(currentComment)) {
            return true;
        }

        if ("PASS".equals(normalizedDecision)
                && Boolean.TRUE.equals(ruleResult.getReviewerVerified())
                && "manual_pass".equals(currentStatus)
                && normalizedComment.equals(currentComment)) {
            return true;
        }

        return "FAIL".equals(normalizedDecision)
                && Boolean.FALSE.equals(ruleResult.getReviewerVerified())
                && "fail".equals(currentStatus)
                && normalizedComment.equals(currentComment);
    }

    private String normalizedStatus(String status) {
        if (status == null || status.isBlank()) {
            return "verify";
        }
        return status.trim().toLowerCase();
    }

    private String displayName(User user) {
        if (user == null) return "another reviewer";
        if (user.getFullName() != null && !user.getFullName().isBlank()) return user.getFullName();
        return user.getUsername();
    }
}
