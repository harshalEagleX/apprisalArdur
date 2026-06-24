package com.shal.batch.service;

import com.shal.common.entity.*;
import com.shal.common.exception.BatchProcessingException;
import com.shal.common.exception.ResourceNotFoundException;
import com.shal.common.exception.ValidationException;
import com.shal.common.repository.BatchFileRepository;
import com.shal.common.repository.BatchRepository;
import com.shal.common.repository.DocumentMatchRepository;
import com.shal.common.repository.ProcessingMetricsRepository;
import com.shal.common.repository.QCResultRepository;
import com.shal.common.repository.QCRuleResultRepository;
import com.shal.common.service.AuditLogService;
import com.shal.common.service.BusinessEventService;
import com.shal.common.service.FileMatchingService;
import com.shal.common.util.AppTime;
import com.shal.common.util.TimelineLog;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;
import java.util.Objects;
import org.springframework.lang.NonNull;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

/**
 * Service for managing batch uploads and processing.
 */
@Service
@SuppressWarnings("unused")
public class BatchService {

    private static final Logger log = LoggerFactory.getLogger(BatchService.class);
    private static final int MAX_ZIP_ENTRIES = 1000;

    private final BatchRepository batchRepository;
    private final BatchFileRepository batchFileRepository;
    private final QCResultRepository qcResultRepository;
    private final QCRuleResultRepository qcRuleResultRepository;
    private final DocumentMatchRepository documentMatchRepository;
    private final ProcessingMetricsRepository metricsRepository;
    private final com.shal.common.repository.DocStatRepository docStatRepository;
    private final AuditLogService auditLogService;
    private final BusinessEventService businessEventService;

    @Value("${app.storage.path:./uploads}")
    private String storagePath;

    /** Per-file size cap (MB). Files in the ZIP larger than this are excluded with a clear note. */
    @Value("${app.upload.max-file-mb:50}")
    private long maxUploadFileMb;

    public BatchService(BatchRepository batchRepository,
            BatchFileRepository batchFileRepository,
            QCResultRepository qcResultRepository,
            QCRuleResultRepository qcRuleResultRepository,
            DocumentMatchRepository documentMatchRepository,
            ProcessingMetricsRepository metricsRepository,
            com.shal.common.repository.DocStatRepository docStatRepository,
            AuditLogService auditLogService,
            BusinessEventService businessEventService) {
        this.batchRepository = batchRepository;
        this.batchFileRepository = batchFileRepository;
        this.qcResultRepository = qcResultRepository;
        this.qcRuleResultRepository = qcRuleResultRepository;
        this.documentMatchRepository = documentMatchRepository;
        this.metricsRepository = metricsRepository;
        this.docStatRepository = docStatRepository;
        this.auditLogService = auditLogService;
        this.businessEventService = businessEventService;
    }

    @Transactional(readOnly = true)
    public Optional<Batch> findById(@NonNull Long id) {
        return batchRepository.findById(id);
    }

    @Transactional(readOnly = true)
    public Optional<Batch> findByIdWithFiles(@NonNull Long id) {
        return batchRepository.findWithFilesById(id);
    }

    @Transactional(readOnly = true)
    public Optional<Map<String, Object>> getStatusInfo(@NonNull Long batchId, @NonNull Long clientId) {
        return batchRepository.findWithFilesById(batchId)
                .filter(b -> b.getClient().getId().equals(clientId))
                .map(b -> {
                    Map<String, Object> info = new HashMap<>();
                    info.put("batchId", b.getId());
                    info.put("parentBatchId", b.getParentBatchId());
                    info.put("status", b.getStatus());
                    info.put("totalFiles", b.getFiles().size());
                    info.put("pendingFiles",   b.getFiles().stream().filter(f -> f.getStatus() == FileStatus.PENDING).count());
                    info.put("completedFiles", b.getFiles().stream().filter(f -> f.getStatus() == FileStatus.COMPLETED).count());
                    info.put("updatedAt", b.getUpdatedAt());
                    return info;
                });
    }

    @Transactional(readOnly = true)
    public List<Batch> findByClientId(Long clientId) {
        return batchRepository.findByClientId(clientId);
    }

    @Transactional(readOnly = true)
    public Page<Batch> findByClientId(Long clientId, Pageable pageable) {
        return batchRepository.findByClientId(clientId, pageable);
    }

    @Transactional(readOnly = true)
    public List<Batch> findByStatus(BatchStatus status) {
        return batchRepository.findByStatus(status);
    }

    @Transactional(readOnly = true)
    public List<Batch> findByReviewerId(Long reviewerId) {
        return batchRepository.findByAssignedReviewerId(reviewerId);
    }

