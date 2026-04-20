package com.apprisal.controller.api;

import com.apprisal.entity.Client;
import com.apprisal.entity.Role;
import com.apprisal.entity.User;
import com.apprisal.service.*;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;
import org.springframework.lang.NonNull;

import java.util.Map;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;

/**
 * REST API Controller for admin operations.
 */
@RestController
@RequestMapping("/api/admin")
@Tag(name = "Admin API", description = "Operations for User, Client, and Batch management by Administrators")
public class AdminApiController {

    private final UserService userService;
    private final ClientService clientService;
    private final BatchService batchService;
    private final ImpersonationService impersonationService;

    public AdminApiController(UserService userService,
            ClientService clientService,
            BatchService batchService,
            ImpersonationService impersonationService) {
        this.userService = userService;
        this.clientService = clientService;
        this.batchService = batchService;
        this.impersonationService = impersonationService;
    }

    // ============ User Management APIs ============

    @Operation(summary = "Get all users pageable", description = "Returns a paginated list of all users")
    @GetMapping("/users")
    public ResponseEntity<Page<User>> getUsers(
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "10") int size) {
        return ResponseEntity.ok(userService.findAll(PageRequest.of(page, size, Sort.by("id").descending())));
    }

    @Operation(summary = "Get user by ID", description = "Returns a single user by ID")
    @GetMapping("/users/{id}")
    public ResponseEntity<?> getUser(@PathVariable @NonNull Long id) {
        return userService.findById(id)
                .map(ResponseEntity::ok)
                .orElse(ResponseEntity.notFound().build());
    }

    @Operation(summary = "Create a new user", description = "Creates a new user and assigns them a required role")
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

            return ResponseEntity.ok(user);
        } catch (Exception e) {
            return ResponseEntity.badRequest().body(Map.of("error", e.getMessage()));
        }
    }

    @Operation(summary = "Update an existing user", description = "Updates email, fullName, role, or linked client")
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

            return ResponseEntity.ok(user);
        } catch (Exception e) {
            return ResponseEntity.badRequest().body(Map.of("error", e.getMessage()));
        }
    }

    @Operation(summary = "Delete user", description = "Deletes user by ID")
    @DeleteMapping("/users/{id}")
    public ResponseEntity<?> deleteUser(@PathVariable @NonNull Long id,
            @AuthenticationPrincipal UserPrincipal principal) {
        try {
            userService.delete(id);
            return ResponseEntity.ok(Map.of("success", true));
        } catch (Exception e) {
            return ResponseEntity.badRequest().body(Map.of("error", e.getMessage()));
        }
    }

    // ============ Client Management APIs ============

    @Operation(summary = "Get all clients", description = "Retrieve list of all registered clients")
    @GetMapping("/clients")
    public ResponseEntity<?> getClients() {
        return ResponseEntity.ok(clientService.findAll());
    }

    @Operation(summary = "Create client organization", description = "Creates a new client organization mapped to batches")
    @PostMapping("/clients")
    public ResponseEntity<?> createClient(@RequestBody Map<String, String> request,
            @AuthenticationPrincipal UserPrincipal principal) {
        try {
            Client client = clientService.create(request.get("name"), request.get("code"));
            return ResponseEntity.ok(client);
        } catch (Exception e) {
            return ResponseEntity.badRequest().body(Map.of("error", e.getMessage()));
        }
    }

    // ============ Batch Management APIs ============

    @Operation(summary = "Get paginated batches", description = "Retrieves batches globally for admin view")
    @GetMapping("/batches")
    public ResponseEntity<?> getBatches(
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "10") int size) {
        return ResponseEntity.ok(batchService.findAll(PageRequest.of(page, size, Sort.by("createdAt").descending())));
    }

    @Operation(summary = "Assign reviewer to batch", description = "Manually assign a reviewer using this endpoint")
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

            return ResponseEntity.ok(Map.of("success", true));
        } catch (Exception e) {
            return ResponseEntity.badRequest().body(Map.of("error", e.getMessage()));
        }
    }

    // ============ Impersonation APIs ============

    @Operation(summary = "Impersonate another user", description = "Start impersonating a user (Client/Reviewer) for debugging")
    @PostMapping("/impersonate/{userId}")
    public ResponseEntity<?> startImpersonation(@PathVariable @NonNull Long userId,
            @AuthenticationPrincipal UserPrincipal principal) {

        if (impersonationService.startImpersonation(userId)) {
            return ResponseEntity.ok(Map.of(
                    "success", true,
                    "message", "Now impersonating user " + userId));
        }
        return ResponseEntity.badRequest().body(Map.of("error", "Failed to start impersonation"));
    }

    @Operation(summary = "Stop impersonating", description = "Reverts context back to Admin")
    @PostMapping("/impersonate/stop")
    public ResponseEntity<?> stopImpersonation(@AuthenticationPrincipal UserPrincipal principal) {
        if (impersonationService.stopImpersonation()) {
            return ResponseEntity.ok(Map.of("success", true, "message", "Impersonation stopped"));
        }
        return ResponseEntity.badRequest().body(Map.of("error", "Not currently impersonating"));
    }

    @Operation(summary = "Check impersonation status", description = "Check if an impersonation session is active")
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
