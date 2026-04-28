package com.apprisal.user.controller.api;

import com.apprisal.common.entity.User;
import com.apprisal.user.service.DashboardService;
import com.apprisal.common.security.UserPrincipal;
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

    /**
     * Returns the current user's id, username, and role.
     * Used by the Next.js root page (/) to decide which dashboard to show
     * without probing multiple role-specific endpoints.
     * Returns 401 automatically if the session is not authenticated.
     */
    @GetMapping("/me")
    public ResponseEntity<Map<String, Object>> getCurrentUser(
            @AuthenticationPrincipal UserPrincipal principal) {
        if (principal == null) {
            return ResponseEntity.status(401).build();
        }
        User user = principal.getUser();
        return ResponseEntity.ok(Map.of(
                "id",       user.getId(),
                "username", user.getUsername(),
                "role",     user.getRole().name()
        ));
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