    @Transactional(readOnly = true)
    public List<Batch> findByReviewerIdAndStatus(Long reviewerId, BatchStatus status) {
        return batchRepository.findByAssignedReviewerIdAndStatus(reviewerId, status);
    }

    @Transactional(readOnly = true)
    public Page<Batch> findByReviewer(Long reviewerId, Pageable pageable) {
        return batchRepository.findByAssignedReviewerId(reviewerId, pageable);
    }

    @Transactional(readOnly = true)
    public List<Batch> findAll() {
        return batchRepository.findAll();
    }

    @Transactional(readOnly = true)
    public Page<Batch> findAll(@NonNull Pageable pageable) {
        return batchRepository.findAll(pageable);
    }

    @Transactional(readOnly = true)
    public Page<Batch> searchAdminBatches(BatchStatus status, String search, @NonNull Pageable pageable) {
        String trimmedSearch = search == null || search.isBlank() ? null : search.trim();
        return batchRepository.searchAdminBatches(status, trimmedSearch, pageable);
    }

    /**
     * Soft-delete a batch: mark it deleted so it disappears from the app (hidden
     * by @SQLRestriction on the Batch entity) while its rows, files, and Envers
     * audit trail are fully preserved. This is the default delete path — a hard
     * purge ({@link #deleteBatch}) is a separate, explicit admin action.
     *
     * @param batchId the batch to soft-delete
     * @param actorId id of the admin performing the deletion (recorded on the row)
     * @throws ResourceNotFoundException if batch not found
     */
    @Transactional
    public void softDeleteBatch(@NonNull Long batchId, Long actorId) {
        Batch batch = batchRepository.findById(batchId)
                .orElseThrow(() -> new ResourceNotFoundException("Batch", "id", batchId));
        batch.setDeletedAt(java.time.LocalDateTime.now());
        batch.setDeletedBy(actorId);
        batchRepository.save(batch);
        log.info("Soft-deleted batch {} (id={}) by user {}", batch.getParentBatchId(), batchId, actorId);
    }

    /**
     * Hard-delete (purge) a batch and all its associated files and QC rows.
     * Irreversible — only invoked on explicit admin confirmation.
     *
     * @param batchId the batch ID to delete
     * @throws ResourceNotFoundException if batch not found
     */
    @Transactional
    public void deleteBatch(@NonNull Long batchId) {
        Batch batch = batchRepository.findById(batchId)
                .orElseThrow(() -> new ResourceNotFoundException("Batch", "id", batchId));

        // Touch both lazy associations NOW, before the bulk @Modifying deletes
        // below fire clearAutomatically=true and evict all entities from the
        // persistence context.  Once evicted, any uninitialized proxy
        // (Client, files) can no longer be resolved — LazyInitializationException.
        // Forcing getCode() / getFiles().size() initialises both proxies into
        // in-memory objects, so they remain accessible after the context clear.
        String clientCode = batch.getClient().getCode();
        int fileCount = batch.getFiles().size();

        long started = System.nanoTime();
        log.info("Deleting batch {} with {} files", batch.getParentBatchId(), fileCount);

        long dbStarted = System.nanoTime();
        int matchesDeleted = documentMatchRepository.deleteByBatchId(batchId);
        int metricsDeleted = metricsRepository.deleteByBatchId(batchId);
        // doc_stat FKs to qc_result, so its tree must be removed before qcResults
        int docStatsDeleted = docStatRepository.deleteTreeByBatchId(batchId);
        int rulesDeleted = qcRuleResultRepository.deleteByBatchId(batchId);
        int resultsDeleted = qcResultRepository.deleteByBatchId(batchId);
        log.info("Deleted batch {} QC rows in {} ms: documentMatches={}, metrics={}, docStats={}, ruleResults={}, qcResults={}",
                batch.getParentBatchId(), elapsedMs(dbStarted), matchesDeleted, metricsDeleted, docStatsDeleted, rulesDeleted, resultsDeleted);

        // Delete storage files
        long filesStarted = System.nanoTime();
        for (BatchFile file : batch.getFiles()) {
            if (file.getStoragePath() != null) {
                try {
                    Path filePath = Paths.get(file.getStoragePath());
                    Files.deleteIfExists(filePath);
                } catch (IOException e) {
                    log.warn("Failed to delete file {}: {}", file.getStoragePath(), e.getMessage());
                }
            }
        }

        // Delete batch storage directory
        try {
            Path batchDir = Paths.get(storagePath, clientCode, batch.getParentBatchId());
            if (Files.exists(batchDir)) {
                try (var paths = Files.walk(batchDir)) {
                    paths.sorted((a, b) -> b.compareTo(a)) // Delete files before directories
                            .forEach(path -> {
                                try {
                                    Files.deleteIfExists(path);
                                } catch (IOException e) {
                                    log.warn("Failed to delete path {}: {}", path, e.getMessage());
                                }
                            });
                }
            }
        } catch (IOException e) {
            log.warn("Failed to clean up batch directory: {}", e.getMessage());
        }
        log.info("Deleted batch {} storage files in {} ms", batch.getParentBatchId(), elapsedMs(filesStarted));

        // Database will cascade delete files due to orphanRemoval.
        long batchDeleteStarted = System.nanoTime();
        batchRepository.delete(batch);
        log.info("Deleted batch {} row in {} ms", batch.getParentBatchId(), elapsedMs(batchDeleteStarted));
        log.info("Batch {} deleted successfully in {} ms", batch.getParentBatchId(), elapsedMs(started));
    }

