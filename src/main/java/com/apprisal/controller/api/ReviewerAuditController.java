package com.apprisal.controller.api;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

/**
 * Audit logging API for reviewer actions.
 * Logs highlight/navigation events for compliance.
 */
@RestController
@RequestMapping("/api/audit")
public class ReviewerAuditController {

    private static final Logger log = LoggerFactory.getLogger(ReviewerAuditController.class);

    /**
     * Log PDF highlight action for audit trail.
     */
    @PostMapping("/highlight")
    public ResponseEntity<?> logHighlight(
            @RequestBody Map<String, Object> event,
            @AuthenticationPrincipal UserDetails principal) {

        String reviewerId = principal != null ? principal.getUsername() : "anonymous";

        log.info("AUDIT_HIGHLIGHT: reviewer={} fileId={} ruleId={} page={} status={} section={} timestamp={}",
                reviewerId,
                event.get("fileId"),
                event.get("ruleId"),
                event.get("pageNumber"),
                event.get("status"),
                event.get("section"),
                event.get("timestamp"));

        return ResponseEntity.ok(Map.of("logged", true));
    }
}
