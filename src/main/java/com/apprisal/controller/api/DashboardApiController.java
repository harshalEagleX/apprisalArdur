package com.apprisal.controller.api;

import com.apprisal.entity.User;
import com.apprisal.service.DashboardService;
import com.apprisal.service.UserPrincipal;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

/**
 * REST API Controller for dashboard metrics.
 */
@RestController
@RequestMapping("/api")
public class DashboardApiController {

    private final DashboardService dashboardService;

    public DashboardApiController(DashboardService dashboardService) {
        this.dashboardService = dashboardService;
    }

    @GetMapping("/admin/dashboard")
    public ResponseEntity<Map<String, Object>> getAdminDashboard() {
        return ResponseEntity.ok(dashboardService.getAdminDashboard());
    }

    @GetMapping("/client/dashboard")
    public ResponseEntity<?> getClientDashboard(@AuthenticationPrincipal UserPrincipal principal) {
        User user = principal.getUser();

        if (user.getClient() == null) {
            return ResponseEntity.badRequest()
                    .body(Map.of("error", "No client organization assigned"));
        }

        return ResponseEntity.ok(dashboardService.getClientDashboard(user.getClient().getId()));
    }

    @GetMapping("/reviewer/dashboard")
    public ResponseEntity<Map<String, Object>> getReviewerDashboard(
            @AuthenticationPrincipal UserPrincipal principal) {
        User user = principal.getUser();
        return ResponseEntity.ok(dashboardService.getReviewerDashboard(user.getId()));
    }
}
