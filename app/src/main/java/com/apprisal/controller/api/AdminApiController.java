package com.apprisal.controller.api;

import com.apprisal.common.entity.Client;
import com.apprisal.common.entity.Role;
import com.apprisal.common.entity.User;
import com.apprisal.user.service.UserService;
import com.apprisal.user.service.ClientService;
import com.apprisal.batch.service.BatchService;
import com.apprisal.user.service.ImpersonationService;
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
 * REST API Controller for admin operations.
 */
@RestController
@RequestMapping("/api/admin")
public class AdminApiController {

    private final UserService userService;
    private final ClientService clientService;
    private final BatchService batchService;
    private final ImpersonationService impersonationService;
    private final AuditLogService auditLogService;

    public AdminApiController(UserService userService,
            ClientService clientService,
            BatchService batchService,
            ImpersonationService impersonationService,
            AuditLogService auditLogService) {
        this.userService = userService;
        this.clientService = clientService;
        this.batchService = batchService;
        this.impersonationService = impersonationService;
        this.auditLogService = auditLogService;
    }

    // ============ User Management APIs ============

    @GetMapping("/users")
    public ResponseEntity<Page<User>> getUsers(
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "10") int size) {
        return ResponseEntity.ok(userService.findAll(PageRequest.of(page, size, Sort.by("id").descending())));
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
            Role role = Role.valueOf((String) request.get("role"));
            String email = (String) request.get("email");
            String fullName = (String) request.get("fullName");
            Long clientId = request.get("clientId") != null ? Long.valueOf(request.get("clientId").toString()) : null;

            Client client = clientId != null ? clientService.findById(clientId).orElse(null) : null;
            User user = userService.create(username, password, role, email, fullName, client);

            auditLogService.logEntity(principal.getUser(), "USER_CREATED_API", "User", user.getId());

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
            String email = (String) request.get("email");
            String fullName = (String) request.get("fullName");
            Role role = request.get("role") != null ? Role.valueOf((String) request.get("role")) : null;
            Long clientId = request.get("clientId") != null ? Long.valueOf(request.get("clientId").toString()) : null;

            Client client = clientId != null ? clientService.findById(clientId).orElse(null) : null;
            User user = userService.update(id, email, fullName, role, client);

            auditLogService.logEntity(principal.getUser(), "USER_UPDATED_API", "User", id);

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
            auditLogService.logEntity(principal.getUser(), "USER_DELETED_API", "User", id);
            return ResponseEntity.ok(Map.of("success", true));
        } catch (Exception e) {
            return ResponseEntity.badRequest().body(Map.of("error", e.getMessage()));
        }
    }

    // ============ Client Management APIs ============

    @GetMapping("/clients")
    public ResponseEntity<?> getClients() {
        return ResponseEntity.ok(clientService.findAll());
    }

    @PostMapping("/clients")
    public ResponseEntity<?> createClient(@RequestBody Map<String, String> request,
            @AuthenticationPrincipal UserPrincipal principal) {
        try {
            Client client = clientService.create(request.get("name"), request.get("code"));
            auditLogService.logEntity(principal.getUser(), "CLIENT_CREATED_API", "Client", client.getId());
            return ResponseEntity.ok(client);
        } catch (Exception e) {
            return ResponseEntity.badRequest().body(Map.of("error", e.getMessage()));
        }
    }

    // ============ Batch Management APIs ============

    @GetMapping("/batches")
    public ResponseEntity<?> getBatches(
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "10") int size) {
        return ResponseEntity.ok(batchService.findAll(PageRequest.of(page, size, Sort.by("createdAt").descending())));
    }

    @PostMapping("/batches/{id}/assign")
    public ResponseEntity<?> assignBatch(@PathVariable @NonNull Long id,
            @RequestBody Map<String, Long> request,
            @AuthenticationPrincipal UserPrincipal principal) {
        try {
            Long reviewerId = request.get("reviewerId");
            if (reviewerId == null) {
                throw new IllegalArgumentException("Reviewer ID is required");
            }
            User reviewer = userService.findById(reviewerId)
                    .orElseThrow(() -> new IllegalArgumentException("Reviewer not found"));

            batchService.assignReviewer(id, reviewer);
            auditLogService.logEntity(principal.getUser(), "BATCH_ASSIGNED_API", "Batch", id);

            return ResponseEntity.ok(Map.of("success", true));
        } catch (Exception e) {
            return ResponseEntity.badRequest().body(Map.of("error", e.getMessage()));
        }
    }

    // ============ Impersonation APIs ============

    @PostMapping("/impersonate/{userId}")
    public ResponseEntity<?> startImpersonation(@PathVariable @NonNull Long userId,
            @AuthenticationPrincipal UserPrincipal principal) {
        auditLogService.logEntity(principal.getUser(), "IMPERSONATION_STARTED", "User", userId);

        if (impersonationService.startImpersonation(userId)) {
            return ResponseEntity.ok(Map.of(
                    "success", true,
                    "message", "Now impersonating user " + userId));
        }
        return ResponseEntity.badRequest().body(Map.of("error", "Failed to start impersonation"));
    }

    @PostMapping("/impersonate/stop")
    public ResponseEntity<?> stopImpersonation(@AuthenticationPrincipal UserPrincipal principal) {
        if (impersonationService.stopImpersonation()) {
            return ResponseEntity.ok(Map.of("success", true, "message", "Impersonation stopped"));
        }
        return ResponseEntity.badRequest().body(Map.of("error", "Not currently impersonating"));
    }

    @GetMapping("/impersonate/status")
    public ResponseEntity<?> getImpersonationStatus() {
        boolean isImpersonating = impersonationService.isImpersonating();
        return ResponseEntity.ok(Map.of(
                "isImpersonating", isImpersonating,
                "originalUser", impersonationService.getOriginalUser()
                        .map(User::getUsername)
                        .orElse(null)));
    }
}