    /**
     * Process and create a new batch from uploaded ZIP file.
     * 
     * @param file    the ZIP file to process
     * @param client  the client organization
     * @param creator the user creating the batch
     * @return the created batch
     * @throws BatchProcessingException if processing fails
     */
    @Transactional
    @SuppressWarnings("null")
    public Batch createFromZip(MultipartFile file, Client client, User creator) {
        long flowStarted = System.nanoTime();
        if (file == null || file.isEmpty()) {
            throw new ValidationException("file", "File is required");
        }
        if (client == null) {
            throw new ValidationException("client", "Client is required");
        }
        if (creator == null) {
            throw new ValidationException("creator", "Creator is required");
        }

        // Java-side file size guard (50 MB hard limit)
        long maxBytes = 50L * 1024 * 1024;
        if (file.getSize() > maxBytes) {
            throw new ValidationException("file",
                "File exceeds maximum allowed size of 50 MB (received " +
                (file.getSize() / 1024 / 1024) + " MB)");
        }

        // Idempotent deduplication: same ZIP content = same batch
        String fileHash = computeSha256(file);
        if (fileHash != null) {
            var existing = batchRepository.findByFileHash(fileHash);
            if (existing.isPresent()) {
                log.info("Duplicate ZIP detected (hash={}), returning existing batch {}",
                        fileHash, existing.get().getId());
                businessEventService.batchEvent("BATCH_DUPLICATE_UPLOAD", creator, existing.get(), "DUPLICATE",
                        Map.of("file_hash", fileHash));
                return existing.get();
            }
        }

        String originalFilename = file.getOriginalFilename();
        String parentBatchId = originalFilename != null
                ? originalFilename.replace(".zip", "")
                : "BATCH_" + UUID.randomUUID().toString().substring(0, 8).toUpperCase();

        log.info(TimelineLog.event("admin_batches", "java_upload_start",
                "batch_ref", parentBatchId,
                "client_code", client.getCode(),
                "user", creator.getUsername(),
                "zip_name", originalFilename,
                "zip_bytes", file.getSize(),
                "file_hash", fileHash));
        log.info("Creating batch '{}' for client '{}' by user '{}'",
                parentBatchId, client.getCode(), creator.getUsername());

        // Build batch in memory — do NOT save yet.
        // Saving before addFile() would make this a managed entity; Hibernate would
        // then auto-flush the dirty files collection AND cascade-merge on the second
        // save, causing every file to be inserted twice (Bug 1 fix).
        Batch batch = Batch.builder()
                .parentBatchId(parentBatchId)
                .client(client)
                .status(BatchStatus.VALIDATING)
                .createdBy(creator)
                .build();
        batch.setFileHash(fileHash);

        try {
            long extractStarted = System.nanoTime();
            Path batchDir = Paths.get(storagePath, client.getCode(), parentBatchId);
            Files.createDirectories(batchDir);
            extractAndValidateZip(file, batch, batchDir);
            log.info(TimelineLog.event("admin_batches", "java_upload_extracted",
                    "batch_ref", parentBatchId,
                    "client_code", client.getCode(),
                    "file_count", batch.getFiles().size(),
                    "storage_dir", batchDir,
                    "elapsed_ms", TimelineLog.elapsedMs(extractStarted)));
            // UPLOADED = ZIP is valid, files are on disk, waiting for admin to trigger QC.
            // QC_PROCESSING is only set by QCProcessingService when Python is actually called.
            // Setting QC_PROCESSING here was the bug that hid the "Run QC" button forever.
            batch.setStatus(BatchStatus.UPLOADED);
            log.info("Batch '{}' uploaded successfully with {} files — ready for QC",
                    parentBatchId, batch.getFiles().size());
        } catch (ValidationException e) {
            log.warn("Batch validation failed for '{}': {}", parentBatchId, e.getMessage());
            batch.setStatus(BatchStatus.VALIDATION_FAILED);
            batch.setErrorMessage(e.getMessage());
            batchRepository.save(batch); // persist error state so admin can see it
            throw e;
        } catch (IOException e) {
            log.error("IO error processing batch '{}': {}", parentBatchId, e.getMessage(), e);
            batch.setStatus(BatchStatus.VALIDATION_FAILED);
            batch.setErrorMessage("Failed to process ZIP file: " + e.getMessage());
            Long savedId = batchRepository.save(batch).getId();
            throw new BatchProcessingException(savedId, "Failed to process ZIP file: " + e.getMessage(), e);
        } catch (Exception e) {
            log.error("Unexpected error processing batch '{}': {}", parentBatchId, e.getMessage(), e);
            batch.setStatus(BatchStatus.ERROR);
            batch.setErrorMessage("Unexpected error: " + e.getMessage());
            Long savedId = batchRepository.save(batch).getId();
            throw new BatchProcessingException(savedId, "Unexpected error: " + e.getMessage(), e);
        }

        // ONE save in the success path — cascade creates all files atomically
        long saveStarted = System.nanoTime();
        batch = Objects.requireNonNull(batchRepository.save(batch));
        log.info(TimelineLog.event("admin_batches", "java_upload_saved",
                "batch_id", batch.getId(),
                "batch_ref", batch.getParentBatchId(),
                "status", batch.getStatus(),
                "file_count", batch.getFileCount(),
                "save_ms", TimelineLog.elapsedMs(saveStarted),
                "total_elapsed_ms", TimelineLog.elapsedMs(flowStarted)));
        auditLogService.logEntity(creator, "BATCH_UPLOAD", "Batch", batch.getId());
        Map<String, Object> eventPayload = new HashMap<>();
        eventPayload.put("parent_batch_id", batch.getParentBatchId());
        eventPayload.put("client_id", client.getId());
        eventPayload.put("file_count", batch.getFiles().size());
        eventPayload.put("file_hash", fileHash);
        businessEventService.batchEvent("BATCH_CREATED", creator, batch, "UPLOADED", eventPayload);

        return batch;
    }

