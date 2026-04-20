package com.apprisal.controller.api;

import com.apprisal.dto.DecisionSaveRequest;
import com.apprisal.entity.QCRuleResult;
import com.apprisal.service.VerificationService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;

/**
 * REST API controller for reviewer AJAX operations.
 * Supports auto-save and state persistence without page reloads.
 */
@RestController
@RequestMapping("/api/reviewer")
@Tag(name = "Reviewer API", description = "Operations for reviewers to save and load QC verification decisions")
public class ReviewerApiController {

    private static final Logger log = LoggerFactory.getLogger(ReviewerApiController.class);

    private final VerificationService verificationService;

    public ReviewerApiController(VerificationService verificationService) {
        this.verificationService = verificationService;
    }

    /**
     * Auto-save a single reviewer decision.
     * Called on each Accept/Reject button click for real-time persistence.
     */
    @Operation(summary = "Auto-save decision", description = "Updates and persists a single verified decision dynamically via AJAX")
    @PostMapping("/decision/save")
    public ResponseEntity<Map<String, Object>> saveDecision(@RequestBody DecisionSaveRequest request) {
        try {
            // Validate required fields
            if (request.getRuleResultId() == null) {
                throw new IllegalArgumentException("ruleResultId is required");
            }
            if (request.getDecision() == null || request.getDecision().isEmpty()) {
                throw new IllegalArgumentException("decision is required");
            }

            QCRuleResult result = verificationService.saveDecision(
                    Objects.requireNonNull(request.getRuleResultId()),
                    Objects.requireNonNull(request.getDecision()),
                    request.getComment());

            Map<String, Object> response = new HashMap<>();
            response.put("success", true);
            response.put("ruleResultId", result.getId());
            response.put("ruleId", result.getRuleId());
            response.put("decision", request.getDecision());
            response.put("savedAt", result.getVerifiedAt().toString());

            log.info("Decision auto-saved: ruleResultId={}, decision={}",
                    request.getRuleResultId(), request.getDecision());

            return ResponseEntity.ok(response);
        } catch (Exception e) {
            log.error("Failed to save decision: {}", e.getMessage(), e);
            Map<String, Object> error = new HashMap<>();
            error.put("success", false);
            error.put("error", e.getMessage());
            return ResponseEntity.badRequest().body(error);
        }
    }

    /**
     * Get all rule results for a QC result (for UI rendering).
     */
    @Operation(summary = "Get all rule outcomes", description = "Fetches the full suite of rules for an individual file's verification progress")
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

    /**
     * Get verification progress for a QC result.
     */
    @Operation(summary = "Get verification stats", description = "Provides metrics on the reviewer's progress: total verifications pending vs completed")
    @GetMapping("/qc/{qcResultId}/progress")
    public ResponseEntity<Map<String, Object>> getProgress(@PathVariable Long qcResultId) {
        try {
            List<QCRuleResult> allRules = verificationService.getAllRuleResults(qcResultId);
            List<QCRuleResult> pendingItems = verificationService.getPendingItems(qcResultId);
            List<QCRuleResult> verificationItems = verificationService.getVerificationItems(qcResultId);

            Map<String, Object> response = new HashMap<>();
            response.put("totalRules", allRules.size());
            response.put("totalToVerify", verificationItems.size());
            response.put("pending", pendingItems.size());
            response.put("completed", verificationItems.size() - pendingItems.size());
            response.put("canSubmit", pendingItems.isEmpty() && !verificationItems.isEmpty());

            return ResponseEntity.ok(response);
        } catch (Exception e) {
            log.error("Failed to get progress: {}", e.getMessage(), e);
            return ResponseEntity.badRequest().body(Map.of("error", e.getMessage()));
        }
    }
}
