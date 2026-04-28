package com.apprisal.qc.controller.api;

import com.apprisal.common.dto.DecisionSaveRequest;
import com.apprisal.common.entity.QCDecision;
import com.apprisal.common.entity.QCResult;
import com.apprisal.common.entity.QCRuleResult;
import com.apprisal.common.repository.QCResultRepository;
import com.apprisal.qc.service.VerificationService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/**
 * REST API controller for reviewer AJAX operations.
 * Supports auto-save and state persistence without page reloads.
 */
@RestController
@RequestMapping("/api/reviewer")
public class ReviewerApiController {

    private static final Logger log = LoggerFactory.getLogger(ReviewerApiController.class);

    private final VerificationService verificationService;
    private final QCResultRepository qcResultRepository;

    public ReviewerApiController(VerificationService verificationService,
                                 QCResultRepository qcResultRepository) {
        this.verificationService = verificationService;
        this.qcResultRepository  = qcResultRepository;
    }

    // ── Pending queue ──────────────────────────────────────────────────────────

    /**
     * Returns all TO_VERIFY QC results that have no final decision yet.
     * Called by the Next.js reviewer queue page at /api/qc/results/pending.
     */
    @GetMapping("/qc/results/pending")
    public ResponseEntity<List<Map<String, Object>>> getPendingQueue() {
        try {
            List<QCResult> pending = qcResultRepository.findPendingVerification();
            List<Map<String, Object>> body = pending.stream().map(r -> {
                Map<String, Object> m = new HashMap<>();
                m.put("id",             r.getId());
                m.put("qcDecision",     r.getQcDecision() != null ? r.getQcDecision().name() : null);
                m.put("finalDecision",  r.getFinalDecision() != null ? r.getFinalDecision().name() : null);
                m.put("totalRules",     r.getTotalRules());
                m.put("passedCount",    r.getPassedCount());
                m.put("failedCount",    r.getFailedCount());
                m.put("verifyCount",    r.getVerifyCount());
                m.put("manualPassCount",r.getManualPassCount());
                m.put("processingTimeMs", r.getProcessingTimeMs());
                m.put("cacheHit",       r.getCacheHit());
                m.put("processedAt",    r.getProcessedAt() != null ? r.getProcessedAt().toString() : null);
                // Embed minimal batchFile info the UI needs
                if (r.getBatchFile() != null) {
                    m.put("batchFile", Map.of(
                            "id",       r.getBatchFile().getId(),
                            "filename", r.getBatchFile().getFilename() != null ? r.getBatchFile().getFilename() : ""
                    ));
                }
                return m;
            }).toList();
            return ResponseEntity.ok(body);
        } catch (Exception e) {
            log.error("Failed to load pending queue: {}", e.getMessage(), e);
            return ResponseEntity.ok(List.of()); // return empty list, not an error
        }
    }

    // ── Decision save ──────────────────────────────────────────────────────────

    /**
     * Auto-save a single reviewer decision.
     * Called on each Accept/Reject button click for real-time persistence.
     */
    @PostMapping("/decision/save")
    public ResponseEntity<Map<String, Object>> saveDecision(@RequestBody DecisionSaveRequest request) {
        try {
            // Validate required fields
            if (request.ruleResultId() == null) {
                throw new IllegalArgumentException("ruleResultId is required");
            }
            if (request.decision() == null || request.decision().isEmpty()) {
                throw new IllegalArgumentException("decision is required");
            }

            QCRuleResult result = verificationService.saveDecision(
                    Objects.requireNonNull(request.ruleResultId()),
                    Objects.requireNonNull(request.decision()),
                    request.comment());

            Map<String, Object> response = new HashMap<>();
            response.put("success", true);
            response.put("ruleResultId", result.getId());
            response.put("ruleId", result.getRuleId());
            response.put("decision", request.decision());
            response.put("savedAt", result.getVerifiedAt().toString());

            log.info("Decision auto-saved: ruleResultId={}, decision={}",
                    request.ruleResultId(), request.decision());

            return ResponseEntity.ok(response);
        } catch (Exception e) {
            log.error("Failed to save decision: {}", e.getMessage(), e);
            Map<String, Object> error = new HashMap<>();
            error.put("success", false);
            error.put("error", e.getMessage());
            return ResponseEntity.badRequest().body(error);
        }
    }

    // ── Rule results ───────────────────────────────────────────────────────────

    /**
     * Get all rule results for a QC result (for UI rendering).
     */
    @GetMapping("/qc/{qcResultId}/rules")
    public ResponseEntity<List<Map<String, Object>>> getAllRules(@PathVariable Long qcResultId) {
        try {
            List<QCRuleResult> rules = verificationService.getAllRuleResults(qcResultId);

            List<Map<String, Object>> response = rules.stream().map(rule -> {
                Map<String, Object> ruleMap = new HashMap<>();
                ruleMap.put("id", rule.getId());
                ruleMap.put("ruleId", rule.getRuleId());
                ruleMap.put("ruleName", rule.getRuleName());
                ruleMap.put("status", rule.getStatus());
                ruleMap.put("message", rule.getMessage());
                ruleMap.put("details", rule.getDetails());
                ruleMap.put("actionItem", rule.getActionItem());
                ruleMap.put("reviewRequired", rule.getReviewRequired());
                ruleMap.put("appraisalValue", rule.getAppraisalValue());
                ruleMap.put("engagementValue", rule.getEngagementValue());
                ruleMap.put("reviewerVerified", rule.getReviewerVerified());
                ruleMap.put("reviewerComment", rule.getReviewerComment());
                return ruleMap;
            }).toList();

            return ResponseEntity.ok(response);
        } catch (Exception e) {
            log.error("Failed to get rules: {}", e.getMessage(), e);
            return ResponseEntity.badRequest().body(List.of());
        }
    }

    // ── Progress ───────────────────────────────────────────────────────────────

    /**
     * Get verification progress for a QC result.
     */
    @GetMapping("/qc/{qcResultId}/progress")
    public ResponseEntity<Map<String, Object>> getProgress(@PathVariable Long qcResultId) {
        try {
            List<QCRuleResult> allRules         = verificationService.getAllRuleResults(qcResultId);
            List<QCRuleResult> pendingItems      = verificationService.getPendingItems(qcResultId);
            List<QCRuleResult> verificationItems = verificationService.getVerificationItems(qcResultId);

            Map<String, Object> response = new HashMap<>();
            response.put("totalRules",    allRules.size());
            response.put("totalToVerify", verificationItems.size());
            response.put("pending",       pendingItems.size());
            response.put("completed",     verificationItems.size() - pendingItems.size());
            response.put("canSubmit",     pendingItems.isEmpty() && !verificationItems.isEmpty());

            return ResponseEntity.ok(response);
        } catch (Exception e) {
            log.error("Failed to get progress: {}", e.getMessage(), e);
            return ResponseEntity.badRequest().body(Map.of("error", e.getMessage()));
        }
    }
}