    private void extractAndValidateZip(MultipartFile file, Batch batch, Path batchDir) throws IOException {
        boolean hasAppraisalFolder = false;
        boolean hasEngagementFolder = false;
        int entryCount = 0;
        // Non-PDF files are catalogued (so nothing is silently dropped) but excluded
        // from the extraction pipeline, which only handles PDFs.
        List<String> excludedNonPdf = new ArrayList<>();
        // Files over the per-file cap (default 50 MB) are excluded with a clear note rather than
        // silently processed — appraisals run 5–50 MB, so this catches corrupt/runaway files.
        List<String> oversizeFiles = new ArrayList<>();

        try (ZipInputStream zis = new ZipInputStream(file.getInputStream())) {
            ZipEntry entry;
            while ((entry = zis.getNextEntry()) != null) {
                entryCount++;
                if (entryCount > MAX_ZIP_ENTRIES) {
                    throw new ValidationException("ZIP file contains too many entries (max: " + MAX_ZIP_ENTRIES + ")");
                }

                String entryName = entry.getName();
                String lowerEntryName = entryName.toLowerCase();

                // Security: prevent path traversal attacks
                if (entryName.contains("..")) {
                    throw new ValidationException("Invalid ZIP entry path: " + entryName);
                }

                // Ignore macOS archive metadata. These often look like PDFs
                // under __MACOSX/.../._file.pdf but are not real documents.
                String filenameOnly = Paths.get(entryName).getFileName() != null
                        ? Paths.get(entryName).getFileName().toString()
                        : entryName;
                if (lowerEntryName.startsWith("__macosx/")
                        || filenameOnly.equals(".DS_Store")
                        || filenameOnly.startsWith("._")) {
                    continue;
                }

                if (entry.isDirectory()) {
                    // Classify only by the folder's own name, not the full path, so a set folder
                    // like "8234 E Pearson_no_appraisal" doesn't falsely set hasAppraisalFolder.
                    String dirSegment = lastPathSegment(entryName).toLowerCase();
                    if (dirSegment.startsWith("appraisal")) hasAppraisalFolder = true;
                    if (dirSegment.startsWith("engagement") || dirSegment.startsWith("eagagement")
                            || dirSegment.equals("order") || dirSegment.equals("orders")) hasEngagementFolder = true;
                    continue;
                }

                if (!entryName.toLowerCase().endsWith(".pdf")) {
                    excludedNonPdf.add(filenameOnly);
                    log.info("Cataloguing non-PDF entry (excluded from extraction): {}", entryName);
                    continue;
                }

                // Classify by the DIRECT PARENT FOLDER name only (the segment immediately
                // containing this PDF), not the full entry path. Using the full path causes
                // misclassification when a set folder name contains type keywords
                // (e.g. "8234 E Pearson_no_appraisal/engagement/order.pdf" would incorrectly
                // become APPRAISAL because "appraisal" appears in the set folder name).
                String parentFolder = directParentFolder(entryName);
                FileType fileType;
                if (parentFolder.startsWith("appraisal")) {
                    fileType = FileType.APPRAISAL;
                    hasAppraisalFolder = true;
                } else if (parentFolder.startsWith("engagement") || parentFolder.startsWith("eagagement")
                        || parentFolder.equals("order") || parentFolder.equals("orders")) {
                    fileType = FileType.ENGAGEMENT;
                    hasEngagementFolder = true;
                } else if (parentFolder.startsWith("contract") || parentFolder.startsWith("purchase")
                        || parentFolder.startsWith("agreement")) {
                    fileType = FileType.CONTRACT;
                } else {
                    continue;
                }

                // Extract the property set name from the ZIP path.
                // e.g. "SHAL-sorted/8234 E Pearson/appraisal/file.pdf" → "8234 E Pearson"
                // e.g. "8234 E Pearson/appraisal/file.pdf" → "8234 E Pearson"
                // e.g. "appraisal/file.pdf" → null
                String propertySetName = extractPropertySetName(entryName);

                String filename = filenameOnly;
                // Store files in a sub-directory keyed by propertySetName (sanitized) so
                // files from different property sets never collide on disk.
                String storageFolderName = propertySetName != null
                        ? sanitizeFolderName(propertySetName) + "/" + fileType.name().toLowerCase()
                        : fileType.name().toLowerCase();
                Path typeDir = batchDir.resolve(storageFolderName);
                Files.createDirectories(typeDir);
                // Two entries can share a filename but hold different content (e.g.
                // two "appraisal.pdf" under different subfolders). Never overwrite —
                // store under a suffixed name and log the collision so both survive.
                Path filePath = uniqueFilePath(typeDir, filename);
                if (!filePath.getFileName().toString().equals(filename)) {
                    log.warn("Filename collision in ZIP: '{}' already present in {} folder — stored as '{}'",
                            filename, storageFolderName, filePath.getFileName());
                    filename = filePath.getFileName().toString();
                }
                Files.copy(zis, filePath, java.nio.file.StandardCopyOption.REPLACE_EXISTING);
                long fileBytes = Files.size(filePath);
                if (fileBytes > maxUploadFileMb * 1024L * 1024L) {
                    Files.deleteIfExists(filePath);
                    oversizeFiles.add(filename + " (" + (fileBytes / (1024 * 1024)) + " MB)");
                    log.warn("Excluding oversize file '{}' ({} MB > {} MB cap) from batch {}",
                            filename, fileBytes / (1024 * 1024), maxUploadFileMb, batch.getParentBatchId());
                    zis.closeEntry();
                    continue;
                }
                String contentHash = computeSha256(filePath);
                String qualityFlags = documentQualityFlags(fileType, filename, contentHash, batch.getFiles(), propertySetName);

                BatchFile batchFile = BatchFile.builder()
                        .batch(batch)
                        .fileType(fileType)
                        .filename(filename)
                        .originalPath(entryName)
                        .storagePath(filePath.toString())
                        .fileSize(Files.size(filePath))
                        .contentHash(contentHash)
                        .contentVersion(1L)
                        .documentQualityFlags(qualityFlags)
                        .status(FileStatus.PENDING)
                        .orderId(FileMatchingService.extractOrderId(filename))
                        .propertySetName(propertySetName)
                        .build();

                batch.addFile(batchFile);
                zis.closeEntry();
            }
        }

        if (!hasAppraisalFolder || !hasEngagementFolder) {
            throw new ValidationException(
                    "Invalid folder structure: requires 'appraisal' and 'engagement' folders");
        }

        if (batch.getFiles().isEmpty()) {
            throw new ValidationException("No valid PDF files found in the batch");
        }

        // If only ONE distinct non-null propertySetName exists, all files are under the
        // same folder — that folder is the batch root, not a meaningful property set.
        // Clear propertySetName so the batch is treated as a flat (single-property) upload.
        Set<String> distinctSets = batch.getFiles().stream()
                .map(BatchFile::getPropertySetName)
                .filter(Objects::nonNull)
                .collect(java.util.stream.Collectors.toSet());
        if (distinctSets.size() <= 1) {
            for (BatchFile f : batch.getFiles()) {
                f.setPropertySetName(null);
            }
        } else {
            log.info("Batch {} has {} distinct property sets: {}",
                    batch.getParentBatchId(), distinctSets.size(), distinctSets);
            // Check each set for completeness and warn about incomplete ones
            warnIncompleteSets(batch, distinctSets);
        }

        flagDocumentRoleAmbiguity(batch);

        if (!excludedNonPdf.isEmpty()) {
            String note = excludedNonPdf.size() + " non-PDF file(s) catalogued and excluded from extraction: "
                    + String.join(", ", excludedNonPdf);
            String existing = batch.getIntakeWarnings();
            batch.setIntakeWarnings(existing == null || existing.isBlank() ? note : existing + "\n" + note);
            log.info("Batch {} catalogued {} non-PDF file(s) excluded from extraction",
                    batch.getParentBatchId(), excludedNonPdf.size());
        }

        if (!oversizeFiles.isEmpty()) {
            String note = oversizeFiles.size() + " file(s) exceeded the " + maxUploadFileMb
                    + " MB per-file cap and were excluded: " + String.join(", ", oversizeFiles);
            String existing = batch.getIntakeWarnings();
            batch.setIntakeWarnings(existing == null || existing.isBlank() ? note : existing + "\n" + note);
            log.warn("Batch {} excluded {} oversize file(s)", batch.getParentBatchId(), oversizeFiles.size());
        }
    }

