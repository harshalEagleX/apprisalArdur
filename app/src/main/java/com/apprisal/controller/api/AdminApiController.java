package com.apprisal.controller.api;

import com.apprisal.common.entity.AuditLog;
import com.apprisal.common.entity.Client;
import com.apprisal.common.entity.QCResult;
import com.apprisal.common.entity.Role;
import com.apprisal.common.entity.User;
import com.apprisal.user.service.UserService;
import com.apprisal.user.service.ClientService;
import com.apprisal.batch.service.BatchService;
import com.apprisal.common.service.AuditLogService;
import com.apprisal.common.repository.AuditLogRepository;
import com.apprisal.common.repository.QCResultRepository;
import com.apprisal.common.security.UserPrincipal;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;
import org.springframework.lang.NonNull;
import com.zaxxer.hikari.HikariDataSource;
import com.zaxxer.hikari.HikariPoolMXBean;
import javax.sql.DataSource;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
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
    private final AuditLogRepository auditLogRepository;
    private final QCResultRepository qcResultRepository;
    private final com.apprisal.common.repository.BatchRepository batchRepository;
    private final com.apprisal.common.repository.BatchFileRepository batchFileRepository;
    private final DataSource dataSource;

    public AdminApiController(UserService userService,
            ClientService clientService,
            BatchService batchService,
            AuditLogService auditLogService,
            AuditLogRepository auditLogRepository,
            QCResultRepository qcResultRepository,
            com.apprisal.common.repository.BatchRepository batchRepository,
            com.apprisal.common.repository.BatchFileRepository batchFileRepository,
            DataSource dataSource) {
        this.userService = userService;
        this.clientService = clientService;
        this.batchService = batchService;
        this.auditLogService = auditLogService;
        this.auditLogRepository = auditLogRepository;
        this.qcResultRepository = qcResultRepository;
        this.batchRepository = batchRepository;
        this.batchFileRepository = batchFileRepository;
        this.dataSource = dataSource;
    }

    /**
     * Database connection-pool health for the admin "degraded mode" banner.
     * The pool already degrades gracefully (callers queue up to the 30s
     * connection-timeout, then fail with a clear error rather than crashing) —
     * this surfaces that pressure proactively so an admin knows operations may be
     * slow before they hit a timeout. {@code degraded} is true when callers are
     * waiting for a connection or the pool is fully checked out.
     */
    @GetMapping("/system/health")
    public ResponseEntity<Map<String, Object>> systemHealth() {
        Map<String, Object> body = new HashMap<>();
        Map<String, Object> pool = new HashMap<>();
        boolean degraded = false;
        if (dataSource instanceof HikariDataSource hikari) {
            HikariPoolMXBean mx = hikari.getHikariPoolMXBean();
            if (mx != null) {
                int active = mx.getActiveConnections();
                int waiting = mx.getThreadsAwaitingConnection();
                int max = hikari.getMaximumPoolSize();
                pool.put("active", active);
                pool.put("idle", mx.getIdleConnections());
                pool.put("total", mx.getTotalConnections());
                pool.put("waiting", waiting);
                pool.put("max", max);
                degraded = waiting > 0 || active >= max;
            }
        }
        body.put("pool", pool);
        body.put("degraded", degraded);
        return ResponseEntity.ok(body);
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

    /**
     * Per-client operational rollup for the clients table (batches, completed, files, success rate,
     * last activity). Two grouped queries, joined in memory — no N+1 across the client list.
     * Keyed by client id as a string so the frontend can look each row up.
     */
    @GetMapping("/clients/stats")
    public ResponseEntity<Map<String, Object>> getClientStats() {
        Map<Long, Long> fileCounts = new HashMap<>();
        for (Object[] row : batchFileRepository.clientFileCounts()) {
            fileCounts.put(((Number) row[0]).longValue(), ((Number) row[1]).longValue());
        }
        Map<String, Object> out = new HashMap<>();
        for (Object[] row : batchRepository.clientBatchStats()) {
            long clientId   = ((Number) row[0]).longValue();
            long batches    = ((Number) row[1]).longValue();
            long completed  = row[2] != null ? ((Number) row[2]).longValue() : 0L;
            Object lastAct  = row[3];
            Map<String, Object> stat = new HashMap<>();
            stat.put("batches", batches);
            stat.put("completed", completed);
            stat.put("files", fileCounts.getOrDefault(clientId, 0L));
            stat.put("successRate", batches > 0 ? Math.round((completed * 100.0) / batches) : null);
            stat.put("lastActivity", lastAct != null ? lastAct.toString() : null);
            out.put(String.valueOf(clientId), stat);
        }
        return ResponseEntity.ok(out);
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

    // ── Batch audit log for graph ─────────────────────────────────────────────

    @GetMapping("/batches/{id}/audit")
    public ResponseEntity<List<Map<String, Object>>> getBatchAuditLog(@PathVariable @NonNull Long id) {
        try {
            // Collect all QCResult IDs for files in this batch
            List<QCResult> qcResults = qcResultRepository.findByBatchId(id);
            List<Map<String, Object>> result = new ArrayList<>();
            for (QCResult qcr : qcResults) {
                List<AuditLog> logs = auditLogRepository.findByEntityTypeAndEntityId("QCResult", qcr.getId());
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
                    result.add(row);
                }
            }
            return ResponseEntity.ok(result);
        } catch (Exception e) {
            return ResponseEntity.ok(List.of());
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
