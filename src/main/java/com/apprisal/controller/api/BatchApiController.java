package com.apprisal.controller.api;

import com.apprisal.entity.*;
import com.apprisal.service.*;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.lang.NonNull;

import java.util.HashMap;
import java.util.Map;

/**
 * REST API Controller for batch operations.
 */
@RestController
@RequestMapping("/api/client/batches")
public class BatchApiController {

    private final BatchService batchService;
    private final AuditLogService auditLogService;

    public BatchApiController(BatchService batchService, AuditLogService auditLogService) {
        this.batchService = batchService;
        this.auditLogService = auditLogService;
    }

    @GetMapping
    public ResponseEntity<?> getBatches(
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "10") int size,
            @AuthenticationPrincipal UserPrincipal principal) {

        User user = principal.getUser();
        Client client = user.getClient();

        if (client == null) {
            return ResponseEntity.badRequest().body(Map.of("error", "No client organization assigned"));
        }

        Page<Batch> batches = batchService.findByClientId(client.getId(),
                PageRequest.of(page, size, Sort.by("createdAt").descending()));

        return ResponseEntity.ok(batches);
    }

    @GetMapping("/{id}")
    public ResponseEntity<?> getBatch(@PathVariable @NonNull Long id,
            @AuthenticationPrincipal UserPrincipal principal) {
        User user = principal.getUser();
        Client userClient = user.getClient();
        if (userClient == null) return ResponseEntity.status(403).build();

        return batchService.findByIdWithFiles(id)
                .filter(batch -> batch.getClient().getId().equals(userClient.getId()))
                .map(ResponseEntity::ok)
                .orElse(ResponseEntity.notFound().build());
    }

    @PostMapping("/upload")
    public ResponseEntity<?> uploadBatch(@RequestParam MultipartFile file,
            @AuthenticationPrincipal UserPrincipal principal) {
        User user = principal.getUser();
        Client client = user.getClient();

        if (client == null) {
            return ResponseEntity.badRequest().body(Map.of("error", "No client organization assigned"));
        }

        if (file.isEmpty()) {
            return ResponseEntity.badRequest().body(Map.of("error", "Please select a file to upload"));
        }

        String filename = file.getOriginalFilename();
        if (filename == null || !filename.toLowerCase().endsWith(".zip")) {
            return ResponseEntity.badRequest().body(Map.of("error", "Please upload a ZIP file"));
        }

        try {
            Batch batch = batchService.createFromZip(file, client, user);
            auditLogService.logEntity(user, "BATCH_UPLOADED_API", "Batch", batch.getId());

            Map<String, Object> response = new HashMap<>();
            response.put("success", true);
            response.put("batchId", batch.getId());
            response.put("parentBatchId", batch.getParentBatchId());
            response.put("fileCount", batch.getFiles().size());
            response.put("status", batch.getStatus());

            return ResponseEntity.ok(response);
        } catch (Exception e) {
            return ResponseEntity.badRequest().body(Map.of("error", "Upload failed: " + e.getMessage()));
        }
    }

    @GetMapping("/{id}/status")
    public ResponseEntity<?> getBatchStatus(@PathVariable @NonNull Long id,
            @AuthenticationPrincipal UserPrincipal principal) {
        User user = principal.getUser();
        Client userClient = user.getClient();
        if (userClient == null) return ResponseEntity.status(403).build();

        return batchService.getStatusInfo(id, userClient.getId())
                .<ResponseEntity<?>>map(ResponseEntity::ok)
                .orElse(ResponseEntity.notFound().build());
    }
}
