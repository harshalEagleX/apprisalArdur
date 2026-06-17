package com.apprisal.qc.controller.api;

import com.apprisal.common.dto.DecisionSaveRequest;
import com.apprisal.common.entity.QCResult;
import com.apprisal.common.entity.QCRuleResult;
import com.apprisal.common.entity.Role;
import com.apprisal.common.repository.QCResultRepository;
import com.apprisal.common.repository.QCRuleResultRepository;
import com.apprisal.common.repository.AuditLogRepository;
import com.apprisal.common.security.UserPrincipal;
import com.apprisal.common.realtime.RealtimeEventPublisher;
import com.apprisal.common.service.AuditLogService;
import com.apprisal.common.entity.AuditLog;
import com.apprisal.qc.service.VerificationService;
import tools.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletRequest;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.orm.ObjectOptimisticLockingFailureException;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

import java.util.ArrayList;
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
    private final QCRuleResultRepository qcRuleResultRepository;
    private final RealtimeEventPublisher realtimeEventPublisher;
    private final AuditLogService auditLogService;
    private final AuditLogRepository auditLogRepository;
    private final ObjectMapper objectMapper;

    public ReviewerApiController(VerificationService verificationService,
                                 QCResultRepository qcResultRepository,
                                 QCRuleResultRepository qcRuleResultRepository,
                                 RealtimeEventPublisher realtimeEventPublisher,
                                 AuditLogService auditLogService,
                                 AuditLogRepository auditLogRepository,
                                 ObjectMapper objectMapper) {
        this.verificationService = verificationService;
        this.qcResultRepository  = qcResultRepository;
        this.qcRuleResultRepository = qcRuleResultRepository;
        this.realtimeEventPublisher = realtimeEventPublisher;
        this.auditLogService = auditLogService;
        this.auditLogRepository = auditLogRepository;
        this.objectMapper = objectMapper;
    }

    // ── Review config (policy flags the UI must mirror) ───────────────────────

    /** Policy flags the reviewer UI mirrors so its messaging/affordances match the backend. */
    @GetMapping("/config")
    public ResponseEntity<Map<String, Object>> getReviewConfig() {
        return ResponseEntity.ok(Map.of(
            "requireSecondApprovalForOverride", verificationService.isSecondApprovalRequiredForOverride()
        ));
    }

    // ── Submitted queue (recently completed by this reviewer) ─────────────────

    @GetMapping("/qc/results/submitted")
    public ResponseEntity<List<Map<String, Object>>> getSubmittedQueue(
            @AuthenticationPrincipal UserPrincipal principal) {
        try {
            List<QCResult> submitted;
            if (principal != null && principal.getUser().getRole() == Role.REVIEWER) {
                submitted = qcResultRepository.findRecentlyReviewedForReviewer(principal.getUser().getId());
            } else {
                submitted = qcResultRepository.findRecentlyReviewed();
            }

            List<Map<String, Object>> body = submitted.stream().map(r -> {
                Map<String, Object> m = new HashMap<>();
                m.put("id",            r.getId());
                m.put("finalDecision", r.getFinalDecision() != null ? r.getFinalDecision().name() : null);
                m.put("failedCount",   r.getFailedCount());
                m.put("passedCount",   r.getPassedCount());
                m.put("totalRules",    r.getTotalRules());
                m.put("reviewedAt",    r.getReviewedAt() != null ? r.getReviewedAt().toString() : null);
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
            log.error("Failed to load submitted queue: {}", e.getMessage(), e);
            return ResponseEntity.ok(List.of());
        }
    }

    // ── Pending queue ──────────────────────────────────────────────────────────

    /**
     * Paginated pending review queue.
     *
     * Returns a page envelope so the frontend can render a paginator and the
     * server never loads the entire queue into memory (OOM prevention at scale).
     * Default page size is 50 — large enough for a productive session, small
     * enough to keep response times fast.
     */
    @GetMapping("/qc/results/pending")
    public ResponseEntity<Map<String, Object>> getPendingQueue(
            @AuthenticationPrincipal UserPrincipal principal,
            @RequestParam(defaultValue = "0")  int page,
            @RequestParam(defaultValue = "50") int size) {
        try {
            // Cap page size to 200 so a crafted request can't trigger an OOM.
            int safeSize = Math.min(Math.max(1, size), 200);
            PageRequest pageable = PageRequest.of(
                    Math.max(0, page), safeSize,
                    Sort.by(Sort.Direction.DESC, "failedCount")
                        .and(Sort.by(Sort.Direction.DESC, "verifyCount"))
                        .and(Sort.by(Sort.Direction.ASC,  "updatedAt")));

            Page<QCResult> pendingPage;
            if (principal != null && principal.getUser().getRole() == Role.REVIEWER) {
                pendingPage = qcResultRepository.findPendingVerificationForReviewerPaged(
                        principal.getUser().getId(), pageable);
            } else {
                pendingPage = qcResultRepository.findPendingVerificationPaged(pageable);
            }

            List<Map<String, Object>> content = pendingPage.getContent().stream().map(r -> {
                Map<String, Object> m = new HashMap<>();
                m.put("id",               r.getId());
                m.put("qcDecision",       r.getQcDecision() != null ? r.getQcDecision().name() : null);
                m.put("finalDecision",    r.getFinalDecision() != null ? r.getFinalDecision().name() : null);
                m.put("totalRules",       r.getTotalRules());
                m.put("passedCount",      r.getPassedCount());
                m.put("failedCount",      r.getFailedCount());
                m.put("verifyCount",      r.getVerifyCount());
                m.put("manualPassCount",  r.getManualPassCount());
                m.put("processingTimeMs", r.getProcessingTimeMs());
                m.put("cacheHit",         r.getCacheHit());
                m.put("processedAt",      r.getProcessedAt() != null ? r.getProcessedAt().toString() : null);
                if (r.getBatchFile() != null) {
                    m.put("batchFile", Map.of(
                            "id",       r.getBatchFile().getId(),
                            "filename", r.getBatchFile().getFilename() != null ? r.getBatchFile().getFilename() : ""
                    ));
                }
                return m;
            }).toList();

            return ResponseEntity.ok(Map.of(
                    "content",       content,
                    "page",          pendingPage.getNumber(),
                    "size",          pendingPage.getSize(),
                    "totalElements", pendingPage.getTotalElements(),
                    "totalPages",    pendingPage.getTotalPages(),
                    "first",         pendingPage.isFirst(),
                    "last",          pendingPage.isLast()
            ));
        } catch (Exception e) {
            log.error("Failed to load pending queue: {}", e.getMessage(), e);
            return ResponseEntity.ok(Map.of("content", List.of(), "totalElements", 0L,
                    "totalPages", 0, "page", 0, "size", size));
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
            body.put("priorActionCount", verificationService.priorActionCount(qcResultId));
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
                return ResponseEntity.status(401).body(errorBody("AUTH_REQUIRED", "Authentication required"));
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
            response.put("status", normalizeStatus(result.getStatus()));
            response.put("reviewerVerified", result.getReviewerVerified());
            response.put("overridePending", Boolean.TRUE.equals(result.getOverridePending()));
            response.put("reviewerComment", result.getReviewerComment());

            Long qcResultId = result.getQcResult().getId();
            realtimeEventPublisher.publish("/topic/reviewer/qc/" + qcResultId + "/decision", response);

            log.info("Decision saved: ruleResultId={}, decision={}", request.ruleResultId(), request.decision());
            return ResponseEntity.ok(response);
        } catch (SecurityException e) {
            return ResponseEntity.status(403).body(errorBody("ACCESS_DENIED", e.getMessage()));
        } catch (ObjectOptimisticLockingFailureException e) {
            log.warn("Concurrent decision save detected for ruleResultId={}: {}", request.ruleResultId(), e.getMessage());
            return ResponseEntity.status(409).body(errorBody(
                    "DECISION_ALREADY_UPDATED",
                    "This review item was updated a moment ago. The latest saved decision is already on the server. Refresh the rule list if the screen still looks outdated."
            ));
        } catch (IllegalArgumentException e) {
            return ResponseEntity.badRequest().body(errorBody("INVALID_REQUEST", e.getMessage()));
        } catch (IllegalStateException e) {
            return ResponseEntity.status(409).body(errorBody("REVIEW_STATE_CONFLICT", e.getMessage()));
        } catch (Exception e) {
            log.error("Failed to save decision: {}", e.getMessage(), e);
            return ResponseEntity.status(500).body(errorBody(
                    "DECISION_SAVE_FAILED",
                    "We couldn't save that review decision right now. Please try again. If it keeps happening, refresh the page to load the latest review state."
            ));
        }
    }

    @PostMapping("/decision/focus")
    public ResponseEntity<Map<String, Object>> recordRuleFocus(
            @RequestBody Map<String, Object> request,
            @AuthenticationPrincipal UserPrincipal principal) {
        try {
            if (principal == null) {
                return ResponseEntity.status(401).body(errorBody("AUTH_REQUIRED", "Authentication required"));
            }
            Object rawRuleResultId = request != null ? request.get("ruleResultId") : null;
            Long ruleResultId = rawRuleResultId instanceof Number n ? n.longValue()
                    : rawRuleResultId != null ? Long.valueOf(rawRuleResultId.toString()) : null;
            String sessionToken = request != null && request.get("sessionToken") != null
                    ? request.get("sessionToken").toString()
                    : null;
            if (ruleResultId == null) throw new IllegalArgumentException("ruleResultId is required");
            if (sessionToken == null || sessionToken.isBlank()) throw new IllegalArgumentException("sessionToken is required");

            if (principal.getUser().getRole() == Role.REVIEWER) {
                verificationService.assertReviewerOwnsRuleResult(ruleResultId, principal.getUser().getId());
            }
            verificationService.recordRuleFocused(ruleResultId, sessionToken, principal.getUser());
            return ResponseEntity.ok(Map.of("success", true));
        } catch (SecurityException e) {
            return ResponseEntity.status(403).body(errorBody("ACCESS_DENIED", e.getMessage()));
        } catch (IllegalArgumentException e) {
            return ResponseEntity.badRequest().body(errorBody("INVALID_REQUEST", e.getMessage()));
        } catch (Exception e) {
            log.debug("Rule focus event was not recorded: {}", e.getMessage());
            return ResponseEntity.status(409).body(errorBody("REVIEW_STATE_CONFLICT", e.getMessage()));
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
                ruleMap.put("section",         rule.getSection() != null && !rule.getSection().isBlank()
                                                   ? rule.getSection()
                                                   : sectionForRule(rule.getRuleId()));
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
                ruleMap.put("evidence",        parseEvidenceJson(rule.getEvidence()));
                ruleMap.put("help",            ruleHelp(rule.getRuleId(), rule.getRuleName()));
                ruleMap.put("reviewerVerified",rule.getReviewerVerified());
                ruleMap.put("reviewerComment", rule.getReviewerComment());
                ruleMap.put("firstPresentedAt", rule.getFirstPresentedAt() != null ? rule.getFirstPresentedAt().toString() : null);
                ruleMap.put("decisionLatencyMs", rule.getDecisionLatencyMs());
                ruleMap.put("acknowledgedReferences", rule.getAcknowledgedReferences());
                ruleMap.put("overridePending", Boolean.TRUE.equals(rule.getOverridePending()));
                ruleMap.put("overrideRequestedBy", rule.getOverrideRequestedBy() != null ? displayName(rule.getOverrideRequestedBy()) : null);
                ruleMap.put("overrideRequestedAt", rule.getOverrideRequestedAt() != null ? rule.getOverrideRequestedAt().toString() : null);
                ruleMap.put("severity",        rule.getSeverity() != null ? rule.getSeverity() : "STANDARD");
                ruleMap.put("verifiedAt",      rule.getVerifiedAt() != null ? rule.getVerifiedAt().toString() : null);
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

    /**
     * Deserialize the stored evidence JSON into a real list so the API emits
     * structured evidence (a list of document-tagged objects) rather than a
     * stringified blob the client must re-parse. Tolerates legacy rows that
     * stored a list of plain strings, and returns an empty list on any problem.
     */
    private Object parseEvidenceJson(String json) {
        if (json == null || json.isBlank()) {
            return List.of();
        }
        try {
            return objectMapper.readValue(json, List.class);
        } catch (Exception e) {
            log.warn("Could not parse rule evidence JSON; returning empty list: {}", e.getMessage());
            return List.of();
        }
    }

    // ── Submitted result summary ───────────────────────────────────────────────

    @GetMapping("/qc/{qcResultId}/result")
    public ResponseEntity<Map<String, Object>> getSubmittedResult(
            @PathVariable Long qcResultId,
            @AuthenticationPrincipal UserPrincipal principal) {
        try {
            if (principal != null && principal.getUser().getRole() == Role.REVIEWER) {
                verificationService.assertReviewerOwnsQcResult(qcResultId, principal.getUser().getId());
            }
            QCResult result = verificationService.getForVerification(qcResultId);
            Map<String, Object> body = new HashMap<>();
            body.put("id", result.getId());
            body.put("finalDecision", result.getFinalDecision() != null ? result.getFinalDecision().name() : null);
            body.put("reviewedAt", result.getReviewedAt() != null ? result.getReviewedAt().toString() : null);
            body.put("reviewerNotes", result.getReviewerNotes());
            return ResponseEntity.ok(body);
        } catch (SecurityException e) {
            return ResponseEntity.status(403).body(Map.of("error", e.getMessage()));
        } catch (Exception e) {
            return ResponseEntity.badRequest().body(Map.of("error", e.getMessage()));
        }
    }

    // ── Re-review request ──────────────────────────────────────────────────────

    @PostMapping("/qc/{qcResultId}/request-re-review")
    public ResponseEntity<Map<String, Object>> requestReReview(
            @PathVariable Long qcResultId,
            @RequestBody(required = false) Map<String, String> request,
            @AuthenticationPrincipal UserPrincipal principal,
            HttpServletRequest httpRequest) {
        try {
            if (principal == null) {
                return ResponseEntity.status(401).body(Map.of("success", false, "error", "Authentication required"));
            }
            if (principal.getUser().getRole() == Role.REVIEWER) {
                verificationService.assertReviewerOwnsQcResult(qcResultId, principal.getUser().getId());
            }
            String reason = request != null ? request.getOrDefault("reason", "") : "";
            if (reason.isBlank()) {
                return ResponseEntity.badRequest().body(Map.of("success", false, "error", "Re-review reason is required"));
            }

            auditLogService.log(principal.getUser(), "RE_REVIEW_REQUESTED", "QCResult", qcResultId,
                    "reason=" + reason, clientIp(httpRequest), httpRequest.getHeader("User-Agent"));

            // Notify admin via realtime broadcast
            Map<String, Object> event = new HashMap<>();
            event.put("type", "RE_REVIEW_REQUESTED");
            event.put("qcResultId", qcResultId);
            event.put("requestedBy", displayName(principal.getUser()));
            event.put("reason", reason);
            realtimeEventPublisher.publish("/topic/admin/notifications", event);

            log.info("Re-review requested for QCResult {} by {}: {}", qcResultId, principal.getUser().getUsername(), reason);
            return ResponseEntity.ok(Map.of("success", true, "message", "Re-review request submitted. Admin will be notified."));
        } catch (SecurityException e) {
            return ResponseEntity.status(403).body(Map.of("success", false, "error", e.getMessage()));
        } catch (Exception e) {
            log.error("Failed to request re-review: {}", e.getMessage(), e);
            return ResponseEntity.status(500).body(Map.of("success", false, "error", "Re-review request failed"));
        }
    }

    // ── Audit log for graph (ADMIN sees all, REVIEWER sees own) ───────────────

    @GetMapping("/qc/{qcResultId}/audit")
    public ResponseEntity<List<Map<String, Object>>> getAuditLog(
            @PathVariable Long qcResultId,
            @AuthenticationPrincipal UserPrincipal principal) {
        try {
            if (principal != null && principal.getUser().getRole() == Role.REVIEWER) {
                verificationService.assertReviewerOwnsQcResult(qcResultId, principal.getUser().getId());
            }
            List<AuditLog> logs = auditLogRepository.findByEntityTypeAndEntityId("QCResult", qcResultId);
            List<Map<String, Object>> body = new ArrayList<>();
            for (AuditLog entry : logs) {
                Map<String, Object> row = new HashMap<>();
                row.put("id", entry.getId());
                row.put("action", entry.getAction());
                row.put("entityType", entry.getEntityType());
                row.put("entityId", entry.getEntityId());
                row.put("details", entry.getDetails());
                row.put("createdAt", entry.getCreatedAt() != null ? entry.getCreatedAt().toString() : null);
                if (entry.getUser() != null) {
                    row.put("user", Map.of("id", entry.getUser().getId(), "username", entry.getUser().getUsername()));
                }
                body.add(row);
            }
            return ResponseEntity.ok(body);
        } catch (SecurityException e) {
            return ResponseEntity.status(403).body(List.of());
        } catch (Exception e) {
            return ResponseEntity.ok(List.of());
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
        java.util.List<Object[]> rows = qcRuleResultRepository.progressCountsForQcResult(qcResultId);
        Object[] row = rows != null && !rows.isEmpty() && rows.get(0) != null
                ? rows.get(0)
                : new Object[] {0L, 0L, 0L};
        long totalRules = numberAt(row, 0);
        long totalToVerify = numberAt(row, 1);
        long pending = numberAt(row, 2);

        Map<String, Object> response = new HashMap<>();
        response.put("qcResultId", qcResultId);
        response.put("totalRules", totalRules);
        response.put("totalToVerify", totalToVerify);
        response.put("pending", pending);
        response.put("completed", totalToVerify - pending);
        response.put("canSubmit", pending == 0 && totalToVerify > 0);
        return response;
    }

    private long numberAt(Object[] row, int index) {
        if (row == null || row.length <= index || row[index] == null) {
            return 0L;
        }
        return ((Number) row[index]).longValue();
    }

    private String normalizeStatus(String status) {
        if (status == null || status.isBlank()) {
            return "verify";
        }
        return status.trim().toLowerCase();
    }

    private boolean needsReviewerAction(String status) {
        String normalized = normalizeStatus(status);
        return "fail".equals(normalized)
                || "verify".equals(normalized)
                || "review".equals(normalized)
                || "extraction_failed".equals(normalized)
                || "ocr_low_confidence".equals(normalized)
                || "system_error".equals(normalized)
                || "source_missing".equals(normalized)
                || "cross_doc_mismatch".equals(normalized);
    }

    private Map<String, Object> errorBody(String code, String message) {
        Map<String, Object> response = new HashMap<>();
        response.put("success", false);
        response.put("error", code);
        response.put("message", message);
        return response;
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

    /** Group rules in the reviewer UI by report section, derived from the rule id
     * prefix (S-1 -> SUBJECT, SCA-5 -> SALES_COMPARISON, FHA-2 -> FHA, ...). */
    private String sectionForRule(String ruleId) {
        if (ruleId == null) return "OTHER";
        String id = ruleId.toUpperCase();
        if (id.startsWith("SCA")) return "SALES_COMPARISON";
        if (id.startsWith("SIG")) return "SIGNATURE";
        if (id.startsWith("ST")) return "SITE";
        if (id.startsWith("FHA")) return "FHA";
        if (id.startsWith("USDA")) return "USDA";
        if (id.startsWith("ADD")) return "ADDENDUM";
        if (id.startsWith("RECON")) return "RECONCILIATION";
        if (id.startsWith("PH")) return "PHOTOS";
        if (id.startsWith("CA")) return "COST_APPROACH";
        if (id.startsWith("DOC")) return "DOCUMENTS";
        if (id.startsWith("M-")) return "MAPS";
        if (id.startsWith("SK")) return "SKETCH";
        char c = id.charAt(0);
        switch (c) {
            case 'S': return "SUBJECT";
            case 'C': return "CONTRACT";
            case 'N': return "NEIGHBORHOOD";
            case 'I': return "IMPROVEMENTS";
            case 'R': return "RECONCILIATION";
            case 'G': return "GLOBAL";
            default:  return "OTHER";
        }
    }

    private Map<String, Object> ruleHelp(String ruleId, String ruleName) {
        Map<String, Object> exact = exactRuleHelp(ruleId);
        if (exact != null) {
            return exact;
        }

        String prefix = ruleId == null ? "" : ruleId.split("-")[0];
        Map<String, Object> sectionHelp = switch (prefix) {
            case "S" -> Map.of(
                    "summary", "Subject section checks compare the appraisal's subject property facts against the order and UAD requirements.",
                    "terms", Map.of("PUD", "Planned Unit Development", "HOA", "Homeowners association dues", "APN", "Assessor parcel number"),
                    "example", "Address, borrower, ownership, occupancy, PUD/HOA, and property-rights fields should match the supporting documents.");
            case "C" -> Map.of(
                    "summary", "Contract checks verify purchase/refinance treatment, final signature date, price, concessions, and personal property.",
                    "terms", Map.of("fully executed", "signed by all required parties", "concession", "seller or financing assistance affecting the transaction"),
                    "example", "For refinance assignments, contract fields should generally be blank/default.");
            case "N" -> Map.of(
                    "summary", "Neighborhood checks verify market trend, boundaries, price range, land use, and commentary specificity.",
                    "terms", Map.of("1004MC", "Market Conditions Addendum", "DOM", "days on market"),
                    "example", "If values are declining or increasing, time adjustments should be supported or explained.");
            case "SCA" -> Map.of(
                    "summary", "Sales comparison checks validate comparable counts, UAD formatting, dates, prices, adjustments, and data sources.",
                    "terms", Map.of("comp", "comparable sale/listing", "DOM", "days on market", "UAD", "Uniform Appraisal Dataset"),
                    "example", "Comparable sale prices outside the neighborhood range need explanation.");
            case "FHA", "XF" -> Map.of(
                    "summary", "Cross-field and FHA checks compare values across sections and pages to catch inconsistencies.",
                    "terms", Map.of("REL", "remaining economic life", "case number", "FHA identifier expected in page headers"),
                    "example", "FHA case number should appear consistently in required page headers.");
            default -> Map.of(
                    "summary", "Review the referenced values and document location, then decide whether the item is acceptable or needs correction.",
                    "terms", Map.of(),
                    "example", "Use Pass only when the evidence supports the rule.");
        };
        return Map.of(
                "summary", "Rule " + (ruleId != null ? ruleId : "") + " - " + (ruleName != null ? ruleName : "QC check") + ". " + sectionHelp.get("summary"),
                "terms", sectionHelp.get("terms"),
                "example", sectionHelp.get("example"),
                "documentationRef", "QCChecklist.md#" + (ruleId != null ? ruleId.toLowerCase().replace("-", "-") : "rule")
        );
    }

    private Map<String, Object> exactRuleHelp(String ruleId) {
        if (ruleId == null) return null;
        return switch (ruleId) {
            case "S-1" -> Map.of(
                    "summary", "Checks that the subject address in the appraisal matches the order/engagement letter and known address signals.",
                    "terms", Map.of("USPS", "address standardization source", "subject", "property being appraised"),
                    "example", "Pass only if street, city, state, ZIP, and county identify the same property.");
            case "S-2" -> Map.of(
                    "summary", "Checks that borrower and co-borrower names match the engagement letter without omitted parties.",
                    "terms", Map.of("suffix", "name endings such as Jr, Sr, III"),
                    "example", "Middle-name differences can be reviewed, but a missing borrower should fail.");
            case "S-9" -> Map.of(
                    "summary", "Checks PUD and HOA consistency between checkbox state and dues.",
                    "terms", Map.of("PUD", "Planned Unit Development", "HOA", "Homeowners association dues"),
                    "example", "HOA dues greater than zero normally require the PUD indicator to be marked when applicable.");
            case "C-1" -> Map.of(
                    "summary", "Checks whether contract fields are completed for purchases and blank/default for refinance assignments.",
                    "terms", Map.of("refinance", "loan transaction without a current purchase contract"),
                    "example", "A refinance with populated purchase-contract price/date fields should fail.");
            case "C-2" -> Map.of(
                    "summary", "Checks contract price and fully executed date against purchase agreement evidence.",
                    "terms", Map.of("fully executed", "signed by all required parties", "contract date", "latest required signature date"),
                    "example", "If buyer signed 03/15 and seller signed 04/02, the contract date should be 04/02.");
            case "N-2" -> Map.of(
                    "summary", "Checks market trend against time-adjustment behavior in the sales grid.",
                    "terms", Map.of("time adjustment", "market-condition adjustment for sale date", "trend", "increasing, stable, or declining values"),
                    "example", "Increasing or declining markets need supported time adjustments or explanation.");
            case "N-5" -> Map.of(
                    "summary", "Checks that neighborhood boundaries are specific and complete.",
                    "terms", Map.of("boundary", "north, south, east, and west neighborhood limits"),
                    "example", "Named streets, highways, rivers, or city limits are better than generic area descriptions.");
            case "SCA-7" -> Map.of(
                    "summary", "Checks concessions and financing details for comparable sales and whether adjustments make sense.",
                    "terms", Map.of("concession", "seller or financing assistance", "comp", "comparable sale"),
                    "example", "A comparable with seller-paid costs may need a concession adjustment if market behavior supports it.");
            case "ADD-6" -> Map.of(
                    "summary", "Checks whether 1004MC comparable-sale counts match the sales comparison grid.",
                    "terms", Map.of("1004MC", "Market Conditions Addendum", "sales grid", "sales comparison section"),
                    "example", "If 1004MC shows 6 comparable sales but the grid has 3, the mismatch needs correction or support.");
            case "FHA-2" -> Map.of(
                    "summary", "Checks FHA case-number presence and consistency across required page headers.",
                    "terms", Map.of("case number", "FHA identifier expected on appraisal pages"),
                    "example", "Missing FHA case number on any required page should fail.");
            case "FHA-5" -> Map.of(
                    "summary", "Checks whether primary FHA comparables are recent enough relative to the effective date.",
                    "terms", Map.of("effective date", "appraisal valuation date", "primary comparables", "comparables 1, 2, and 3"),
                    "example", "A primary comparable more than 12 months older than the effective date should fail unless FHA policy supports it.");
            case "FHA-10" -> Map.of(
                    "summary", "Checks remaining economic life and whether short life is explained.",
                    "terms", Map.of("REL", "remaining economic life"),
                    "example", "REL under 30 years needs clear explanation and support.");
            case "COM-1", "COM-2", "COM-3", "COM-4", "COM-5", "COM-6", "COM-7" -> Map.of(
                    "summary", "Checks whether narrative commentary is specific, analytical, and tied to the subject or market evidence.",
                    "terms", Map.of("canned", "generic boilerplate that could apply to any report", "reconciliation", "final weighting and value reasoning"),
                    "example", "A useful comment explains why the data supports the conclusion, not just that the appraiser reviewed it.");
            default -> null;
        };
    }

    // ── Override / escalation workflow (ADMIN-only) ────────────────────────────

    /**
     * Returns all rule results awaiting admin override approval, across all batches.
     * Displayed in the admin "Override Queue" panel.
     */
    @GetMapping("/admin/overrides/pending")
    @org.springframework.security.access.prepost.PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<List<Map<String, Object>>> getPendingOverrides() {
        List<com.apprisal.common.entity.QCRuleResult> pending = qcRuleResultRepository.findAllPendingOverrides();
        List<Map<String, Object>> body = pending.stream().map(rr -> {
            Map<String, Object> m = new HashMap<>();
            m.put("ruleResultId",       rr.getId());
            m.put("ruleId",             rr.getRuleId());
            m.put("ruleName",           rr.getRuleName());
            m.put("status",             rr.getStatus());
            m.put("message",            rr.getMessage());
            m.put("severity",           rr.getSeverity());
            m.put("overridePending",    rr.getOverridePending());
            m.put("overrideRequestedAt", rr.getOverrideRequestedAt() != null ? rr.getOverrideRequestedAt().toString() : null);
            m.put("overrideRequestedBy", rr.getOverrideRequestedBy() != null ? displayName(rr.getOverrideRequestedBy()) : null);
            m.put("reviewerComment",    rr.getReviewerComment());
            if (rr.getQcResult() != null) {
                m.put("qcResultId", rr.getQcResult().getId());
                if (rr.getQcResult().getBatchFile() != null) {
                    m.put("filename", rr.getQcResult().getBatchFile().getFilename());
                    if (rr.getQcResult().getBatchFile().getBatch() != null) {
                        m.put("batchId",       rr.getQcResult().getBatchFile().getBatch().getId());
                        m.put("parentBatchId", rr.getQcResult().getBatchFile().getBatch().getParentBatchId());
                    }
                }
            }
            return m;
        }).toList();
        return ResponseEntity.ok(body);
    }

    /**
     * Admin approves or rejects a pending FAIL override.
     *
     * approve=true  → final decision PASS, override cleared, reviewer informed.
     * approve=false → override rejected, reviewer must re-decide or escalate.
     */
    @PostMapping("/admin/overrides/{ruleResultId}/decide")
    @org.springframework.security.access.prepost.PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<Map<String, Object>> decideOverride(
            @PathVariable Long ruleResultId,
            @RequestBody Map<String, Object> body,
            @AuthenticationPrincipal UserPrincipal principal,
            HttpServletRequest httpRequest) {
        try {
            boolean approve = Boolean.TRUE.equals(body.get("approve"));
            String adminComment = body.containsKey("comment") ? String.valueOf(body.get("comment")) : "";

            com.apprisal.common.entity.QCRuleResult rr = qcRuleResultRepository.findById(ruleResultId)
                    .orElseThrow(() -> new IllegalArgumentException("Rule result not found: " + ruleResultId));

            if (!Boolean.TRUE.equals(rr.getOverridePending())) {
                return ResponseEntity.badRequest().body(Map.of("success", false,
                        "error", "Rule result " + ruleResultId + " is not awaiting override approval."));
            }

            rr.setOverridePending(false);
            rr.setOverrideApprovedBy(principal.getUser());
            rr.setOverrideApprovedAt(java.time.LocalDateTime.now());

            if (approve) {
                rr.setReviewerVerified(true);
                rr.setReviewerComment(adminComment.isBlank() ? rr.getReviewerComment() : adminComment);
            } else {
                // Rejection: reset the decision so the reviewer can reconsider.
                rr.setReviewerVerified(null);
                rr.setReviewerComment("Override rejected by admin" + (adminComment.isBlank() ? "." : ": " + adminComment));
            }

            qcRuleResultRepository.save(rr);

            auditLogService.log(principal.getUser(),
                    approve ? "OVERRIDE_APPROVED" : "OVERRIDE_REJECTED",
                    "QCRuleResult", ruleResultId,
                    "comment=" + adminComment, clientIp(httpRequest), httpRequest.getHeader("User-Agent"));

            // Notify the reviewer via real-time event
            if (rr.getQcResult() != null) {
                Map<String, Object> event = new HashMap<>();
                event.put("type",         approve ? "OVERRIDE_APPROVED" : "OVERRIDE_REJECTED");
                event.put("ruleResultId", ruleResultId);
                event.put("ruleId",       rr.getRuleId());
                event.put("approvedBy",   displayName(principal.getUser()));
                event.put("comment",      adminComment);
                realtimeEventPublisher.publish("/topic/reviewer/qc/" + rr.getQcResult().getId() + "/override", event);
            }

            return ResponseEntity.ok(Map.of(
                    "success", true,
                    "ruleResultId", ruleResultId,
                    "approved", approve,
                    "approvedBy", displayName(principal.getUser())
            ));
        } catch (IllegalArgumentException e) {
            return ResponseEntity.badRequest().body(Map.of("success", false, "error", e.getMessage()));
        } catch (Exception e) {
            log.error("Override decision failed: {}", e.getMessage(), e);
            return ResponseEntity.status(500).body(Map.of("success", false, "error", "Override decision failed"));
        }
    }
}
