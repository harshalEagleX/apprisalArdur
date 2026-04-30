package com.apprisal.batch.controller.api;

import com.apprisal.common.entity.*;
import com.apprisal.batch.service.BatchService;
import com.apprisal.common.service.AuditLogService;
import com.apprisal.common.security.UserPrincipal;
import com.apprisal.common.repository.BatchFileRepository;
import com.apprisal.common.repository.ClientRepository;
import com.apprisal.common.repository.QCResultRepository;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.lang.NonNull;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * REST API for batch operations — ADMIN only.
 */
@RestController
@RequestMapping("/api/admin/batches")
@PreAuthorize("hasRole('ADMIN')")
public class BatchApiController {

    private final BatchService batchService;
    private final AuditLogService auditLogService;
    private final ClientRepository clientRepository;
    private final BatchFileRepository batchFileRepository;
    private final QCResultRepository qcResultRepository;

    public BatchApiController(BatchService batchService,
                              AuditLogService auditLogService,
                              ClientRepository clientRepository,
                              BatchFileRepository batchFileRepository,
                              QCResultRepository qcResultRepository) {
        this.batchService = batchService;
        this.auditLogService = auditLogService;
        this.clientRepository = clientRepository;
        this.batchFileRepository = batchFileRepository;
        this.qcResultRepository = qcResultRepository;
    }

    /**
     * Returns paginated batch list as a stable JSON structure.
     *
     * Spring Data's PageImpl serialization is not stable — it produces different
     * JSON across versions. We return an explicit Map instead to avoid the
     * "Serializing PageImpl instances as-is is not supported" warning and
     * to guarantee a consistent shape for the frontend.
     *
     * Each batch item includes fileCount (from @Formula — no lazy-load required)
     * so the frontend gets accurate file counts without loading the full files list.
     */
    @GetMapping
    public ResponseEntity<?> getBatches(
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size,
            @RequestParam(required = false) String status) {

        Page<Batch> batchPage;
        if (status != null && !status.isBlank()) {
            try {
                BatchStatus batchStatus = BatchStatus.valueOf(status.toUpperCase());
                List<Batch> list = batchService.findByStatus(batchStatus);
                return ResponseEntity.ok(Map.of(
                    "content", list.stream().map(b -> toSummary(b, false)).toList(),
                    "totalPages", 1,
                    "number", 0,
                    "totalElements", list.size()
                ));
            } catch (IllegalArgumentException e) {
                return ResponseEntity.badRequest().body(Map.of("error", "Unknown status: " + status));
            }
        }

        batchPage = batchService.findAll(PageRequest.of(page, size, Sort.by("createdAt").descending()));

        return ResponseEntity.ok(Map.of(
            "content",       batchPage.getContent().stream().map(b -> toSummary(b, false)).toList(),
            "totalPages",    batchPage.getTotalPages(),
            "number",        batchPage.getNumber(),
            "totalElements", batchPage.getTotalElements()
        ));
    }

    /**
     * Converts a Batch to a summary map for the list API.
     * Uses @Formula fileCount — no lazy-loading of the files collection required.
     */
    private Map<String, Object> toSummary(Batch b, boolean includeFiles) {
        Map<String, Object> m = new HashMap<>();
        m.put("id",            b.getId());
        m.put("parentBatchId", b.getParentBatchId());
        m.put("status",        b.getStatus() != null ? b.getStatus().name() : null);
        m.put("errorMessage",  b.getErrorMessage());
        m.put("fileHash",      b.getFileHash());
        m.put("createdAt",     b.getCreatedAt() != null ? b.getCreatedAt().toString() : null);
        m.put("updatedAt",     b.getUpdatedAt() != null ? b.getUpdatedAt().toString() : null);
        // fileCount from @Formula — always accurate, no lazy-load required
        m.put("fileCount", b.getFileCount());
        if (includeFiles) {
            m.put("files", b.getFiles().stream().map(f -> Map.of(
                "id",       f.getId(),
                "filename", f.getFilename(),
                "fileType", f.getFileType() != null ? f.getFileType().name() : "",
                "fileSize", f.getFileSize() != null ? f.getFileSize() : 0L,
                "status",   f.getStatus() != null ? f.getStatus().name() : "",
                "orderId",  f.getOrderId() != null ? f.getOrderId() : ""
            )).toList());
        } else {
            // Do NOT touch b.getFiles() here — the Hibernate session is closed after findAll()
            // returns (open-in-view=false). Use fileCount for the count display.
            m.put("files", List.of());
        }
        // Embed reviewer
        if (b.getAssignedReviewer() != null) {
            m.put("assignedReviewer", Map.of(
                "id",       b.getAssignedReviewer().getId(),
                "username", b.getAssignedReviewer().getUsername(),
                "fullName", b.getAssignedReviewer().getFullName() != null ? b.getAssignedReviewer().getFullName() : ""
            ));
        } else {
            m.put("assignedReviewer", null);
        }
        // Embed client
        if (b.getClient() != null) {
            m.put("client", Map.of(
                "id",   b.getClient().getId(),
                "name", b.getClient().getName() != null ? b.getClient().getName() : "",
                "code", b.getClient().getCode() != null ? b.getClient().getCode() : ""
            ));
        } else {
            m.put("client", null);
        }
        return m;
    }

