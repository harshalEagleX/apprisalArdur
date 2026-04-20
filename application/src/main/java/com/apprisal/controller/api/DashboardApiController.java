package com.apprisal.controller.api;

import com.apprisal.entity.User;
import com.apprisal.service.AdminDashboardService;
import com.apprisal.service.ClientDashboardService;
import com.apprisal.service.ReviewerDashboardService;
import com.apprisal.service.UserPrincipal;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;

/**
 * REST API Controller for dashboard metrics.
 */
@RestController
@RequestMapping("/api")
@Tag(name = "Dashboard API", description = "Operations for fetching unified stats across Admin, Reviewer, and Client")
public class DashboardApiController {

    private final AdminDashboardService adminDashboardService;
    private final ClientDashboardService clientDashboardService;
    private final ReviewerDashboardService reviewerDashboardService;

    public DashboardApiController(AdminDashboardService adminDashboardService,
                                  ClientDashboardService clientDashboardService,
                                  ReviewerDashboardService reviewerDashboardService) {
        this.adminDashboardService = adminDashboardService;
        this.clientDashboardService = clientDashboardService;
        this.reviewerDashboardService = reviewerDashboardService;
    }

    @Operation(summary = "Get admin dashboard metrics", description = "Fetches global stats: batches, queue, active reviewers")
    @GetMapping("/admin/dashboard")
    public ResponseEntity<Map<String, Object>> getAdminDashboard() {
        return ResponseEntity.ok(adminDashboardService.getAdminDashboard());
    }

    @Operation(summary = "Get client dashboard metrics", description = "Fetches client-scoped stats: client batches, OCR progress")
    @GetMapping("/client/dashboard")
    public ResponseEntity<?> getClientDashboard(@AuthenticationPrincipal UserPrincipal principal) {
        User user = principal.getUser();

        if (user.getClient() == null) {
            return ResponseEntity.badRequest()
                    .body(Map.of("error", "No client organization assigned"));
        }

        return ResponseEntity.ok(clientDashboardService.getClientDashboard(user.getClient().getId()));
    }

    @Operation(summary = "Get reviewer dashboard metrics", description = "Fetches assigned batches and queue length for reviewer")
    @GetMapping("/reviewer/dashboard")
    public ResponseEntity<Map<String, Object>> getReviewerDashboard(
            @AuthenticationPrincipal UserPrincipal principal) {
        User user = principal.getUser();
        return ResponseEntity.ok(reviewerDashboardService.getReviewerDashboard(user.getId()));
    }
}