    /**
     * Flag ambiguous document roles within each property set.
     * Multiple appraisals across different sets is expected (multi-property ZIP).
     * Only warn when a single set has more than one document of the same role.
     */
    private void flagDocumentRoleAmbiguity(Batch batch) {
        // Group files by propertySetName (null → "__root__" for flat ZIPs)
        Map<String, List<BatchFile>> bySet = new HashMap<>();
        for (BatchFile f : batch.getFiles()) {
            String key = f.getPropertySetName() != null ? f.getPropertySetName() : "__root__";
            bySet.computeIfAbsent(key, k -> new ArrayList<>()).add(f);
        }

        List<String> warnings = new ArrayList<>();

        if (bySet.size() > 1) {
            // Multi-set ZIP: inform admin how many property sets were found
            List<String> setNames = bySet.keySet().stream()
                    .filter(k -> !"__root__".equals(k))
                    .sorted()
                    .toList();
            log.info("Batch {} contains {} property sets: {}", batch.getParentBatchId(), setNames.size(), setNames);
        }

        for (Map.Entry<String, List<BatchFile>> entry : bySet.entrySet()) {
            String setLabel = "__root__".equals(entry.getKey()) ? "root" : ("\"" + entry.getKey() + "\"");
            List<BatchFile> files = entry.getValue();

            long appraisals = files.stream().filter(f -> f.getFileType() == FileType.APPRAISAL).count();
            long engagements = files.stream().filter(f -> f.getFileType() == FileType.ENGAGEMENT).count();
            long contracts   = files.stream().filter(f -> f.getFileType() == FileType.CONTRACT).count();

            if (appraisals > 1) {
                warnings.add("Set " + setLabel + ": " + appraisals
                        + " appraisal PDFs found — confirm they belong to the same appraisal.");
            }
            if (engagements > 1) {
                warnings.add("Set " + setLabel + ": " + engagements
                        + " engagement letters found — confirm which one applies before running QC.");
            }
            if (contracts > 1) {
                warnings.add("Set " + setLabel + ": " + contracts
                        + " contracts found — confirm which one applies before running QC.");
            }
        }

        if (!warnings.isEmpty()) {
            String note = String.join("\n", warnings);
            String existing = batch.getIntakeWarnings();
            batch.setIntakeWarnings(existing == null || existing.isBlank() ? note : existing + "\n" + note);
            log.warn("Batch {} has ambiguous document roles per set: {}", batch.getParentBatchId(), warnings);
        }
    }

