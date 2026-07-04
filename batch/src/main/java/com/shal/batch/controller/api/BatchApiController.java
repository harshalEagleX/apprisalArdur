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

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
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
     * The exact set of batch statuses the backend recognises, in declaration order.
     * The admin filter dropdown sources its options from here so the two can never
     * drift — a status added to (or removed from) {@link BatchStatus} shows up in the
     * filter with no frontend change, and the filter can never offer a value the
     * backend would reject with "Unknown status".
     */
    @GetMapping("/statuses")
    public ResponseEntity<List<String>> getStatuses() {
        return ResponseEntity.ok(
                java.util.Arrays.stream(BatchStatus.values()).map(Enum::name).toList());
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
            List<Map<String, Object>> fileDtos = b.getFiles().stream().map(f -> {
                Map<String, Object> fm = new HashMap<>();
                fm.put("id",                   f.getId());
                fm.put("filename",              f.getFilename());
                fm.put("fileType",              f.getFileType() != null ? f.getFileType().name() : "");
                fm.put("fileSize",              f.getFileSize() != null ? f.getFileSize() : 0L);
                fm.put("status",                f.getStatus() != null ? f.getStatus().name() : "");
                fm.put("orderId",               f.getOrderId() != null ? f.getOrderId() : "");
                fm.put("propertySetName",       f.getPropertySetName());
                fm.put("documentQualityFlags",  f.getDocumentQualityFlags());
                // Resolved Order (AppraisalTransaction) link — null for legacy files
                // ingested before Order resolution existed (run the backfill to fix).
                fm.put("resolvedOrderId",       f.getOrder() != null ? f.getOrder().getId() : null);
                fm.put("orderDocumentStatus",   f.getOrder() != null ? f.getOrder().getDocumentStatus().name() : null);
                return fm;
            }).toList();
            m.put("files", fileDtos);

            // Group files by resolved Order (falling back to the raw propertySetName
            // string for legacy files with no resolved order yet) → propertySets list
            // for the detail view. Sets are ordered by their first occurrence.
            java.util.LinkedHashMap<String, List<Map<String, Object>>> setMap = new java.util.LinkedHashMap<>();
            for (Map<String, Object> f : fileDtos) {
                Object resolvedOrderId = f.get("resolvedOrderId");
                String setKey = (String) f.get("propertySetName");
                setKey = setKey != null && !setKey.isBlank() ? setKey : null;
                String bucket = resolvedOrderId != null ? ("order:" + resolvedOrderId) : (setKey != null ? setKey : "__root__");
                setMap.computeIfAbsent(bucket, k -> new ArrayList<>()).add(f);
            }
            List<Map<String, Object>> propertySets = setMap.entrySet().stream().map(entry -> {
                List<Map<String, Object>> setFiles = entry.getValue();
                Object resolvedOrderId = setFiles.stream().map(f -> f.get("resolvedOrderId")).filter(Objects::nonNull).findFirst().orElse(null);
                Object orderDocumentStatus = setFiles.stream().map(f -> f.get("orderDocumentStatus")).filter(Objects::nonNull).findFirst().orElse(null);
                String displaySetName = setFiles.stream()
                        .map(f -> (String) f.get("propertySetName"))
                        .filter(n -> n != null && !n.isBlank())
                        .findFirst().orElse(null);
                Map<String, Object> ps = new HashMap<>();
                ps.put("setName",      displaySetName);
                ps.put("orderId",      resolvedOrderId);
                ps.put("documentStatus", orderDocumentStatus);
                ps.put("files",        setFiles);
                ps.put("fileCount",    setFiles.size());
                ps.put("completedCount",        setFiles.stream().filter(f -> "COMPLETED".equals(f.get("status"))).count());
                ps.put("errorCount",            setFiles.stream().filter(f -> "ERROR".equals(f.get("status"))).count());
                ps.put("pendingCount",          setFiles.stream().filter(f -> "PENDING".equals(f.get("status"))).count());
                ps.put("needsAssignmentCount",  setFiles.stream().filter(f -> "NEEDS_ASSIGNMENT".equals(f.get("status"))).count());
                return ps;
            }).toList();
            m.put("propertySets", propertySets);
            m.put("setCount", (long) setMap.entrySet().stream().filter(e -> !"__root__".equals(e.getKey())).count());
            // Surface unassigned files at the batch level so the admin UI can show
            // the "Assign" panel without having to dig into each property set.
            long needsAssignmentTotal = fileDtos.stream()
                    .filter(f -> "NEEDS_ASSIGNMENT".equals(f.get("status"))).count();
            m.put("needsAssignmentCount", needsAssignmentTotal);
            if (needsAssignmentTotal > 0) {
                m.put("unassignedFiles", fileDtos.stream()
                        .filter(f -> "NEEDS_ASSIGNMENT".equals(f.get("status")))
                        .toList());
            } else {
                m.put("unassignedFiles", List.of());
            }
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
        } catch (com.shal.common.exception.BatchStructureException e) {
            log.info(TimelineLog.event("admin_batches", "java_upload_rejected_structure",
                    "client_id", clientId,
                    "zip_name", file.getOriginalFilename(),
                    "issue_count", e.getIssues().size(),
                    "elapsed_ms", TimelineLog.elapsedMs(started)));
            // 422 with the fixable issue list — the ZIP is rejected, nothing is queued.
            return ResponseEntity.unprocessableEntity().body(Map.of(
                    "error", e.getMessage(),
                    "issues", e.getIssues()));
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
     * Dismiss a permanently-failing appraisal file as unreviewable.
     *
     * Sets FileStatus → DISMISSED so the batch can complete without retrying a file
     * that will never succeed (corrupt scan, unreadable PDF). This is the terminal
     * "give up on this file" action. The file row is kept for audit; DISMISSED files
     * are excluded from the completion gate in recomputeBatchStatusFromActiveResults.
     *
     * Only available for files in ERROR status. Admins only (enforced by SecurityConfig).
     */
    @PostMapping("/{batchId}/files/{fileId}/dismiss-error")
    public ResponseEntity<?> dismissFileError(
            @PathVariable @NonNull Long batchId,
            @PathVariable @NonNull Long fileId,
            @AuthenticationPrincipal UserPrincipal principal) {
        Optional<ResponseEntity<?>> denied = assertClientAccess(principal.getUser(), batchId);
        if (denied.isPresent()) return denied.get();
        try {
            batchService.dismissFileError(fileId, principal.getUser().getId());
            return ResponseEntity.ok(Map.of(
                    "success", true,
                    "fileId", fileId,
                    "status", "DISMISSED",
                    "message", "File marked as permanently unreviewable. The batch can now complete."));
        } catch (IllegalStateException e) {
            return ResponseEntity.badRequest().body(Map.of("error", e.getMessage()));
        } catch (Exception e) {
            log.error("Failed to dismiss file error for file {}: {}", fileId, e.getMessage(), e);
            return ResponseEntity.status(500).body(Map.of("error", "Dismiss failed: " + e.getMessage()));
        }
    }

    /**
     * Manually assign a supporting file to a specific appraisal in the same batch.
     *
     * This is the resolution path for NEEDS_ASSIGNMENT files — those that could not
     * be auto-matched at intake because their filename has no link to an appraisal
     * (e.g. "EngagementLetter 2.pdf" in a 3-order batch).
     *
     * Creates a DocumentMatch(manual_admin, confidence=1.0) that FileMatchingService
     * always honours and never overwrites during Re-QC. After assigning, trigger
     * Re-QC on the appraisal to include the newly paired document.
     *
     * Body: { "appraisalFileId": <Long>, "force": <boolean, optional> }
     *
     * force=false (default) runs content cross-validation: if the document's own
     * text confidently identifies it as belonging to a DIFFERENT order in this
     * batch, the assignment is rejected with error "ADDRESS_MISMATCH" so the admin
     * can re-check before resubmitting with force=true to override.
     */
    @PostMapping("/{batchId}/files/{fileId}/assign")
    public ResponseEntity<?> assignFileToAppraisal(
            @PathVariable @NonNull Long batchId,
            @PathVariable @NonNull Long fileId,
            @RequestBody Map<String, Object> body,
            @AuthenticationPrincipal UserPrincipal principal) {
        Optional<ResponseEntity<?>> denied = assertClientAccess(principal.getUser(), batchId);
        if (denied.isPresent()) return denied.get();
        Object raw = body.get("appraisalFileId");
        if (raw == null) {
            return ResponseEntity.badRequest().body(Map.of("error", "appraisalFileId is required"));
        }
        Long appraisalFileId;
        try {
            appraisalFileId = Long.parseLong(raw.toString());
        } catch (NumberFormatException e) {
            return ResponseEntity.badRequest().body(Map.of("error", "appraisalFileId must be a number"));
        }
        boolean force = Boolean.TRUE.equals(body.get("force")) || "true".equals(String.valueOf(body.get("force")));
        try {
            batchService.manuallyAssignFile(fileId, appraisalFileId, batchId, principal.getUser(), force);
            return ResponseEntity.ok(Map.of(
                    "success", true,
                    "fileId", fileId,
                    "appraisalFileId", appraisalFileId,
                    "message", "File assigned. Run Re-QC on the appraisal to include this document."));
        } catch (com.shal.common.exception.ValidationException e) {
            if ("addressMismatch".equals(e.getField())) {
                return ResponseEntity.status(409).body(Map.of(
                        "error", "ADDRESS_MISMATCH",
                        "message", e.getMessage()));
            }
            log.warn("Manual assign failed: batchId={} fileId={} appraisalFileId={} error={}",
                    batchId, fileId, appraisalFileId, e.getMessage());
            return ResponseEntity.badRequest().body(Map.of("error", e.getMessage()));
        } catch (Exception e) {
            log.warn("Manual assign failed: batchId={} fileId={} appraisalFileId={} error={}",
                    batchId, fileId, appraisalFileId, e.getMessage());
            return ResponseEntity.badRequest().body(Map.of("error", e.getMessage()));
        }
    }

    /**
     * Change a file's document type.
     *
     * Used when intake classification was wrong — most commonly a MISMO XML that
     * landed outside the appraisal/ folder and was classified as CONTRACT. After
     * reclassifying, run Re-QC so the corrected type is picked up by matching.
     *
     * Body: { "fileType": "APPRAISAL_XML" }
     */
    @PostMapping("/{batchId}/files/{fileId}/reclassify")
    public ResponseEntity<?> reclassifyFile(
            @PathVariable @NonNull Long batchId,
            @PathVariable @NonNull Long fileId,
            @RequestBody Map<String, Object> body,
            @AuthenticationPrincipal UserPrincipal principal) {
        Optional<ResponseEntity<?>> denied = assertClientAccess(principal.getUser(), batchId);
        if (denied.isPresent()) return denied.get();
        String typeStr = body.get("fileType") instanceof String s ? s : null;
        if (typeStr == null || typeStr.isBlank()) {
            return ResponseEntity.badRequest().body(Map.of("error", "fileType is required"));
        }
        FileType newType;
        try {
            newType = FileType.valueOf(typeStr.toUpperCase());
        } catch (IllegalArgumentException e) {
            return ResponseEntity.badRequest().body(Map.of(
                    "error", "Unknown fileType: " + typeStr,
                    "valid", java.util.Arrays.stream(FileType.values()).map(Enum::name).toList()));
        }
        try {
            batchService.reclassifyFile(fileId, batchId, newType, principal.getUser());
            return ResponseEntity.ok(Map.of(
                    "success", true,
                    "fileId", fileId,
                    "newType", newType.name(),
                    "message", "File reclassified to " + newType.name() + ". Run Re-QC to apply."));
        } catch (Exception e) {
            log.warn("Reclassify failed: batchId={} fileId={} type={} error={}",
                    batchId, fileId, typeStr, e.getMessage());
            return ResponseEntity.badRequest().body(Map.of("error", e.getMessage()));
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
