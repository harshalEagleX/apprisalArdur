package com.apprisal.qc.controller.api;

import com.apprisal.common.dto.DecisionSaveRequest;
import com.apprisal.common.entity.QCResult;
import com.apprisal.common.entity.QCRuleResult;
import com.apprisal.common.entity.Role;
import com.apprisal.common.repository.QCResultRepository;
import com.apprisal.common.security.UserPrincipal;
import com.apprisal.common.realtime.RealtimeEventPublisher;
import com.apprisal.qc.service.VerificationService;
import jakarta.servlet.http.HttpServletRequest;
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
    private final RealtimeEventPublisher realtimeEventPublisher;

    public ReviewerApiController(VerificationService verificationService,
                                 QCResultRepository qcResultRepository,
                                 RealtimeEventPublisher realtimeEventPublisher) {
        this.verificationService = verificationService;
        this.qcResultRepository  = qcResultRepository;
        this.realtimeEventPublisher = realtimeEventPublisher;
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

    @PostMapping("/qc/{qcResultId}/session/start")
    public ResponseEntity<Map<String, Object>> startReviewSession(
            @PathVariable Long qcResultId,
            @RequestBody(required = false) Map<String, Object> request,
            @AuthenticationPrincipal UserPrincipal principal,
            HttpServletRequest httpRequest) {
        try {
            if (principal == null) {
                return ResponseEntity.status(401).body(Map.of("success", false, "error", "Authentication required"));
            }
            if (principal.getUser().getRole() == Role.REVIEWER) {
                verificationService.assertReviewerOwnsQcResult(qcResultId, principal.getUser().getId());
            }

            boolean acknowledge = request != null && Boolean.TRUE.equals(request.get("acknowledgeExistingLock"));
            QCResult result = verificationService.beginReviewSession(
                    qcResultId,
                    principal.getUser(),
                    acknowledge,
                    clientIp(httpRequest),
                    httpRequest.getHeader("User-Agent"));

            Map<String, Object> body = new HashMap<>();
            body.put("success", true);
            body.put("sessionToken", result.getReviewSessionToken());
            body.put("lockedBy", displayName(result.getReviewLockedBy()));
            body.put("startedAt", result.getReviewStartedAt() != null ? result.getReviewStartedAt().toString() : null);
            body.put("expiresAt", result.getReviewLockExpiresAt() != null ? result.getReviewLockExpiresAt().toString() : null);
            body.put("lockAcknowledged", Boolean.TRUE.equals(result.getReviewLockAcknowledged()));
            realtimeEventPublisher.publish("/topic/reviewer/qc/" + qcResultId + "/presence", body);
            return ResponseEntity.ok(body);
        } catch (SecurityException e) {
            return ResponseEntity.status(403).body(Map.of("success", false, "error", e.getMessage()));
        } catch (Exception e) {
            return ResponseEntity.status(409).body(Map.of("success", false, "error", e.getMessage()));
        }
    }

    @PostMapping("/qc/{qcResultId}/session/heartbeat")
    public ResponseEntity<Map<String, Object>> heartbeatReviewSession(
            @PathVariable Long qcResultId,
            @RequestBody Map<String, String> request,
            @AuthenticationPrincipal UserPrincipal principal) {
        try {
            if (principal == null) {
                return ResponseEntity.status(401).body(Map.of("success", false, "error", "Authentication required"));
            }
            if (principal.getUser().getRole() == Role.REVIEWER) {
                verificationService.assertReviewerOwnsQcResult(qcResultId, principal.getUser().getId());
            }
            String sessionToken = request != null ? request.get("sessionToken") : null;
            QCResult result = verificationService.heartbeatReviewSession(qcResultId, Objects.requireNonNull(sessionToken));
            return ResponseEntity.ok(Map.of(
                    "success", true,
                    "expiresAt", result.getReviewLockExpiresAt() != null ? result.getReviewLockExpiresAt().toString() : ""));
        } catch (Exception e) {
            return ResponseEntity.status(409).body(Map.of("success", false, "error", e.getMessage()));
        }
    }

    @PostMapping("/decision/save")
    public ResponseEntity<Map<String, Object>> saveDecision(
            @RequestBody DecisionSaveRequest request,
            @AuthenticationPrincipal UserPrincipal principal,
            HttpServletRequest httpRequest) {
        try {
            if (principal == null) {
                return ResponseEntity.status(401).body(Map.of("success", false, "error", "Authentication required"));
            }
            if (request.ruleResultId() == null) throw new IllegalArgumentException("ruleResultId is required");
            if (request.decision() == null || request.decision().isEmpty()) throw new IllegalArgumentException("decision is required");
            if (request.sessionToken() == null || request.sessionToken().isBlank()) throw new IllegalArgumentException("sessionToken is required");

            // IDOR check: REVIEWER can only save decisions for their assigned batches
            if (principal != null && principal.getUser().getRole() == Role.REVIEWER) {
                verificationService.assertReviewerOwnsRuleResult(
                        Objects.requireNonNull(request.ruleResultId()),
                        principal.getUser().getId());
            }

            QCRuleResult result = verificationService.saveDecision(
                    Objects.requireNonNull(request.ruleResultId()),
                    Objects.requireNonNull(request.decision()),
                    request.comment(),
                    Objects.requireNonNull(request.sessionToken()),
                    request.decisionLatencyMs(),
                    request.acknowledged(),
                    principal.getUser(),
                    clientIp(httpRequest),
                    httpRequest.getHeader("User-Agent"));

            Map<String, Object> response = new HashMap<>();
            response.put("success", true);
            response.put("ruleResultId", result.getId());
            response.put("ruleId", result.getRuleId());
            response.put("decision", request.decision());
            response.put("savedAt", result.getVerifiedAt().toString());
            response.put("overridePending", Boolean.TRUE.equals(result.getOverridePending()));

            Long qcResultId = result.getQcResult().getId();
            realtimeEventPublisher.publish("/topic/reviewer/qc/" + qcResultId + "/decision", response);
            realtimeEventPublisher.publish("/topic/reviewer/qc/" + qcResultId + "/progress", progressPayload(qcResultId));

            log.info("Decision saved: ruleResultId={}, decision={}", request.ruleResultId(), request.decision());
            return ResponseEntity.ok(response);
        } catch (SecurityException e) {
            return ResponseEntity.status(403).body(Map.of("success", false, "error", e.getMessage()));
        } catch (Exception e) {
            log.error("Failed to save decision: {}", e.getMessage(), e);
            return ResponseEntity.badRequest().body(Map.of("success", false, "error", e.getMessage()));
        }
    }

    @PostMapping("/qc/{qcResultId}/submit")
    public ResponseEntity<Map<String, Object>> submitSavedReview(
            @PathVariable Long qcResultId,
            @RequestBody(required = false) Map<String, String> request,
            @AuthenticationPrincipal UserPrincipal principal) {
        try {
            if (principal == null) {
                return ResponseEntity.status(401).body(Map.of("success", false, "error", "Authentication required"));
            }
            if (principal.getUser().getRole() == Role.REVIEWER) {
                verificationService.assertReviewerOwnsQcResult(qcResultId, principal.getUser().getId());
            }

            String notes = request != null ? request.get("notes") : null;
            String sessionToken = request != null ? request.get("sessionToken") : null;
            if (sessionToken == null || sessionToken.isBlank()) {
                return ResponseEntity.badRequest().body(Map.of("success", false, "error", "sessionToken is required"));
            }
            verificationService.heartbeatReviewSession(qcResultId, sessionToken);
            QCResult result = verificationService.completeSavedVerification(qcResultId, principal.getUser(), notes);

            Map<String, Object> response = new HashMap<>();
            response.put("success", true);
            response.put("qcResultId", result.getId());
            response.put("finalDecision", result.getFinalDecision() != null ? result.getFinalDecision().name() : null);

            realtimeEventPublisher.publish("/topic/reviewer/qc/" + qcResultId + "/progress", progressPayload(qcResultId));
            realtimeEventPublisher.publish("/topic/reviewer/qc/" + qcResultId + "/decision", response);
            return ResponseEntity.ok(response);
        } catch (SecurityException e) {
            return ResponseEntity.status(403).body(Map.of("success", false, "error", e.getMessage()));
        } catch (Exception e) {
            log.error("Failed to submit review: {}", e.getMessage(), e);
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
                ruleMap.put("status",          normalizeStatus(rule.getStatus()));
                ruleMap.put("message",         rule.getMessage());
                ruleMap.put("details",         rule.getDetails());
                ruleMap.put("actionItem",      rule.getActionItem());
                ruleMap.put("reviewRequired",  Boolean.TRUE.equals(rule.getReviewRequired()) || needsReviewerAction(rule.getStatus()));
                ruleMap.put("appraisalValue",  rule.getAppraisalValue());
                ruleMap.put("engagementValue", rule.getEngagementValue());
                ruleMap.put("confidence",      rule.getConfidenceScore());
                ruleMap.put("extractedValue",  rule.getExtractedValue());
                ruleMap.put("expectedValue",   rule.getExpectedValue());
                ruleMap.put("verifyQuestion",  rule.getVerifyQuestion());
                ruleMap.put("rejectionText",   rule.getRejectionText());
                ruleMap.put("evidence",        rule.getEvidence());
                ruleMap.put("reviewerVerified",rule.getReviewerVerified());
                ruleMap.put("reviewerComment", rule.getReviewerComment());
                ruleMap.put("firstPresentedAt", rule.getFirstPresentedAt() != null ? rule.getFirstPresentedAt().toString() : null);
                ruleMap.put("decisionLatencyMs", rule.getDecisionLatencyMs());
                ruleMap.put("acknowledgedReferences", rule.getAcknowledgedReferences());
                ruleMap.put("overridePending", Boolean.TRUE.equals(rule.getOverridePending()));
                ruleMap.put("overrideRequestedBy", rule.getOverrideRequestedBy() != null ? displayName(rule.getOverrideRequestedBy()) : null);
                ruleMap.put("overrideRequestedAt", rule.getOverrideRequestedAt() != null ? rule.getOverrideRequestedAt().toString() : null);
                ruleMap.put("severity",        rule.getSeverity() != null ? rule.getSeverity() : "STANDARD");
                ruleMap.put("pdfPage",         rule.getPdfPage());
                ruleMap.put("bboxX",           rule.getBboxX());
                ruleMap.put("bboxY",           rule.getBboxY());
                ruleMap.put("bboxW",           rule.getBboxW());
                ruleMap.put("bboxH",           rule.getBboxH());
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

            return ResponseEntity.ok(progressPayload(qcResultId));
        } catch (SecurityException e) {
            return ResponseEntity.status(403).body(Map.of("error", e.getMessage()));
        } catch (Exception e) {
            log.error("Failed to get progress: {}", e.getMessage(), e);
            return ResponseEntity.badRequest().body(Map.of("error", e.getMessage()));
        }
    }

    private Map<String, Object> progressPayload(Long qcResultId) {
        List<QCRuleResult> allRules = verificationService.getAllRuleResults(qcResultId);
        List<QCRuleResult> pendingItems = verificationService.getPendingItems(qcResultId);
        List<QCRuleResult> verificationItems = verificationService.getVerificationItems(qcResultId);

        Map<String, Object> response = new HashMap<>();
        response.put("qcResultId", qcResultId);
        response.put("totalRules", allRules.size());
        response.put("totalToVerify", verificationItems.size());
        response.put("pending", pendingItems.size());
        response.put("completed", verificationItems.size() - pendingItems.size());
        response.put("canSubmit", pendingItems.isEmpty() && !verificationItems.isEmpty());
        return response;
    }

    private String normalizeStatus(String status) {
        if (status == null || status.isBlank()) {
            return "verify";
        }
        return status.trim().toLowerCase();
    }

    private boolean needsReviewerAction(String status) {
        String normalized = normalizeStatus(status);
        return "verify".equals(normalized) || "fail".equals(normalized) || "system_error".equals(normalized);
    }

    private String clientIp(HttpServletRequest request) {
        String forwarded = request.getHeader("X-Forwarded-For");
        if (forwarded != null && !forwarded.isBlank()) {
            return forwarded.split(",")[0].trim();
        }
        return request.getRemoteAddr();
    }

    private String displayName(com.apprisal.common.entity.User user) {
        if (user == null) return null;
        if (user.getFullName() != null && !user.getFullName().isBlank()) return user.getFullName();
        return user.getUsername();
    }
}
