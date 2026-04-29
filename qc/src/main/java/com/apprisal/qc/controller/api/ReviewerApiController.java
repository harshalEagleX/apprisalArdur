package com.apprisal.qc.controller.api;

import com.apprisal.common.dto.DecisionSaveRequest;
import com.apprisal.common.entity.QCResult;
import com.apprisal.common.entity.QCRuleResult;
import com.apprisal.common.entity.Role;
import com.apprisal.common.repository.QCResultRepository;
import com.apprisal.common.security.UserPrincipal;
import com.apprisal.qc.service.VerificationService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/**
 * REST API for reviewer AJAX operations (auto-save, queue, progress).
 *
 * ADMIN sees all pending results.
 * REVIEWER sees only results for batches assigned to them (IDOR protection).
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

    @GetMapping("/qc/results/pending")
    public ResponseEntity<List<Map<String, Object>>> getPendingQueue(
            @AuthenticationPrincipal UserPrincipal principal) {
        try {
            List<QCResult> pending;

            if (principal != null && principal.getUser().getRole() == Role.REVIEWER) {
                // REVIEWER: only see batches assigned to them
                pending = qcResultRepository.findPendingVerificationForReviewer(principal.getUser().getId());
            } else {
                // ADMIN: see all pending
                pending = qcResultRepository.findPendingVerification();
            }

            List<Map<String, Object>> body = pending.stream().map(r -> {
                Map<String, Object> m = new HashMap<>();
                m.put("id",              r.getId());
                m.put("qcDecision",      r.getQcDecision() != null ? r.getQcDecision().name() : null);
                m.put("finalDecision",   r.getFinalDecision() != null ? r.getFinalDecision().name() : null);
                m.put("totalRules",      r.getTotalRules());
                m.put("passedCount",     r.getPassedCount());
                m.put("failedCount",     r.getFailedCount());
                m.put("verifyCount",     r.getVerifyCount());
                m.put("manualPassCount", r.getManualPassCount());
                m.put("processingTimeMs", r.getProcessingTimeMs());
                m.put("cacheHit",        r.getCacheHit());
                m.put("processedAt",     r.getProcessedAt() != null ? r.getProcessedAt().toString() : null);
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
            return ResponseEntity.ok(List.of());
        }
    }

    // ── Decision save (IDOR-protected) ─────────────────────────────────────────

    @PostMapping("/decision/save")
    public ResponseEntity<Map<String, Object>> saveDecision(
            @RequestBody DecisionSaveRequest request,
            @AuthenticationPrincipal UserPrincipal principal) {
        try {
            if (request.ruleResultId() == null) throw new IllegalArgumentException("ruleResultId is required");
            if (request.decision() == null || request.decision().isEmpty()) throw new IllegalArgumentException("decision is required");

            // IDOR check: REVIEWER can only save decisions for their assigned batches
            if (principal != null && principal.getUser().getRole() == Role.REVIEWER) {
                verificationService.assertReviewerOwnsRuleResult(
                        Objects.requireNonNull(request.ruleResultId()),
                        principal.getUser().getId());
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

            log.info("Decision saved: ruleResultId={}, decision={}", request.ruleResultId(), request.decision());
            return ResponseEntity.ok(response);
        } catch (SecurityException e) {
            return ResponseEntity.status(403).body(Map.of("success", false, "error", e.getMessage()));
        } catch (Exception e) {
            log.error("Failed to save decision: {}", e.getMessage(), e);
            return ResponseEntity.badRequest().body(Map.of("success", false, "error", e.getMessage()));
        }
    }

    // ── Rule results ───────────────────────────────────────────────────────────

    @GetMapping("/qc/{qcResultId}/rules")
    public ResponseEntity<List<Map<String, Object>>> getAllRules(
            @PathVariable Long qcResultId,
            @AuthenticationPrincipal UserPrincipal principal) {
        try {
            // IDOR check for REVIEWER
            if (principal != null && principal.getUser().getRole() == Role.REVIEWER) {
                verificationService.assertReviewerOwnsQcResult(qcResultId, principal.getUser().getId());
            }

            List<QCRuleResult> rules = verificationService.getAllRuleResults(qcResultId);
            List<Map<String, Object>> response = rules.stream().map(rule -> {
                Map<String, Object> ruleMap = new HashMap<>();
                ruleMap.put("id",              rule.getId());
                ruleMap.put("ruleId",          rule.getRuleId());
                ruleMap.put("ruleName",        rule.getRuleName());
                ruleMap.put("status",          rule.getStatus());
                ruleMap.put("message",         rule.getMessage());
                ruleMap.put("details",         rule.getDetails());
                ruleMap.put("actionItem",      rule.getActionItem());
                ruleMap.put("reviewRequired",  rule.getReviewRequired());
                ruleMap.put("appraisalValue",  rule.getAppraisalValue());
                ruleMap.put("engagementValue", rule.getEngagementValue());
                ruleMap.put("reviewerVerified",rule.getReviewerVerified());
                ruleMap.put("reviewerComment", rule.getReviewerComment());
                ruleMap.put("severity",        rule.getSeverity() != null ? rule.getSeverity() : "STANDARD");
                return ruleMap;
            }).toList();

            return ResponseEntity.ok(response);
        } catch (SecurityException e) {
            return ResponseEntity.status(403).body(List.of());
        } catch (Exception e) {
            log.error("Failed to get rules for qcResultId={}: {}", qcResultId, e.getMessage(), e);
            return ResponseEntity.badRequest().body(List.of());
        }
    }

    // ── Progress ───────────────────────────────────────────────────────────────

    @GetMapping("/qc/{qcResultId}/progress")
    public ResponseEntity<Map<String, Object>> getProgress(
            @PathVariable Long qcResultId,
            @AuthenticationPrincipal UserPrincipal principal) {
        try {
            if (principal != null && principal.getUser().getRole() == Role.REVIEWER) {
                verificationService.assertReviewerOwnsQcResult(qcResultId, principal.getUser().getId());
            }

            List<QCRuleResult> allRules          = verificationService.getAllRuleResults(qcResultId);
            List<QCRuleResult> pendingItems       = verificationService.getPendingItems(qcResultId);
            List<QCRuleResult> verificationItems  = verificationService.getVerificationItems(qcResultId);

            Map<String, Object> response = new HashMap<>();
            response.put("totalRules",    allRules.size());
            response.put("totalToVerify", verificationItems.size());
            response.put("pending",       pendingItems.size());
            response.put("completed",     verificationItems.size() - pendingItems.size());
            response.put("canSubmit",     pendingItems.isEmpty() && !verificationItems.isEmpty());

            return ResponseEntity.ok(response);
        } catch (SecurityException e) {
            return ResponseEntity.status(403).body(Map.of("error", e.getMessage()));
        } catch (Exception e) {
            log.error("Failed to get progress: {}", e.getMessage(), e);
            return ResponseEntity.badRequest().body(Map.of("error", e.getMessage()));
        }
    }
}