    /**
     * Warn about property sets that are missing required documents.
     *
     * A set without an appraisal cannot be QC'd at all — it should be uploaded as a
     * separate batch once the appraisal PDF is available.
     * A set without an engagement letter can still be QC'd but with reduced accuracy —
     * the admin should be aware and ideally upload it as its own batch with the full set.
     */
    private void warnIncompleteSets(Batch batch, Set<String> distinctSets) {
        List<String> warnings = new ArrayList<>();
        for (String setName : distinctSets) {
            List<BatchFile> setFiles = batch.getFiles().stream()
                    .filter(f -> setName.equals(f.getPropertySetName()))
                    .toList();
            boolean hasAppraisal  = setFiles.stream().anyMatch(f -> f.getFileType() == FileType.APPRAISAL);
            boolean hasEngagement = setFiles.stream().anyMatch(f -> f.getFileType() == FileType.ENGAGEMENT);

            if (!hasAppraisal) {
                warnings.add("Set \"" + setName + "\" has no appraisal PDF — this set will be skipped during QC. "
                        + "Remove it from the ZIP and upload it as a separate batch once the appraisal is available.");
                log.warn("Batch {} set '{}' has no appraisal — it will be skipped during QC",
                        batch.getParentBatchId(), setName);
            } else if (!hasEngagement) {
                warnings.add("Set \"" + setName + "\" has no engagement letter — QC will proceed without it, "
                        + "which reduces accuracy. Consider removing it and uploading as a separate batch "
                        + "once the engagement letter is available.");
                log.warn("Batch {} set '{}' has no engagement letter — QC accuracy may be reduced",
                        batch.getParentBatchId(), setName);
            }
        }
        if (!warnings.isEmpty()) {
            String note = String.join("\n", warnings);
            String existing = batch.getIntakeWarnings();
            batch.setIntakeWarnings(existing == null || existing.isBlank() ? note : existing + "\n" + note);
        }
    }

