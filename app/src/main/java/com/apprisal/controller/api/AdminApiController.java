package com.apprisal.controller.api;

import com.apprisal.common.entity.Client;
import com.apprisal.common.entity.Role;
import com.apprisal.common.entity.User;
import com.apprisal.user.service.UserService;
import com.apprisal.user.service.ClientService;
import com.apprisal.batch.service.BatchService;
import com.apprisal.common.service.AuditLogService;
import com.apprisal.common.security.UserPrincipal;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;
import org.springframework.lang.NonNull;

import java.util.Map;

/**
 * Admin REST API — user management, client management.
 * Batch operations are in BatchApiController.
 * All endpoints require ROLE_ADMIN (enforced in SecurityConfig).
 */
@RestController
@RequestMapping("/api/admin")
public class AdminApiController {

    private final UserService userService;
    private final ClientService clientService;
    private final BatchService batchService;
    private final AuditLogService auditLogService;

    public AdminApiController(UserService userService,
            ClientService clientService,
            BatchService batchService,
            AuditLogService auditLogService) {
        this.userService = userService;
        this.clientService = clientService;
        this.batchService = batchService;
        this.auditLogService = auditLogService;
    }

    // ── User Management ───────────────────────────────────────────────────────

    @GetMapping("/users")
    public ResponseEntity<?> getUsers(
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        var pg = userService.findAll(PageRequest.of(page, size, Sort.by("id").descending()));
        // Return a stable map — Page<User> serialization is unstable across Spring Data versions
        return ResponseEntity.ok(Map.of(
            "content",       pg.getContent(),
            "totalPages",    pg.getTotalPages(),
            "number",        pg.getNumber(),
            "totalElements", pg.getTotalElements()
        ));
    }

    @GetMapping("/users/{id}")
    public ResponseEntity<?> getUser(@PathVariable @NonNull Long id) {
        return userService.findById(id)
                .map(ResponseEntity::ok)
                .orElse(ResponseEntity.notFound().build());
    }

    @PostMapping("/users")
    public ResponseEntity<?> createUser(@RequestBody Map<String, Object> request,
            @AuthenticationPrincipal UserPrincipal principal) {
        try {
            String username = (String) request.get("username");
            String password = (String) request.get("password");
            String roleStr  = (String) request.get("role");

            // Enforce two-role system: only ADMIN or REVIEWER
            if (roleStr == null || (!roleStr.equals("ADMIN") && !roleStr.equals("REVIEWER"))) {
                return ResponseEntity.badRequest().body(Map.of("error", "Role must be ADMIN or REVIEWER"));
            }
            Role role = Role.valueOf(roleStr);
            String email    = (String) request.get("email");
            String fullName = (String) request.get("fullName");
            Long clientId   = request.get("clientId") != null ? Long.valueOf(request.get("clientId").toString()) : null;

            Client client = clientId != null ? clientService.findById(clientId).orElse(null) : null;
            User user = userService.create(username, password, role, email, fullName, client);
            auditLogService.logEntity(principal.getUser(), "USER_CREATED", "User", user.getId());
            return ResponseEntity.ok(user);
        } catch (Exception e) {
            return ResponseEntity.badRequest().body(Map.of("error", e.getMessage()));
        }
    }

    @PutMapping("/users/{id}")
    public ResponseEntity<?> updateUser(@PathVariable @NonNull Long id,
            @RequestBody Map<String, Object> request,
            @AuthenticationPrincipal UserPrincipal principal) {
        try {
            String email    = (String) request.get("email");
            String fullName = (String) request.get("fullName");
            Role role = null;
            if (request.get("role") != null) {
                String roleStr = (String) request.get("role");
                if (!roleStr.equals("ADMIN") && !roleStr.equals("REVIEWER")) {
                    return ResponseEntity.badRequest().body(Map.of("error", "Role must be ADMIN or REVIEWER"));
                }
                role = Role.valueOf(roleStr);
            }
            Long clientId = request.get("clientId") != null ? Long.valueOf(request.get("clientId").toString()) : null;
            Client client = clientId != null ? clientService.findById(clientId).orElse(null) : null;

            User user = userService.update(id, email, fullName, role, client);
            auditLogService.logEntity(principal.getUser(), "USER_UPDATED", "User", id);
            return ResponseEntity.ok(user);
        } catch (Exception e) {
            return ResponseEntity.badRequest().body(Map.of("error", e.getMessage()));
        }
    }

    @DeleteMapping("/users/{id}")
    public ResponseEntity<?> deleteUser(@PathVariable @NonNull Long id,
            @AuthenticationPrincipal UserPrincipal principal) {
        try {
            userService.delete(id);
            auditLogService.logEntity(principal.getUser(), "USER_DELETED", "User", id);
            return ResponseEntity.ok(Map.of("success", true));
        } catch (Exception e) {
            return ResponseEntity.badRequest().body(Map.of("error", e.getMessage()));
        }
    }

    // ── Client Organisations ──────────────────────────────────────────────────

    @GetMapping("/clients")
    public ResponseEntity<?> getClients() {
        return ResponseEntity.ok(clientService.findAll());
    }

    @PostMapping("/clients")
    public ResponseEntity<?> createClient(@RequestBody Map<String, String> request,
            @AuthenticationPrincipal UserPrincipal principal) {
        try {
            Client client = clientService.create(request.get("name"), request.get("code"));
            auditLogService.logEntity(principal.getUser(), "CLIENT_CREATED", "Client", client.getId());
            return ResponseEntity.ok(client);
        } catch (Exception e) {
            return ResponseEntity.badRequest().body(Map.of("error", e.getMessage()));
        }
    }

    // ── Batch assignment (delegated to BatchApiController for upload,
    //    kept here for the assign action used in the admin dashboard) ──────────

    @PostMapping("/batches/{id}/assign")
    public ResponseEntity<?> assignBatch(@PathVariable @NonNull Long id,
            @RequestBody Map<String, Long> request,
            @AuthenticationPrincipal UserPrincipal principal) {
        try {
            Long reviewerId = request.get("reviewerId");
            if (reviewerId == null) throw new IllegalArgumentException("reviewerId is required");

            User reviewer = userService.findById(reviewerId)
                    .orElseThrow(() -> new IllegalArgumentException("Reviewer not found: " + reviewerId));

            if (reviewer.getRole() != Role.REVIEWER) {
                throw new IllegalArgumentException("User " + reviewerId + " is not a REVIEWER");
            }

            batchService.assignReviewer(id, reviewer);
            auditLogService.logEntity(principal.getUser(), "BATCH_ASSIGNED", "Batch", id);
            return ResponseEntity.ok(Map.of("success", true, "reviewerId", reviewerId));
        } catch (Exception e) {
            return ResponseEntity.badRequest().body(Map.of("error", e.getMessage()));
        }
    }
}
