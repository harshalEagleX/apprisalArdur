package com.shal.batch.controller.api;

import com.shal.common.dto.BatchStatusView;
import com.shal.common.entity.*;
import com.shal.batch.service.BatchService;
import com.shal.common.service.AuditLogService;
import com.shal.common.security.UserPrincipal;
import com.shal.common.repository.BatchRepository;
import com.shal.common.repository.ClientRepository;
import com.shal.common.util.TimelineLog;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
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
import java.util.Optional;

/**
 * REST API for batch operations — ADMIN only.
 */
@RestController
@RequestMapping("/api/admin/batches")
@PreAuthorize("hasRole('ADMIN')")
public class BatchApiController {

    private static final Logger log = LoggerFactory.getLogger(BatchApiController.class);

    private final BatchService batchService;
    private final AuditLogService auditLogService;
    private final ClientRepository clientRepository;
    private final BatchRepository batchRepository;

    public BatchApiController(BatchService batchService,
                              AuditLogService auditLogService,
                              ClientRepository clientRepository,
                              BatchRepository batchRepository) {
        this.batchService = batchService;
        this.auditLogService = auditLogService;
        this.clientRepository = clientRepository;
        this.batchRepository = batchRepository;
    }

    /**
     * Client-isolation guard.
     *
     * An admin with no client assigned is a super-admin (full access).
     * An admin whose account is scoped to a specific client may only act on
     * batches belonging to that client — prevents horizontal privilege escalation
     * where one client's admin deletes or views another client's appraisal data.
     */
    private Optional<ResponseEntity<?>> assertClientAccess(User admin, Long batchId) {
        Client adminClient = admin.getClient();
        if (adminClient == null) {
            return Optional.empty(); // super-admin: no restriction
        }
        return batchRepository.findByIdWithClient(batchId).map(batch -> {
            if (batch.getClient() == null || !adminClient.getId().equals(batch.getClient().getId())) {
                return Optional.<ResponseEntity<?>>of(ResponseEntity.status(403)
                        .body(Map.of("error", "ACCESS_DENIED",
                                "message", "You do not have access to this batch.")));
            }
            return Optional.<ResponseEntity<?>>empty();
        }).orElse(Optional.of(ResponseEntity.notFound().build()));
    }

    /**
     * Returns paginated batch list as a stable JSON structure.
     *
     * Spring Data's PageImpl serialization is not stable — it produces different
     * JSON across versions. We return an explicit Map instead to avoid the
     * "Serializing PageImpl instances as-is is not supported" warning and
     * to guarantee a consistent shape for the frontend.
     *
     * Each batch item includes fileCount (denormalized column — no lazy-load required)
     * so the frontend gets accurate file counts without loading the full files list.
     */
    @GetMapping
    public ResponseEntity<?> getBatches(
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size,
            @RequestParam(required = false) String status,
            @RequestParam(required = false) String search) {
        long started = System.nanoTime();

        BatchStatus batchStatus = null;
        if (status != null && !status.isBlank()) {
            try {
                batchStatus = BatchStatus.valueOf(status.toUpperCase());
            } catch (IllegalArgumentException e) {
                return ResponseEntity.badRequest().body(Map.of("error", "Unknown status: " + status));
            }
        }

        Page<Batch> batchPage = (batchStatus != null || (search != null && !search.isBlank()))
                ? batchService.searchAdminBatches(batchStatus, search, PageRequest.of(page, size, Sort.by("createdAt").descending()))
                : batchService.findAll(PageRequest.of(page, size, Sort.by("createdAt").descending()));

        log.info(TimelineLog.event("admin_batches", "java_list_served",
                "page", page,
                "size", size,
                "status_filter", status,
                "search", search,
                "returned", batchPage.getContent().size(),
                "total_elements", batchPage.getTotalElements(),
                "elapsed_ms", TimelineLog.elapsedMs(started)));
        return ResponseEntity.ok(Map.of(
            "content",       batchPage.getContent().stream().map(b -> toSummary(b, false)).toList(),
            "totalPages",    batchPage.getTotalPages(),
            "number",        batchPage.getNumber(),
            "totalElements", batchPage.getTotalElements()
        ));
    }