    /**
     * Extract the property set (top-level property folder) name from a ZIP entry path.
     * Looks for the directory segment that is a document-type keyword and returns
     * the segment immediately before it.
     *
     * Examples:
     *   "8234 E Pearson/appraisal/file.pdf"             → "8234 E Pearson"
     *   "SHAL-sorted/8234 E Pearson/appraisal/file.pdf" → "8234 E Pearson"
     *   "appraisal/file.pdf"                            → null (no set)
     */
    static String extractPropertySetName(String entryPath) {
        if (entryPath == null || entryPath.isBlank()) return null;
        String[] parts = entryPath.split("/");
        // Iterate over directory segments (all except the last, which is the filename)
        for (int i = 0; i < parts.length - 1; i++) {
            if (isDocTypeFolder(parts[i])) {
                return i > 0 ? parts[i - 1].trim() : null;
            }
        }
        return null;
    }

    private static boolean isDocTypeFolder(String segment) {
        if (segment == null) return false;
        String lower = segment.trim().toLowerCase();
        return lower.equals("appraisal")   || lower.equals("appraisals")
            || lower.equals("engagement")  || lower.equals("engagements")
            || lower.equals("eagagement")  || lower.equals("eagagements")
            || lower.equals("contract")    || lower.equals("contracts")
            || lower.equals("order")       || lower.equals("orders")
            || lower.equals("purchase")    || lower.equals("agreement");
    }

    /** Strip characters that are unsafe in filesystem path segments. */
    private static String sanitizeFolderName(String name) {
        return name.replaceAll("[/\\\\:*?\"<>|]", "_").trim();
    }

    /**
     * Returns the last non-empty path segment of a ZIP entry name (directory or file),
     * lower-cased and with trailing slashes stripped.
     * e.g. "SHAL-sorted/8234 E Pearson/appraisal/" → "appraisal"
     */
    private static String lastPathSegment(String entryName) {
        if (entryName == null || entryName.isBlank()) return "";
        String trimmed = entryName.replace("\\", "/").stripTrailing();
        if (trimmed.endsWith("/")) trimmed = trimmed.substring(0, trimmed.length() - 1);
        int slash = trimmed.lastIndexOf('/');
        return (slash >= 0 ? trimmed.substring(slash + 1) : trimmed).trim().toLowerCase();
    }

    /**
     * Returns the direct parent folder name of a ZIP file entry, lower-cased.
     * e.g. "SHAL-sorted/8234 E Pearson/appraisal/report.pdf" → "appraisal"
     * e.g. "appraisal/report.pdf" → "appraisal"
     * Falls back to the empty string if the structure is unexpected.
     */
    private static String directParentFolder(String entryPath) {
        if (entryPath == null) return "";
        String[] parts = entryPath.replace("\\", "/").split("/");
        // parts[-1] is the filename; parts[-2] is the direct parent folder
        return parts.length >= 2 ? parts[parts.length - 2].trim().toLowerCase() : "";
    }

    private String documentQualityFlags(FileType fileType, String filename, String contentHash,
                                         List<BatchFile> existingFiles, String propertySetName) {
        List<String> flags = new ArrayList<>();

        if (contentHash != null && !existingFiles.isEmpty()) {
            // Check for duplicate content within the same property set first — this is a strong
            // signal that the same file was accidentally included twice in the same property folder.
            boolean sameSetDuplicate = existingFiles.stream().anyMatch(f ->
                    contentHash.equals(f.getContentHash())
                    && java.util.Objects.equals(propertySetName, f.getPropertySetName()));
            if (sameSetDuplicate) {
                String setHint = propertySetName != null ? " in set \"" + propertySetName + "\"" : "";
                flags.add("Duplicate: this PDF has the same fingerprint as another file" + setHint
                        + " — likely an accidental duplicate upload. Review and remove the copy.");
            } else {
                // Cross-set or batch-wide duplicate (less critical — different sets may share
                // supporting documents in some workflows)
                boolean batchWideDuplicate = existingFiles.stream()
                        .anyMatch(f -> contentHash.equals(f.getContentHash()));
                if (batchWideDuplicate) {
                    flags.add("This PDF has the same fingerprint as another document in this batch.");
                }
            }
        }

        String lowerName = filename == null ? "" : filename.toLowerCase();
        if (fileType == FileType.ENGAGEMENT && !lowerName.matches(".*\\d{2,}.*")) {
            flags.add("The engagement/order document filename has no visible order number; verify the order details carefully.");
        }
        if (fileType == FileType.CONTRACT && !lowerName.matches(".*(contract|purchase|agreement).*")) {
            flags.add("The contract document filename does not clearly identify the document type.");
        }

        return flags.isEmpty() ? null : String.join("\n", flags);
    }

