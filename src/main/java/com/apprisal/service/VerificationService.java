package com.apprisal.service;

import com.apprisal.entity.*;
import com.apprisal.repository.QCResultRepository;
import com.apprisal.repository.QCRuleResultRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Objects;
import org.springframework.lang.NonNull;

/**
 * Service for handling reviewer verification of QC results.
 * Processes reviewer decisions on WARNING items and updates final decision.
 */
@Service
public class VerificationService {

    private static final Logger log = LoggerFactory.getLogger(VerificationService.class);

    private final QCResultRepository qcResultRepository;
    private final QCRuleResultRepository qcRuleResultRepository;

    public VerificationService(QCResultRepository qcResultRepository,
            QCRuleResultRepository qcRuleResultRepository) {
        this.qcResultRepository = qcResultRepository;
        this.qcRuleResultRepository = qcRuleResultRepository;
    }

    /**
     * Get QC result for verification.
     */
    public QCResult getForVerification(@NonNull Long qcResultId) {
        return qcResultRepository.findById(qcResultId)
                .orElseThrow(() -> new RuntimeException("QC Result not found: " + qcResultId));
    }

    /**
     * Get items that need verification for a QC result.
     */
    public List<QCRuleResult> getVerificationItems(Long qcResultId) {
        return qcRuleResultRepository.findVerificationItemsForQcResult(qcResultId);
    }

    /**
     * Get pending (unverified) items for a QC result.
     */
    public List<QCRuleResult> getPendingItems(Long qcResultId) {
        return qcRuleResultRepository.findPendingVerificationForQcResult(qcResultId);
    }

    /**
     * Get ALL rule results for a QC result (for full rule visibility UI).
     */
    public List<QCRuleResult> getAllRuleResults(Long qcResultId) {
        return qcRuleResultRepository.findByQcResultId(qcResultId);
    }

    /**
     * Save a single decision (for auto-save AJAX calls).
     * 
     * @param ruleResultId The rule result to update
     * @param decision     "ACCEPT" or "REJECT"
     * @param comment      Optional reviewer comment
     * @return Updated rule result
     */
    @Transactional
    public QCRuleResult saveDecision(@NonNull Long ruleResultId, @NonNull String decision, String comment) {
        QCRuleResult ruleResult = qcRuleResultRepository.findById(ruleResultId)
                .orElseThrow(() -> new RuntimeException("Rule result not found: " + ruleResultId));

        boolean accepted = "ACCEPT".equalsIgnoreCase(decision);

        // Set reviewer decision fields
        ruleResult.setReviewerVerified(accepted);
        ruleResult.setReviewerComment(comment);
        ruleResult.setVerifiedAt(LocalDateTime.now());

        // Update status based on decision
        if (accepted) {
            ruleResult.setStatus("MANUAL_PASS");
        } else {
            ruleResult.setStatus("FAIL");
        }

        qcRuleResultRepository.save(ruleResult);

        // Recalculate parent QCResult counters
        recalculateCounters(Objects.requireNonNull(ruleResult.getQcResult().getId()));

        log.info("Decision saved: ruleResultId={}, decision={}, newStatus={}",
                ruleResultId, decision, ruleResult.getStatus());

        return ruleResult;
    }

    /**
     * Submit verification for a single rule result.
     *
     * @param ruleResultId The rule result to verify
     * @param accepted     true = accept, false = reject
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
        log.info("Rule {} verified: accepted={}, comment={}", ruleResult.getRuleId(), accepted, comment);

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
        // If any item is rejected, final decision is FAIL
        // If all items are accepted, final decision is PASS
        List<QCRuleResult> verifiedItems = qcRuleResultRepository.findVerificationItemsForQcResult(qcResultId);
        boolean anyRejected = verifiedItems.stream()
                .anyMatch(item -> Boolean.FALSE.equals(item.getReviewerVerified()));

        FinalDecision finalDecision = anyRejected ? FinalDecision.FAIL : FinalDecision.PASS;

        qcResult.setFinalDecision(finalDecision);
        qcResult.setReviewedBy(reviewer);
        qcResult.setReviewedAt(LocalDateTime.now());
        qcResult.setReviewerNotes(overallNotes);

        qcResultRepository.save(qcResult);

        log.info("QC Result {} verification complete: finalDecision={}, reviewedBy={}",
                qcResultId, finalDecision, reviewer.getUsername());

        return qcResult;
    }

    /**
     * Quick accept all items (for obvious passes).
     */
    @Transactional
    public QCResult acceptAll(@NonNull Long qcResultId, @NonNull User reviewer, String notes) {
        QCResult qcResult = getForVerification(qcResultId);
        List<QCRuleResult> items = getVerificationItems(qcResultId);

        for (QCRuleResult item : items) {
            item.setReviewerVerified(true);
            item.setReviewerComment("Bulk approved");
            item.setVerifiedAt(LocalDateTime.now());
            qcRuleResultRepository.save(item);
        }

        qcResult.setFinalDecision(FinalDecision.PASS);
        qcResult.setReviewedBy(reviewer);
        qcResult.setReviewedAt(LocalDateTime.now());
        qcResult.setReviewerNotes(notes);

        return qcResultRepository.save(qcResult);
    }

    /**
     * Reject entire QC result (quick reject).
     */
    @Transactional
    public QCResult rejectAll(@NonNull Long qcResultId, @NonNull User reviewer, String reason) {
        QCResult qcResult = getForVerification(qcResultId);

        qcResult.setFinalDecision(FinalDecision.FAIL);
        qcResult.setReviewedBy(reviewer);
        qcResult.setReviewedAt(LocalDateTime.now());
        qcResult.setReviewerNotes(reason);

        return qcResultRepository.save(qcResult);
    }

    /**
     * Recalculate all counters for a QC result based on current rule statuses.
     * Called after each reviewer decision to keep counters accurate.
     */
    @Transactional
    private void recalculateCounters(@NonNull Long qcResultId) {
        QCResult qcResult = qcResultRepository.findById(qcResultId)
                .orElseThrow(() -> new RuntimeException("QC Result not found: " + qcResultId));

        List<QCRuleResult> allRules = qcRuleResultRepository.findByQcResultId(qcResultId);

        int passCount = 0;
        int failCount = 0;
        int verifyCount = 0;
        int manualPassCount = 0;

        for (QCRuleResult rule : allRules) {
            String status = rule.getStatus();

            if ("PASS".equals(status)) {
                passCount++;
            } else if ("FAIL".equals(status)) {
                failCount++;
            } else if ("MANUAL_PASS".equals(status)) {
                manualPassCount++;
            }

            // Verify count: reviewRequired=true AND not yet decided
            if (Boolean.TRUE.equals(rule.getReviewRequired()) && rule.getReviewerVerified() == null) {
                verifyCount++;
            }
        }

        qcResult.setPassedCount(passCount);
        qcResult.setFailedCount(failCount);
        qcResult.setVerifyCount(verifyCount);
        qcResult.setManualPassCount(manualPassCount);

        qcResultRepository.save(qcResult);

        log.debug("Recalculated counters for QCResult {}: pass={}, fail={}, verify={}, manualPass={}",
                qcResultId, passCount, failCount, verifyCount, manualPassCount);
    }
}