    @GetMapping("/{id}")
    public ResponseEntity<?> getBatch(@PathVariable @NonNull Long id) {
        return batchService.findByIdWithFiles(id)
                .map(b -> ResponseEntity.ok(toSummary(b, true)))
                .orElse(ResponseEntity.notFound().build());
    }

    @GetMapping("/{id}/status")
    public ResponseEntity<?> getBatchStatus(@PathVariable @NonNull Long id) {
        return batchService.findById(id)
                .map(b -> ResponseEntity.ok(Map.of(
                        "batchId",      b.getId(),
                        "status",       b.getStatus() != null ? b.getStatus().name() : null,
                        "totalFiles",   b.getFileCount(),
                        "processingTotalFiles", batchFileRepository.countByBatchIdAndFileType(id, FileType.APPRAISAL),
                        "completedFiles", qcResultRepository.countByBatchId(id),
                        "errorMessage", b.getErrorMessage() != null ? b.getErrorMessage() : "",
                        "updatedAt",    b.getUpdatedAt() != null ? b.getUpdatedAt().toString() : null
                )))
                .orElse(ResponseEntity.notFound().build());
    }

    /**
     * Upload a ZIP batch. Requires multipart/form-data:
     *   file     — the ZIP archive
     *   clientId — ID of the tenant organisation
     */
    @PostMapping("/upload")
    public ResponseEntity<?> uploadBatch(
            @RequestParam MultipartFile file,
            @RequestParam @NonNull Long clientId,
            @AuthenticationPrincipal UserPrincipal principal) {

        User admin = principal.getUser();

        if (file.isEmpty()) {
            return ResponseEntity.badRequest().body(Map.of("error", "File is required"));
        }
        String filename = file.getOriginalFilename();
        if (filename == null || !filename.toLowerCase().endsWith(".zip")) {
            return ResponseEntity.badRequest().body(Map.of("error", "Only ZIP files are accepted"));
        }

        Client client = clientRepository.findById(clientId).orElse(null);
        if (client == null) {
            return ResponseEntity.badRequest().body(Map.of("error", "Client organisation not found: " + clientId));
        }

        try {
            Batch batch = batchService.createFromZip(file, client, admin);
            auditLogService.logEntity(admin, "BATCH_UPLOADED", "Batch", batch.getId());

            Map<String, Object> response = new HashMap<>();
            response.put("success",       true);
            response.put("batchId",        batch.getId());
            response.put("parentBatchId",  batch.getParentBatchId());
            response.put("fileCount",      batch.getFileCount());
            response.put("status",         batch.getStatus() != null ? batch.getStatus().name() : null);
            return ResponseEntity.ok(response);
        } catch (Exception e) {
            return ResponseEntity.badRequest().body(Map.of("error", "Upload failed: " + e.getMessage()));
        }
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<?> deleteBatch(
            @PathVariable @NonNull Long id,
            @AuthenticationPrincipal UserPrincipal principal) {
        try {
            batchService.deleteBatch(id);
            auditLogService.logEntity(principal.getUser(), "BATCH_DELETED", "Batch", id);
            return ResponseEntity.ok(Map.of("success", true));
        } catch (Exception e) {
            return ResponseEntity.badRequest().body(Map.of("error", e.getMessage()));
        }
    }
}
