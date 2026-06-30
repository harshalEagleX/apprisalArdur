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
import com.shal.common.realtime.RealtimeEventPublisher;
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
    private final RealtimeEventPublisher realtimeEventPublisher;
    private final TransactionService transactionService;
    private final tools.jackson.databind.ObjectMapper objectMapper;

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
            BusinessEventService businessEventService,
            RealtimeEventPublisher realtimeEventPublisher,
            TransactionService transactionService,
            tools.jackson.databind.ObjectMapper objectMapper) {
        this.batchRepository = batchRepository;
        this.batchFileRepository = batchFileRepository;
        this.qcResultRepository = qcResultRepository;
        this.qcRuleResultRepository = qcRuleResultRepository;
        this.documentMatchRepository = documentMatchRepository;
        this.metricsRepository = metricsRepository;
        this.docStatRepository = docStatRepository;
        this.auditLogService = auditLogService;
        this.businessEventService = businessEventService;
        this.realtimeEventPublisher = realtimeEventPublisher;
        this.transactionService = transactionService;
        this.objectMapper = objectMapper;
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

        log.info("Batch upload started: ref={} client={} user={} size={} bytes",
                parentBatchId, client.getCode(), creator.getUsername(), file.getSize());

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
            batch.setStatus(BatchStatus.UPLOADED);
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
        log.info("Batch '{}' created (id={}) — {} files, {} ms",
                batch.getParentBatchId(), batch.getId(), batch.getFileCount(), TimelineLog.elapsedMs(flowStarted));
        auditLogService.logEntity(creator, "BATCH_UPLOAD", "Batch", batch.getId());
        Map<String, Object> eventPayload = new HashMap<>();
        eventPayload.put("parent_batch_id", batch.getParentBatchId());
        eventPayload.put("client_id", client.getId());
        eventPayload.put("file_count", batch.getFiles().size());
        eventPayload.put("file_hash", fileHash);
        businessEventService.batchEvent("BATCH_CREATED", creator, batch, "UPLOADED", eventPayload);

        // Parse manifest.json from ZIP if present and link to transaction.
        linkBatchToTransactionFromManifest(batch, file, client);

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

                // Accept PDFs (all document types) AND .xml (MISMO appraisal XML).
                // Everything else (images, spreadsheets, etc.) is catalogued but excluded.
                String lowerEntry = entryName.toLowerCase();
                boolean isPdf = lowerEntry.endsWith(".pdf");
                boolean isXmlEntry = lowerEntry.endsWith(".xml");
                if (!isPdf && !isXmlEntry) {
                    excludedNonPdf.add(filenameOnly);
                    log.info("Cataloguing non-PDF/non-XML entry (excluded from extraction): {}", entryName);
                    continue;
                }

                // Classify by the DIRECT PARENT FOLDER name only (the segment immediately
                // containing this PDF), not the full entry path. Using the full path causes
                // misclassification when a set folder name contains type keywords
                // (e.g. "8234 E Pearson_no_appraisal/engagement/order.pdf" would incorrectly
                // become APPRAISAL because "appraisal" appears in the set folder name).
                String parentFolder = directParentFolder(entryName);
                // XML files are the MISMO 2.6 GSE appraisal XML. If they sit inside the
                // appraisal/ folder, classify immediately. If they are outside (common in
                // flat ZIPs where vendor dumps everything at root), peek at the XML content
                // to detect the MISMO namespace before deciding to include or exclude.
                // ZipInputStream does not support mark/reset, so we must read all bytes now
                // and write them manually; preReadXmlBytes is null for non-XML entries.
                byte[] preReadXmlBytes = null;
                FileType fileType;
                if (parentFolder.startsWith("appraisal")) {
                    fileType = isXmlEntry ? FileType.APPRAISAL_XML : FileType.APPRAISAL;
                    hasAppraisalFolder = true;
                } else if (isXmlEntry) {
                    preReadXmlBytes = zis.readAllBytes();
                    String xmlHeader = new String(preReadXmlBytes, 0,
                            Math.min(preReadXmlBytes.length, 2048), java.nio.charset.StandardCharsets.UTF_8);
                    boolean isMismo = xmlHeader.contains("VALUATION_RESPONSE")
                            || xmlHeader.contains("MISMO")
                            || xmlHeader.contains("ValuationResponse")
                            || xmlHeader.contains("UCDP_");
                    if (!isMismo) {
                        excludedNonPdf.add(filenameOnly);
                        log.info("Excluding non-MISMO XML outside appraisal folder: {}", entryName);
                        zis.closeEntry();
                        continue;
                    }
                    fileType = FileType.APPRAISAL_XML;
                    hasAppraisalFolder = true;
                    log.info("MISMO XML detected outside appraisal/ folder — reclassifying to APPRAISAL_XML: {}", entryName);
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
                if (preReadXmlBytes != null) {
                    Files.write(filePath, preReadXmlBytes);
                } else {
                    Files.copy(zis, filePath, java.nio.file.StandardCopyOption.REPLACE_EXISTING);
                }
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
            log.debug("Batch {} — {} distinct property sets", batch.getParentBatchId(), distinctSets.size());
            // Check each set for completeness and warn about incomplete ones
            warnIncompleteSets(batch, distinctSets);
        }

        flagDocumentRoleAmbiguity(batch);
        markUnresolvableFilesNeedsAssignment(batch);

        if (!excludedNonPdf.isEmpty()) {
            String note = excludedNonPdf.size() + " non-PDF file(s) catalogued and excluded from extraction: "
                    + String.join(", ", excludedNonPdf);
            String existing = batch.getIntakeWarnings();
            batch.setIntakeWarnings(existing == null || existing.isBlank() ? note : existing + "\n" + note);
            log.debug("Batch {} — {} non-PDF file(s) catalogued and excluded",
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
            log.debug("Batch {} contains {} property sets", batch.getParentBatchId(), setNames.size());
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
     * For multi-order batches (more than one APPRAISAL file), mark every ENGAGEMENT,
     * CONTRACT, and APPRAISAL_XML file that has no orderId overlap with any appraisal
     * as NEEDS_ASSIGNMENT. These files cannot be auto-matched by filename alone; the
     * admin must use the batch detail UI to manually pair them before Re-QC can run.
     *
     * Single-order batches are exempt — the single_file_fallback in FileMatchingService
     * handles the "only one candidate" case correctly for them.
     */
    private void markUnresolvableFilesNeedsAssignment(Batch batch) {
        long appraisalCount = batch.getFiles().stream()
                .filter(f -> f.getFileType() == FileType.APPRAISAL).count();
        if (appraisalCount <= 1) {
            return;
        }
        Set<String> appraisalOrderIds = batch.getFiles().stream()
                .filter(f -> f.getFileType() == FileType.APPRAISAL)
                .map(BatchFile::getOrderId)
                .filter(id -> id != null && !id.isBlank())
                .collect(java.util.stream.Collectors.toSet());

        for (BatchFile f : batch.getFiles()) {
            if (f.getFileType() == FileType.APPRAISAL) {
                continue;
            }
            String fOrderId = f.getOrderId();
            // Primary check: orderId exact match
            boolean linked = fOrderId != null && !fOrderId.isBlank()
                    && appraisalOrderIds.contains(fOrderId);
            // Secondary check: case-insensitive basename match (covers "ESCA-0019573.xml"
            // vs appraisal orderId "ESCA-0019573" when orderId comes from the full basename)
            if (!linked && fOrderId != null && !fOrderId.isBlank()) {
                linked = appraisalOrderIds.stream()
                        .anyMatch(aid -> aid.equalsIgnoreCase(fOrderId));
            }
            if (!linked) {
                f.setStatus(FileStatus.NEEDS_ASSIGNMENT);
                log.info("Batch {} — file '{}' ({}) marked NEEDS_ASSIGNMENT: no orderId match in {}-order batch",
                        batch.getParentBatchId(), f.getFilename(), f.getFileType(), appraisalCount);
            }
        }

        long needsCount = batch.getFiles().stream()
                .filter(f -> f.getStatus() == FileStatus.NEEDS_ASSIGNMENT).count();
        if (needsCount > 0) {
            String note = needsCount + " supporting file(s) could not be automatically linked to an appraisal "
                    + "and require manual assignment before QC can use them. Use the 'Assign' button "
                    + "next to each NEEDS ASSIGNMENT file in the batch detail view.";
            String existing = batch.getIntakeWarnings();
            batch.setIntakeWarnings(existing == null || existing.isBlank() ? note : existing + "\n" + note);
        }
    }

    /**
     * Manually assign a supporting file (ENGAGEMENT, CONTRACT, or APPRAISAL_XML) to a
     * specific appraisal in the same batch. Creates (or updates) a DocumentMatch with
     * match_type='manual_admin' and confidence 1.0.
     *
     * FileMatchingService.findSupportingFile() always honours manual_admin matches and
     * never overwrites them during Re-QC, so the pairing survives re-runs.
     *
     * The file is moved from NEEDS_ASSIGNMENT → PENDING so the next Re-QC picks it up.
     */
    @Transactional
    public void manuallyAssignFile(Long supportingFileId, Long appraisalFileId, Long batchId, User admin) {
        BatchFile supporting = batchFileRepository.findById(supportingFileId)
                .orElseThrow(() -> new com.shal.common.exception.ResourceNotFoundException(
                        "BatchFile not found: " + supportingFileId));
        BatchFile appraisal = batchFileRepository.findById(appraisalFileId)
                .orElseThrow(() -> new com.shal.common.exception.ResourceNotFoundException(
                        "BatchFile not found: " + appraisalFileId));

        if (!batchId.equals(supporting.getBatch().getId()) || !batchId.equals(appraisal.getBatch().getId())) {
            throw new ValidationException("files", "Both files must belong to batch " + batchId);
        }
        if (appraisal.getFileType() != FileType.APPRAISAL) {
            throw new ValidationException("appraisalFileId", "Target must be an APPRAISAL file");
        }
        if (supporting.getFileType() == FileType.APPRAISAL) {
            throw new ValidationException("fileId", "Cannot assign an APPRAISAL as a supporting file");
        }

        DocumentMatch match = documentMatchRepository
                .findByAppraisalFile_IdAndSupportingFileType(appraisal.getId(), supporting.getFileType())
                .orElseGet(DocumentMatch::new);
        match.setAppraisalFile(appraisal);
        match.setSupportingFile(supporting);
        match.setSupportingFileType(supporting.getFileType());
        match.setMatchType("manual_admin");
        match.setConfidenceScore(1.0);
        match.setMatchReason("Manually assigned by admin " + admin.getUsername()
                + " on " + java.time.LocalDate.now());
        match.setMatchedBy(admin);
        match.setMatchWarning(null);
        match.setAmbiguousCandidatesJson("[]");
        match.setRejectedCandidatesJson("[]");
        documentMatchRepository.save(match);

        if (supporting.getStatus() == FileStatus.NEEDS_ASSIGNMENT
                || supporting.getStatus() == FileStatus.PENDING) {
            supporting.setStatus(FileStatus.PENDING);
            batchFileRepository.save(supporting);
        }

        businessEventService.record("FILE_MANUALLY_ASSIGNED", admin, "java", "ASSIGNED",
                "DocumentMatch", match.getId(), batchId, supportingFileId, null, null,
                Map.of(
                        "supporting_file", supporting.getFilename(),
                        "supporting_type", supporting.getFileType().name(),
                        "appraisal_file", appraisal.getFilename()
                ));
        log.info("Admin {} manually assigned '{}' ({}) → appraisal '{}' in batch {}",
                admin.getUsername(), supporting.getFilename(), supporting.getFileType(),
                appraisal.getFilename(), batchId);
    }

    /**
     * Change a file's FileType. Used when intake classification was wrong — most commonly
     * a MISMO XML that landed in the wrong folder and was classified as CONTRACT.
     * After reclassification the admin should run Re-QC so the corrected type is used.
     */
    @Transactional
    public void reclassifyFile(Long fileId, Long batchId, FileType newType, User admin) {
        BatchFile file = batchFileRepository.findById(fileId)
                .orElseThrow(() -> new com.shal.common.exception.ResourceNotFoundException(
                        "BatchFile not found: " + fileId));
        if (!batchId.equals(file.getBatch().getId())) {
            throw new ValidationException("fileId", "File does not belong to batch " + batchId);
        }
        FileType oldType = file.getFileType();
        if (oldType == newType) {
            return;
        }
        file.setFileType(newType);
        // If this file was previously unresolvable due to wrong type, reset its status
        // so it is re-evaluated (matching will now use the correct type during Re-QC).
        if (file.getStatus() == FileStatus.NEEDS_ASSIGNMENT) {
            file.setStatus(FileStatus.PENDING);
        }
        batchFileRepository.save(file);
        auditLogService.logEntity(admin, "FILE_RECLASSIFIED", "BatchFile", fileId);
        log.info("Admin {} reclassified '{}' from {} → {} in batch {}",
                admin.getUsername(), file.getFilename(), oldType, newType, batchId);
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
        // Notify the reviewer via the reviewer notifications topic
        try {
            Map<String, Object> notif = new java.util.LinkedHashMap<>();
            notif.put("type",          "BATCH_ASSIGNED");
            notif.put("batchId",       batch.getId());
            notif.put("parentBatchId", batch.getParentBatchId());
            notif.put("message",       "Batch \"" + batch.getParentBatchId() + "\" has been assigned to you for review.");
            notif.put("needsReview",   true);
            notif.put("occurredAt",    java.time.LocalDateTime.now().toString());
            realtimeEventPublisher.publish("/topic/reviewer/notifications", notif);
        } catch (Exception e) {
            log.debug("Failed to push assignment notification: {}", e.getMessage());
        }
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

    /**
     * Mark a permanently-failing appraisal file as DISMISSED so the rest of its
     * batch can complete. Use when the file is corrupt or unreadable and retrying
     * via the partial-re-run path will never succeed.
     *
     * The file stays in the DB for audit purposes; DISMISSED files are excluded
     * from the "has unreviewed errors" guard in recomputeBatchStatusFromActiveResults.
     *
     * @param fileId  the BatchFile to dismiss
     * @param adminId the admin performing the dismissal (for audit)
     * @throws ResourceNotFoundException if the file does not exist
     * @throws IllegalStateException     if the file is not in ERROR status
     */
    @Transactional
    public BatchFile dismissFileError(Long fileId, Long adminId) {
        BatchFile file = batchFileRepository.findById(fileId)
                .orElseThrow(() -> new ResourceNotFoundException("BatchFile not found: " + fileId));
        if (file.getStatus() != FileStatus.ERROR) {
            throw new IllegalStateException(
                    "Only ERROR files can be dismissed; file " + fileId + " is " + file.getStatus());
        }
        file.setStatus(FileStatus.DISMISSED);
        BatchFile saved = batchFileRepository.save(file);
        auditLogService.logEntity(
                userRef(adminId), "FILE_ERROR_DISMISSED", "BatchFile", fileId);
        log.info("BatchFile {} dismissed as permanently unreviewable by admin {}", fileId, adminId);
        return saved;
    }

    private com.shal.common.entity.User userRef(Long userId) {
        com.shal.common.entity.User u = new com.shal.common.entity.User();
        u.setId(userId);
        return u;
    }

    private long elapsedMs(long startedNanos) {
        return (System.nanoTime() - startedNanos) / 1_000_000L;
    }

    /**
     * Scan the ZIP for a manifest.json at its root, parse it, and link the batch
     * to an AppraisalTransaction. Creates the transaction if it does not yet exist.
     *
     * Manifest fields (all optional except transaction_ref):
     *   transaction_ref   — stable ID; if absent, no transaction is linked
     *   amc_code          — AMC identifier
     *   order_number      — AMC order/loan number
     *   property_address  — property address (pre-OCR)
     *   is_revision_of    — transaction_ref of the transaction being revised
     *   sla_due_at        — ISO-8601 SLA deadline (e.g. "2026-07-05T17:00:00")
     *
     * Errors are non-fatal: a malformed or missing manifest just means the batch
     * is not linked to a transaction, which is the same as the pre-manifest state.
     */
    @Transactional
    public void linkBatchToTransactionFromManifest(Batch batch, MultipartFile zipFile, Client client) {
        byte[] manifestBytes = null;
        try (ZipInputStream zis = new ZipInputStream(zipFile.getInputStream())) {
            ZipEntry entry;
            while ((entry = zis.getNextEntry()) != null) {
                String name = entry.getName().toLowerCase();
                // Accept manifest.json at the zip root or one level deep
                if (!entry.isDirectory() && (name.equals("manifest.json")
                        || name.endsWith("/manifest.json"))) {
                    manifestBytes = zis.readAllBytes();
                    break;
                }
            }
        } catch (Exception e) {
            log.debug("Could not scan ZIP for manifest in batch {}: {}", batch.getId(), e.getMessage());
            return;
        }

        if (manifestBytes == null) {
            return;  // no manifest — batch runs without transaction linkage
        }

        try {
            @SuppressWarnings("unchecked")
            Map<String, Object> manifest = objectMapper.readValue(manifestBytes, Map.class);

            String txRef = manifest.get("transaction_ref") != null
                    ? manifest.get("transaction_ref").toString().trim() : null;
            if (txRef == null || txRef.isBlank()) {
                log.debug("Manifest in batch {} has no transaction_ref — skipping linkage", batch.getId());
                return;
            }

            String amcCode      = stringOrNull(manifest, "amc_code");
            String orderNumber  = stringOrNull(manifest, "order_number");
            String address      = stringOrNull(manifest, "property_address");
            String revisedFrom  = stringOrNull(manifest, "is_revision_of");
            String slaDueStr    = stringOrNull(manifest, "sla_due_at");

            java.time.LocalDateTime slaDueAt = null;
            if (slaDueStr != null) {
                try { slaDueAt = java.time.LocalDateTime.parse(slaDueStr); } catch (Exception ignored) { }
            }
            final java.time.LocalDateTime finalSlaDueAt = slaDueAt;

            // Find or create the transaction for this ref
            AppraisalTransaction tx = transactionService.findByRef(txRef).orElseGet(() ->
                transactionService.createTransaction(amcCode, orderNumber, address, client, revisedFrom, finalSlaDueAt));

            transactionService.linkBatchToTransaction(batch.getId(), tx.getId());
            log.info("Batch {} linked to transaction {} via manifest", batch.getId(), txRef);

        } catch (Exception e) {
            log.warn("Failed to parse manifest for batch {}: {}", batch.getId(), e.getMessage());
        }
    }

    private String stringOrNull(Map<String, Object> map, String key) {
        Object v = map.get(key);
        return (v != null && !v.toString().isBlank()) ? v.toString().trim() : null;
    }
}
