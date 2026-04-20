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

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;

/**
 * REST API Controller for batch operations.
 */
@RestController
@RequestMapping("/api/client/batches")
@Tag(name = "Client Batch API", description = "Operations for clients to upload and view their data batches")
public class BatchApiController {

    private final BatchService batchService;

    public BatchApiController(BatchService batchService) {
        this.batchService = batchService;
    }

    @Operation(summary = "Get paginated client batches", description = "Retrieves batches assigned to the current client's organization")
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

    @Operation(summary = "Get specific batch details", description = "Retrieve a single batch. Ensures client authorization")
    @GetMapping("/{id}")
    public ResponseEntity<?> getBatch(@PathVariable @NonNull Long id,
            @AuthenticationPrincipal UserPrincipal principal) {
        User user = principal.getUser();

        return batchService.findById(id)
                .filter(batch -> {
                    // Security check: ensure batch belongs to user's client
                    Client userClient = user.getClient();
                    return userClient != null && batch.getClient().getId().equals(userClient.getId());
                })
                .map(ResponseEntity::ok)
                .orElse(ResponseEntity.notFound().build());
    }

    @Operation(summary = "Upload a new batch", description = "Uploads a zip file containing files for a new batch context")
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

    @Operation(summary = "Get batch processing status", description = "Retrieve the current processing and OCR status of a batch")
    @GetMapping("/{id}/status")
    public ResponseEntity<?> getBatchStatus(@PathVariable @NonNull Long id,
            @AuthenticationPrincipal UserPrincipal principal) {
        User user = principal.getUser();

        return batchService.findById(id)
                .filter(batch -> {
                    Client userClient = user.getClient();
                    return userClient != null && batch.getClient().getId().equals(userClient.getId());
                })
                .map(batch -> {
                    Map<String, Object> status = new HashMap<>();
                    status.put("batchId", batch.getId());
                    status.put("parentBatchId", batch.getParentBatchId());
                    status.put("status", batch.getStatus());
                    status.put("totalFiles", batch.getFiles().size());

                    long pendingFiles = batch.getFiles().stream()
                            .filter(f -> f.getStatus() == FileStatus.PENDING)
                            .count();
                    long completedFiles = batch.getFiles().stream()
                            .filter(f -> f.getStatus() == FileStatus.COMPLETED)
                            .count();

                    status.put("pendingFiles", pendingFiles);
                    status.put("completedFiles", completedFiles);
                    status.put("updatedAt", batch.getUpdatedAt());

                    return ResponseEntity.ok(status);
                })
                .orElse(ResponseEntity.notFound().build());
    }
}