    private String computeSha256(MultipartFile file) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] hash = digest.digest(file.getBytes());
            return HexFormat.of().formatHex(hash);
        } catch (Exception e) {
            log.warn("Could not compute SHA-256 for file '{}': {}", file.getOriginalFilename(), e.getMessage());
            return null;
        }
    }

    private String computeSha256(Path file) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] hash = digest.digest(Files.readAllBytes(file));
            return HexFormat.of().formatHex(hash);
        } catch (Exception e) {
            log.warn("Could not compute SHA-256 for file '{}': {}", file, e.getMessage());
            return null;
        }
    }

    /**
     * Resolve a non-colliding path in {@code dir} for {@code filename}. If the name
     * is free it is returned as-is; otherwise a " (n)" suffix is inserted before the
     * extension until a free path is found, so a duplicate filename never overwrites
     * an existing document on disk.
     */
    private static Path uniqueFilePath(Path dir, String filename) {
        Path candidate = dir.resolve(filename);
        if (!Files.exists(candidate)) {
            return candidate;
        }
        int dot = filename.lastIndexOf('.');
        String base = dot > 0 ? filename.substring(0, dot) : filename;
        String ext = dot > 0 ? filename.substring(dot) : "";
        for (int n = 2; n < 1000; n++) {
            Path next = dir.resolve(base + " (" + n + ")" + ext);
            if (!Files.exists(next)) {
                return next;
            }
        }
        // Pathological fallback — guaranteed unique by timestamp.
        return dir.resolve(base + " (" + System.currentTimeMillis() + ")" + ext);
    }

    @Transactional
    public Batch updateStatus(Long id, BatchStatus status) {
        if (id == null) {
            throw new ValidationException("id", "Batch ID is required");
        }
        if (status == null) {
            throw new ValidationException("status", "Status is required");
        }
        Batch batch = batchRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("Batch", "id", id));
        batch.setStatus(status);
        log.info("Updated batch {} status to {}", id, status);
        return batchRepository.save(batch);
    }

    @Transactional
    public Batch assignReviewer(Long batchId, User reviewer) {
        if (batchId == null) {
            throw new ValidationException("batchId", "Batch ID is required");
        }
        if (reviewer == null) {
            throw new ValidationException("reviewer", "Reviewer is required");
        }
        if (reviewer.getRole() != Role.REVIEWER) {
            throw new ValidationException("reviewer", "Assigned user must have REVIEWER role");
        }

        if (!batchRepository.existsById(batchId)) {
            throw new ResourceNotFoundException("Batch", "id", batchId);
        }

        int updated = batchRepository.assignReviewerIfNotProcessing(batchId, reviewer, AppTime.now());
        if (updated == 0) {
            throw new ValidationException("batch", "Reviewer can be assigned after QC processing completes");
        }

        log.info("Assigned batch {} to reviewer {}", batchId, reviewer.getUsername());
        Batch batch = batchRepository.findById(batchId)
                .orElseThrow(() -> new ResourceNotFoundException("Batch", "id", batchId));
        businessEventService.batchEvent("REVIEWER_ASSIGNED", reviewer, batch, "ASSIGNED",
                Map.of(
                        "reviewer_id", reviewer.getId(),
                        "reviewer_username", reviewer.getUsername()
                ));
        return batch;
    }

    // Statistics methods
    @Transactional(readOnly = true)
    public long countByClient(Long clientId) {
        return batchRepository.countByClientId(clientId);
    }

    @Transactional(readOnly = true)
    public long countByClientAndStatus(Long clientId, BatchStatus status) {
        return batchRepository.countByClientIdAndStatus(clientId, status);
    }

    @Transactional(readOnly = true)
    public long countByStatus(BatchStatus status) {
        return batchRepository.countByStatus(status);
    }

    @Transactional(readOnly = true)
    public long count() {
        return batchRepository.count();
    }

    private long elapsedMs(long startedNanos) {
        return (System.nanoTime() - startedNanos) / 1_000_000L;
    }
}
