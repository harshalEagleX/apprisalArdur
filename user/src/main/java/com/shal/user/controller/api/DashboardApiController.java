package com.shal.user.controller.api;

import com.shal.common.entity.User;
import com.shal.user.service.DashboardService;
import com.shal.user.service.UserService;
import com.shal.common.security.UserPrincipal;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.web.bind.annotation.*;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;

/**
 * REST API Controller for dashboard metrics.
 */
@RestController
@RequestMapping("/api")
public class DashboardApiController {

    private final DashboardService dashboardService;
    private final UserService userService;
    private final PasswordEncoder passwordEncoder;

    public DashboardApiController(DashboardService dashboardService,
                                  UserService userService,
                                  PasswordEncoder passwordEncoder) {
        this.dashboardService = dashboardService;
        this.userService = userService;
        this.passwordEncoder = passwordEncoder;
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

    /** Full profile data for the profile page. */
    @GetMapping("/me/profile")
    public ResponseEntity<Map<String, Object>> getProfile(
            @AuthenticationPrincipal UserPrincipal principal) {
        if (principal == null) return ResponseEntity.status(401).build();
        User user = principal.getUser();
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("id",          user.getId());
        body.put("username",    user.getUsername());
        body.put("fullName",    user.getFullName());
        body.put("email",       user.getEmail());
        body.put("role",        user.getRole() != null ? user.getRole().name() : null);
        body.put("active",      user.getActive() == null || user.getActive());
        body.put("lastLoginAt", user.getLastLoginAt() != null ? user.getLastLoginAt().toString() : null);
        body.put("createdAt",   user.getCreatedAt() != null ? user.getCreatedAt().toString() : null);
        if (user.getClient() != null) {
            body.put("client", Map.of(
                    "id",   user.getClient().getId(),
                    "name", user.getClient().getName() != null ? user.getClient().getName() : "",
                    "code", user.getClient().getCode() != null ? user.getClient().getCode() : ""));
        } else {
            body.put("client", null);
        }
        return ResponseEntity.ok(body);
    }

    /** Update display name and email for the current user. */
    @PutMapping("/me/profile")
    public ResponseEntity<Map<String, Object>> updateProfile(
            @RequestBody Map<String, String> request,
            @AuthenticationPrincipal UserPrincipal principal) {
        if (principal == null) return ResponseEntity.status(401).build();
        User user = principal.getUser();
        String fullName = request != null ? request.get("fullName") : null;
        String email    = request != null ? request.get("email") : null;
        try {
            userService.update(Objects.requireNonNull(user.getId()), email, fullName, user.getRole(), user.getClient());
            return ResponseEntity.ok(Map.of("success", true, "message", "Profile updated successfully"));
        } catch (Exception e) {
            return ResponseEntity.badRequest().body(Map.of("success", false, "error", e.getMessage()));
        }
    }

    /** Change password for the currently authenticated user. */
    @PostMapping("/me/change-password")
    public ResponseEntity<Map<String, Object>> changePassword(
            @RequestBody Map<String, String> request,
            @AuthenticationPrincipal UserPrincipal principal) {
        if (principal == null) return ResponseEntity.status(401).build();
        User user = principal.getUser();

        String current  = request != null ? request.get("currentPassword") : null;
        String next     = request != null ? request.get("newPassword") : null;
        String confirm  = request != null ? request.get("confirmPassword") : null;

        if (current == null || current.isBlank())
            return ResponseEntity.badRequest().body(Map.of("success", false, "error", "Current password is required"));
        if (!passwordEncoder.matches(current, user.getPassword()))
            return ResponseEntity.badRequest().body(Map.of("success", false, "error", "Current password is incorrect"));
        if (next == null || next.isBlank())
            return ResponseEntity.badRequest().body(Map.of("success", false, "error", "New password is required"));
        if (!next.equals(confirm))
            return ResponseEntity.badRequest().body(Map.of("success", false, "error", "New passwords do not match"));
        if (next.length() < UserService.PASSWORD_MIN_LENGTH)
            return ResponseEntity.badRequest().body(Map.of("success", false, "error",
                    "Password must be at least " + UserService.PASSWORD_MIN_LENGTH + " characters"));

        try {
            userService.updatePassword(Objects.requireNonNull(user.getId()), next);
            return ResponseEntity.ok(Map.of("success", true, "message", "Password changed successfully"));
        } catch (Exception e) {
            return ResponseEntity.badRequest().body(Map.of("success", false, "error", e.getMessage()));
        }
    }

    @GetMapping("/config/password-policy")
    public ResponseEntity<Map<String, Object>> getPasswordPolicy() {
        return ResponseEntity.ok(Map.of(
                "minLength", UserService.PASSWORD_MIN_LENGTH
        ));
    }

    @GetMapping("/admin/dashboard")
    public ResponseEntity<Map<String, Object>> getAdminDashboard() {
        return ResponseEntity.ok(dashboardService.getAdminDashboard());
    }

    @GetMapping("/reviewer/dashboard")
    public ResponseEntity<Map<String, Object>> getReviewerDashboard(
            @AuthenticationPrincipal UserPrincipal principal) {
        User user = principal.getUser();
        return ResponseEntity.ok(dashboardService.getReviewerDashboard(user.getId()));
    }
}