    /**
     * Converts a Batch to a summary map for the list API.
     * Uses denormalized fileCount column — no lazy-loading of the files collection required.
     */
    private Map<String, Object> toSummary(Batch b, boolean includeFiles) {
        Map<String, Object> m = new HashMap<>();
        m.put("id",            b.getId());
        m.put("parentBatchId", b.getParentBatchId());
        m.put("status",        b.getStatus() != null ? b.getStatus().name() : null);
        m.put("errorMessage",  b.getErrorMessage());
        m.put("intakeWarnings", b.getIntakeWarnings());
        m.put("fileHash",      b.getFileHash());
        m.put("createdAt",     b.getCreatedAt() != null ? b.getCreatedAt().toString() : null);
        m.put("updatedAt",     b.getUpdatedAt() != null ? b.getUpdatedAt().toString() : null);
        // fileCount from denormalized column — always accurate, no lazy-load required
        m.put("fileCount", b.getFileCount());
        if (includeFiles) {
            m.put("files", b.getFiles().stream().map(f -> {
                Map<String, Object> fm = new HashMap<>();
                fm.put("id",                   f.getId());
                fm.put("filename",              f.getFilename());
                fm.put("fileType",              f.getFileType() != null ? f.getFileType().name() : "");
                fm.put("fileSize",              f.getFileSize() != null ? f.getFileSize() : 0L);
                fm.put("status",                f.getStatus() != null ? f.getStatus().name() : "");
                fm.put("orderId",               f.getOrderId() != null ? f.getOrderId() : "");
                fm.put("documentQualityFlags",  f.getDocumentQualityFlags());
                return fm;
            }).toList());
        } else {
            // Do NOT touch b.getFiles() here — the Hibernate session is closed after findAll()
            // returns (open-in-view=false). fileCount column has the accurate count.
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
    public ResponseEntity<?> getBatch(
            @PathVariable @NonNull Long id,
            @AuthenticationPrincipal UserPrincipal principal) {
        Optional<ResponseEntity<?>> denied = assertClientAccess(principal.getUser(), id);
        if (denied.isPresent()) return denied.get();
        return batchService.findByIdWithFiles(id)
                .map(b -> ResponseEntity.ok(toSummary(b, true)))
                .orElse(ResponseEntity.notFound().build());
    }

    @GetMapping("/{id}/status")
    public ResponseEntity<?> getBatchStatus(
            @PathVariable @NonNull Long id,
            @AuthenticationPrincipal UserPrincipal principal) {
        long started = System.nanoTime();
        Optional<ResponseEntity<?>> denied = assertClientAccess(principal.getUser(), id);
        if (denied.isPresent()) return denied.get();
        // Single query replaces: batch load + countByBatchIdAndFileType + countByBatchId
        BatchStatusView view = batchRepository.findStatusById(id);
        ResponseEntity<?> response;
        if (view == null) {
            response = ResponseEntity.notFound().build();
        } else {
            response = ResponseEntity.ok(Map.of(
                    "batchId",              view.getBatchId(),
                    "status",               view.getStatus() != null ? view.getStatus().name() : null,
                    "totalFiles",           view.getTotalFiles(),
                    "processingTotalFiles", view.getProcessingTotalFiles(),
                    "completedFiles",       view.getCompletedFiles(),
                    "errorMessage",         view.getErrorMessage() != null ? view.getErrorMessage() : "",
                    "updatedAt",            view.getUpdatedAt() != null ? view.getUpdatedAt().toString() : null
            ));
        }
        log.info(TimelineLog.event("admin_batches", "java_status_served",
                "batch_id", id,
                "http_status", response.getStatusCode().value(),
                "elapsed_ms", TimelineLog.elapsedMs(started)));
        return response;
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
        long started = System.nanoTime();

        User admin = principal.getUser();
        log.info(TimelineLog.event("admin_batches", "java_upload_request",
                "client_id", clientId,
                "user", admin.getUsername(),
                "zip_name", file.getOriginalFilename(),
                "zip_bytes", file.getSize()));

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
            log.info(TimelineLog.event("admin_batches", "java_upload_response",
                    "batch_id", batch.getId(),
                    "batch_ref", batch.getParentBatchId(),
                    "status", batch.getStatus(),
                    "file_count", batch.getFileCount(),
                    "elapsed_ms", TimelineLog.elapsedMs(started)));
            return ResponseEntity.ok(response);
        } catch (Exception e) {
            log.warn(TimelineLog.event("admin_batches", "java_upload_failed",
                    "client_id", clientId,
                    "zip_name", file.getOriginalFilename(),
                    "elapsed_ms", TimelineLog.elapsedMs(started),
                    "error", e.getMessage()));
            return ResponseEntity.badRequest().body(Map.of("error", "Upload failed: " + e.getMessage()));
        }
    }

    /**
     * Delete a batch. Soft by default — the batch disappears from the app but its
     * data and audit trail are preserved. A hard purge (irreversible) requires the
     * explicit {@code hard=true} flag, which the UI gates behind a second
     * confirmation.
     */
    @DeleteMapping("/{id}")
    public ResponseEntity<?> deleteBatch(
            @PathVariable @NonNull Long id,
            @RequestParam(name = "hard", defaultValue = "false") boolean hard,
            @AuthenticationPrincipal UserPrincipal principal) {
        Optional<ResponseEntity<?>> denied = assertClientAccess(principal.getUser(), id);
        if (denied.isPresent()) return denied.get();
        try {
            if (hard) {
                batchService.deleteBatch(id);
                auditLogService.logEntity(principal.getUser(), "BATCH_HARD_DELETED", "Batch", id);
            } else {
                batchService.softDeleteBatch(id, principal.getUser().getId());
                auditLogService.logEntity(principal.getUser(), "BATCH_SOFT_DELETED", "Batch", id);
            }
            return ResponseEntity.ok(Map.of("success", true, "hard", hard));
        } catch (Exception e) {
            return ResponseEntity.badRequest().body(Map.of("error", e.getMessage()));
        }
    }
}
