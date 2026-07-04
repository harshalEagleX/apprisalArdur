package com.shal.batch.service;

import com.shal.common.entity.*;
import com.shal.common.exception.BatchProcessingException;
import com.shal.common.exception.ResourceNotFoundException;
import com.shal.common.exception.ValidationException;
import com.shal.common.repository.AppraisalTransactionRepository;
import com.shal.common.repository.BatchFileRepository;
import com.shal.common.repository.BatchRepository;
import com.shal.common.repository.DocumentMatchRepository;
import com.shal.common.repository.ProcessingMetricsRepository;
import com.shal.common.repository.QCResultRepository;
import com.shal.common.repository.QCRuleResultRepository;
import com.shal.common.realtime.RealtimeEventPublisher;
import com.shal.common.service.AuditLogService;
import com.shal.common.service.BusinessEventService;
import com.shal.common.service.DocumentContentSniffer;
import com.shal.common.service.FileMatchingService;
import com.shal.common.service.OrderResolutionService;
import com.shal.common.service.OrderStatusService;
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
    /** Guard against nested-ZIP bombs — an order ZIP inside a batch ZIP is depth 1. */
    private static final int MAX_ZIP_DEPTH = 4;

    private final BatchRepository batchRepository;
    private final BatchFileRepository batchFileRepository;
    private final AppraisalTransactionRepository appraisalTransactionRepository;
    private final QCResultRepository qcResultRepository;
    private final QCRuleResultRepository qcRuleResultRepository;
    private final DocumentMatchRepository documentMatchRepository;
    private final ProcessingMetricsRepository metricsRepository;
    private final com.shal.common.repository.DocStatRepository docStatRepository;
    private final AuditLogService auditLogService;
    private final BusinessEventService businessEventService;
    private final RealtimeEventPublisher realtimeEventPublisher;
    private final TransactionService transactionService;
    private final OrderResolutionService orderResolutionService;
    private final OrderStatusService orderStatusService;
    private final DocumentContentSniffer contentSniffer;
    private final tools.jackson.databind.ObjectMapper objectMapper;

    @Value("${app.storage.path:./uploads}")
    private String storagePath;

    /** Per-file size cap (MB). Files in the ZIP larger than this are excluded with a clear note. */
    @Value("${app.upload.max-file-mb:50}")
    private long maxUploadFileMb;

    public BatchService(BatchRepository batchRepository,
            BatchFileRepository batchFileRepository,
            AppraisalTransactionRepository appraisalTransactionRepository,
            QCResultRepository qcResultRepository,
            QCRuleResultRepository qcRuleResultRepository,
            DocumentMatchRepository documentMatchRepository,
            ProcessingMetricsRepository metricsRepository,
            com.shal.common.repository.DocStatRepository docStatRepository,
            AuditLogService auditLogService,
            BusinessEventService businessEventService,
            RealtimeEventPublisher realtimeEventPublisher,
            TransactionService transactionService,
            OrderResolutionService orderResolutionService,
            OrderStatusService orderStatusService,
            DocumentContentSniffer contentSniffer,
            tools.jackson.databind.ObjectMapper objectMapper) {
        this.batchRepository = batchRepository;
        this.batchFileRepository = batchFileRepository;
        this.appraisalTransactionRepository = appraisalTransactionRepository;
        this.qcResultRepository = qcResultRepository;
        this.qcRuleResultRepository = qcRuleResultRepository;
        this.documentMatchRepository = documentMatchRepository;
        this.metricsRepository = metricsRepository;
        this.docStatRepository = docStatRepository;
        this.auditLogService = auditLogService;
        this.businessEventService = businessEventService;
        this.realtimeEventPublisher = realtimeEventPublisher;
        this.transactionService = transactionService;
        this.orderResolutionService = orderResolutionService;
        this.orderStatusService = orderStatusService;
        this.contentSniffer = contentSniffer;
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
     * A soft-deleted batch is hidden from the whole app, so its documents must stop
     * counting toward any Order. We unlink this batch's files from their Orders (the
     * rows themselves are kept for the audit trail) and then remove any Order that is
     * left with no documents — a deleted batch must never leave a ghost Order behind.
     * Orders still referenced by another live batch survive and are recomputed.
     *
     * @param batchId the batch to soft-delete
     * @param actorId id of the admin performing the deletion (recorded on the row)
     * @throws ResourceNotFoundException if batch not found
     */
    @Transactional
    public void softDeleteBatch(@NonNull Long batchId, Long actorId) {
        Batch batch = batchRepository.findById(batchId)
                .orElseThrow(() -> new ResourceNotFoundException("Batch", "id", batchId));

        // Capture the Orders this batch's files touched before we unlink them.
        Set<Long> touchedOrderIds = batch.getFiles().stream()
                .map(BatchFile::getOrder)
                .filter(Objects::nonNull)
                .map(AppraisalTransaction::getId)
                .collect(java.util.stream.Collectors.toSet());

        // Unlink so the deleted batch's documents no longer haunt the Order views.
        for (BatchFile f : batch.getFiles()) {
            if (f.getOrder() != null) {
                f.setOrder(null);
            }
        }

        batch.setDeletedAt(AppTime.now());
        batch.setDeletedBy(actorId);
        batchRepository.save(batch);

        int ordersDeleted = 0;
        for (Long orderId : touchedOrderIds) {
            // countAllByOrderId counts every physical batch_file → order link that
            // remains (the FK), so a zero here means nothing references the Order and
            // it is safe to delete without a constraint violation.
            if (batchFileRepository.countAllByOrderId(orderId) == 0) {
                appraisalTransactionRepository.deleteById(orderId);
                ordersDeleted++;
            } else {
                appraisalTransactionRepository.findById(orderId).ifPresent(orderStatusService::recompute);
            }
        }
        log.info("Soft-deleted batch {} (id={}) by user {} — unlinked files, removed {} orphaned order(s)",
                batch.getParentBatchId(), batchId, actorId, ordersDeleted);
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
        // Orders this batch's files touched — captured now (see comment above: bulk
        // deletes below clear the persistence context, and BatchFile.order is lazy).
        Set<Long> touchedOrderIds = batch.getFiles().stream()
                .map(BatchFile::getOrder)
                .filter(Objects::nonNull)
                .map(AppraisalTransaction::getId)
                .collect(java.util.stream.Collectors.toSet());

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

        // An Order with no remaining documents (this was its only batch) is now
        // orphaned — remove it too. An Order still referenced by another batch's
        // files is left alone.
        int ordersDeleted = 0;
        for (Long orderId : touchedOrderIds) {
            if (batchFileRepository.countAllByOrderId(orderId) == 0) {
                appraisalTransactionRepository.deleteById(orderId);
                ordersDeleted++;
            }
        }
        if (ordersDeleted > 0) {
            log.info("Deleted {} orphaned order(s) after batch {} removal", ordersDeleted, batch.getParentBatchId());
        }

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
            extractAndValidateZip(file, batch, batchDir, creator);
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

    private void extractAndValidateZip(MultipartFile file, Batch batch, Path batchDir, User creator) throws IOException {
        // Non-PDF/XML entries are catalogued (so nothing is silently dropped) but excluded.
        List<String> excludedNonPdf = new ArrayList<>();
        // Files over the per-file cap (default 50 MB) are excluded with a clear note.
        List<String> oversizeFiles = new ArrayList<>();
        List<StagedDoc> staged = new ArrayList<>();
        int[] entryCount = {0};

        Path stagingDir = batchDir.resolve(".staging");
        Files.createDirectories(stagingDir);

        // ── Phase 1 — recursively scan the ZIP (including nested .zip archives),
        //    classify every document, and stage its bytes on disk. Never silently
        //    dropped: unclassifiable entries land in excludedNonPdf / oversizeFiles.
        try {
            try (ZipInputStream zis = new ZipInputStream(file.getInputStream())) {
                scanZip(zis, "", 0, stagingDir, staged, excludedNonPdf, oversizeFiles, entryCount);
            }

            if (staged.isEmpty()) {
                throw new ValidationException("No valid PDF or appraisal-XML files were found in the ZIP.");
            }

            // ── Phase 2 — group documents into Orders. Folder-first: each distinct order
            //    folder (numbered or named) is one order; when several appraisals share a
            //    single type folder, split them into one order per appraisal by filename.
            //    Assigns propertySetName on every staged doc.
            assignOrderGroups(staged);

            // ── Phase 3 — move staged bytes into their final <set>/<type> location and
            //    build the BatchFile rows.
            for (StagedDoc d : staged) {
                String storageFolderName = (d.propertySetName != null && !d.propertySetName.isBlank())
                        ? sanitizeFolderName(d.propertySetName) + "/" + d.fileType.name().toLowerCase()
                        : d.fileType.name().toLowerCase();
                Path typeDir = batchDir.resolve(storageFolderName);
                Files.createDirectories(typeDir);
                Path filePath = uniqueFilePath(typeDir, d.filenameOnly);
                String filename = filePath.getFileName().toString();
                if (!filename.equals(d.filenameOnly)) {
                    log.warn("Filename collision in ZIP: '{}' already present in {} — stored as '{}'",
                            d.filenameOnly, storageFolderName, filename);
                }
                Files.move(d.stagedPath, filePath, java.nio.file.StandardCopyOption.REPLACE_EXISTING);

                String qualityFlags = documentQualityFlags(d.fileType, filename, d.contentHash,
                        batch.getFiles(), d.propertySetName);
                if (d.typeInferredFromFilename) {
                    String note = "Document type was inferred as " + d.fileType.name()
                            + " from the filename (the ZIP had no type folder for it) — verify it is correct.";
                    qualityFlags = qualityFlags == null ? note : qualityFlags + "\n" + note;
                }

                BatchFile batchFile = BatchFile.builder()
                        .batch(batch)
                        .fileType(d.fileType)
                        .filename(filename)
                        .originalPath(d.entryPath)
                        .storagePath(filePath.toString())
                        .fileSize(d.fileSize)
                        .contentHash(d.contentHash)
                        .contentVersion(1L)
                        .documentQualityFlags(qualityFlags)
                        .status(FileStatus.PENDING)
                        .orderId(FileMatchingService.extractOrderId(filename))
                        .propertySetName(d.propertySetName)
                        .build();
                batch.addFile(batchFile);
            }
        } finally {
            cleanupStaging(stagingDir);
        }

        // A batch is processable when it contains at least one appraisal document. The
        // old rule required literal 'appraisal' AND 'engagement' folders, which rejected
        // flat order ZIPs that actually contained every document.
        boolean hasAppraisal = batch.getFiles().stream()
                .anyMatch(f -> f.getFileType() == FileType.APPRAISAL);
        if (!hasAppraisal) {
            throw new ValidationException(
                    "No appraisal document found in the ZIP. Each order must include an appraisal PDF.");
        }

        // Order identity from inside the documents: the MISMO XML carries the AMC
        // order number and subject address for each order group. Extracted once,
        // used by the content sniff below AND by order resolution (true order-number
        // identity instead of filename stems).
        Map<String, DocumentContentSniffer.OrderIdentity> identityBySet = contentSniffer.extractOrderIdentities(batch);

        // S3 content-ID sniff: a supporting document not co-located with any
        // appraisal (e.g. all engagement letters dumped in one folder) states its
        // order number / subject address INSIDE the document — read it and re-home
        // the file to its order group before anything is marked unassignable.
        sniffLinkUnanchoredDocs(batch, identityBySet);

        Set<String> distinctSets = batch.getFiles().stream()
                .map(BatchFile::getPropertySetName)
                .filter(Objects::nonNull)
                .collect(java.util.stream.Collectors.toSet());
        if (distinctSets.size() > 1) {
            log.debug("Batch {} — {} order groups", batch.getParentBatchId(), distinctSets.size());
            warnIncompleteSets(batch, distinctSets);
        }

        flagDocumentRoleAmbiguity(batch);
        markUnresolvableFilesNeedsAssignment(batch);

        // Resolve each file to its canonical Order (AppraisalTransaction) — content-hash
        // → orderId → propertySetName identity matching against every previously
        // ingested batch, so a re-upload under a differently-named folder links back
        // to the order that already exists instead of forking a duplicate.
        orderResolutionService.resolveOrdersForBatch(batch, batch.getClient(), creator, identityBySet);

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
     * A document extracted from the ZIP, staged on disk, awaiting order grouping.
     * Holds everything needed to build a {@link BatchFile} once {@link #assignOrderGroups}
     * has decided which order it belongs to.
     */
    private static final class StagedDoc {
        String entryPath;                 // full ZIP path (incl. nested-zip prefix)
        String filenameOnly;              // leaf filename
        Path stagedPath;                  // temp location under batchDir/.staging
        FileType fileType;
        long fileSize;
        String contentHash;
        String groupKey;                  // batch-local order-folder path (null = ZIP root)
        String setLabel;                  // human-readable order-folder name (leaf of groupKey)
        String propertySetName;           // assigned in phase 2
        boolean typeInferredFromFilename; // true when no type folder — flagged for review
    }

    /**
     * Recursively walk a ZIP (descending into nested {@code .zip} archives up to
     * {@link #MAX_ZIP_DEPTH}), classify each PDF/appraisal-XML, and stage its bytes.
     * {@code pathPrefix} namespaces nested-zip entries so an order ZIP named "1.zip"
     * behaves exactly like an order folder "1/".
     */
    private void scanZip(ZipInputStream zis, String pathPrefix, int depth, Path stagingDir,
                         List<StagedDoc> staged, List<String> excludedNonPdf,
                         List<String> oversizeFiles, int[] entryCount) throws IOException {
        ZipEntry entry;
        while ((entry = zis.getNextEntry()) != null) {
            entryCount[0]++;
            if (entryCount[0] > MAX_ZIP_ENTRIES) {
                throw new ValidationException("ZIP file contains too many entries (max: " + MAX_ZIP_ENTRIES + ")");
            }

            String rawName = entry.getName();
            if (rawName.contains("..")) {
                throw new ValidationException("Invalid ZIP entry path: " + rawName);
            }

            String filenameOnly = leafName(rawName);
            String lowerLeaf = filenameOnly.toLowerCase();
            // Ignore macOS archive metadata (__MACOSX/.../._file.pdf, .DS_Store).
            if (rawName.toLowerCase().startsWith("__macosx/")
                    || lowerLeaf.equals(".ds_store") || filenameOnly.startsWith("._")) {
                zis.closeEntry();
                continue;
            }
            if (entry.isDirectory()) {
                zis.closeEntry();
                continue;
            }

            String entryName = pathPrefix + rawName;

            // Nested ZIP → recurse so an order-zip inside a batch-zip is handled.
            if (lowerLeaf.endsWith(".zip")) {
                byte[] nestedBytes = zis.readAllBytes();
                zis.closeEntry();
                if (depth >= MAX_ZIP_DEPTH) {
                    log.warn("Skipping nested ZIP '{}' — max nesting depth {} exceeded", entryName, MAX_ZIP_DEPTH);
                    continue;
                }
                String nestedPrefix = entryName.substring(0, entryName.length() - 4); // drop ".zip"
                if (!nestedPrefix.endsWith("/")) nestedPrefix = nestedPrefix + "/";
                try (ZipInputStream nested = new ZipInputStream(new java.io.ByteArrayInputStream(nestedBytes))) {
                    scanZip(nested, nestedPrefix, depth + 1, stagingDir, staged,
                            excludedNonPdf, oversizeFiles, entryCount);
                }
                continue;
            }

            boolean isPdf = lowerLeaf.endsWith(".pdf");
            boolean isXml = lowerLeaf.endsWith(".xml");
            if (!isPdf && !isXml) {
                excludedNonPdf.add(filenameOnly);
                log.info("Cataloguing non-PDF/non-XML entry (excluded from extraction): {}", entryName);
                zis.closeEntry();
                continue;
            }

            byte[] bytes = zis.readAllBytes();
            zis.closeEntry();
            if (bytes.length > maxUploadFileMb * 1024L * 1024L) {
                oversizeFiles.add(filenameOnly + " (" + (bytes.length / (1024 * 1024)) + " MB)");
                log.warn("Excluding oversize file '{}' ({} MB > {} MB cap)",
                        filenameOnly, bytes.length / (1024 * 1024), maxUploadFileMb);
                continue;
            }

            // Classify: folder keyword first, then filename/content fallback so a flat
            // order folder (no type subfolders) still resolves instead of being dropped.
            String typeFolder = typeFolderKeyword(directParentFolder(entryName));
            boolean inferred = false;
            FileType fileType;
            if (isXml) {
                boolean apprFolder = typeFolder != null && typeFolder.equals("appraisal");
                if (apprFolder || isMismoXml(bytes)) {
                    fileType = FileType.APPRAISAL_XML;
                } else {
                    excludedNonPdf.add(filenameOnly);
                    log.info("Excluding non-MISMO XML outside appraisal folder: {}", entryName);
                    continue;
                }
            } else if (typeFolder != null) {
                fileType = fileTypeForFolder(typeFolder);
            } else {
                fileType = classifyPdfByFilename(filenameOnly);
                inferred = true;
            }

            Path stagedPath = uniqueFilePath(stagingDir, filenameOnly);
            Files.write(stagedPath, bytes);

            StagedDoc d = new StagedDoc();
            d.entryPath = entryName;
            d.filenameOnly = filenameOnly;
            d.stagedPath = stagedPath;
            d.fileType = fileType;
            d.fileSize = bytes.length;
            d.contentHash = computeSha256(stagedPath);
            d.groupKey = orderGroupKey(entryName);
            d.setLabel = leafSegment(d.groupKey);
            d.typeInferredFromFilename = inferred;
            staged.add(d);
        }
    }

    /**
     * Folder-first order grouping with filename fallback. Files sharing an order-folder
     * path form one order; when a single folder holds several appraisals (properties
     * flattened into one type folder), each appraisal becomes its own order and the
     * supporting documents are attached to the best filename match. Every doc leaves
     * this method with a {@code propertySetName} that identifies its order.
     */
    private void assignOrderGroups(List<StagedDoc> staged) {
        Map<String, List<StagedDoc>> byGroup = new java.util.LinkedHashMap<>();
        for (StagedDoc d : staged) {
            byGroup.computeIfAbsent(d.groupKey != null ? d.groupKey : "__root__", k -> new ArrayList<>()).add(d);
        }

        for (List<StagedDoc> group : byGroup.values()) {
            List<StagedDoc> appraisals = group.stream()
                    .filter(d -> d.fileType == FileType.APPRAISAL).toList();
            String folderLabel = group.get(0).setLabel;

            if (appraisals.size() <= 1) {
                // One (or zero) appraisal → the whole folder is a single order.
                String label = (folderLabel != null && !folderLabel.isBlank())
                        ? folderLabel
                        : (appraisals.isEmpty() ? null : baseName(appraisals.get(0).filenameOnly));
                for (StagedDoc d : group) d.propertySetName = label;
            } else {
                // Several appraisals under one folder → split into one order per appraisal,
                // labelled by the appraisal's own filename (a distinctive property identity).
                for (StagedDoc a : appraisals) a.propertySetName = baseName(a.filenameOnly);
                for (StagedDoc d : group) {
                    if (d.fileType == FileType.APPRAISAL) continue;
                    StagedDoc best = null;
                    int bestScore = 0;
                    for (StagedDoc a : appraisals) {
                        int score = FileMatchingService.filenameMatchScore(d.filenameOnly, a.filenameOnly);
                        if (score > bestScore) { bestScore = score; best = a; }
                    }
                    // No confident filename match → leave in the folder group so the
                    // multi-appraisal NEEDS_ASSIGNMENT path surfaces it for manual pairing.
                    d.propertySetName = best != null ? best.propertySetName : folderLabel;
                }
            }
        }
    }

    /** Map key for an order group: its propertySetName, or "__root__" for the flat/unset group. */
    private static String setKey(String propertySetName) {
        return DocumentContentSniffer.setKeyOf(propertySetName);
    }

    // extractOrderIdentities lives on DocumentContentSniffer — shared with the QC
    // linkage gate, which recomputes the same map live at QC-run time.

    /**
     * S3 content-ID sniff. For every supporting document whose order group holds no
     * appraisal (structural evidence gave no answer — e.g. a "4" folder holding all
     * the batch's engagement letters), read the document's own text and match its
     * stated order number / subject address against the batch's appraisal anchors.
     * A unique match re-homes the file into that appraisal's order group, so the
     * normal set-based pairing and Order resolution downstream treat it exactly as
     * if it had been co-located; no match (or an ambiguous one) leaves the file for
     * the NEEDS_ASSIGNMENT manual flow.
     */
    private void sniffLinkUnanchoredDocs(Batch batch, Map<String, DocumentContentSniffer.OrderIdentity> identityBySet) {
        List<BatchFile> appraisals = batch.getFiles().stream()
                .filter(f -> f.getFileType() == FileType.APPRAISAL)
                .toList();
        if (appraisals.isEmpty()) return;

        Set<String> anchorSetKeys = new HashSet<>();
        Map<String, BatchFile> appraisalBySetKey = new HashMap<>();
        List<DocumentContentSniffer.Anchor> anchors = new ArrayList<>();
        for (BatchFile a : appraisals) {
            String key = setKey(a.getPropertySetName());
            anchorSetKeys.add(key);
            appraisalBySetKey.putIfAbsent(key, a);
            anchors.add(contentSniffer.anchorFor(a, identityBySet.get(key)));
        }

        List<String> linkedNotes = new ArrayList<>();
        for (BatchFile f : batch.getFiles()) {
            if (f.getFileType() == FileType.APPRAISAL) continue;
            if (anchorSetKeys.contains(setKey(f.getPropertySetName()))) continue; // structurally linked

            String text = contentSniffer.sniffableText(f);
            Optional<DocumentContentSniffer.SniffMatch> match = contentSniffer.match(text, anchors);
            if (match.isEmpty()) continue;

            DocumentContentSniffer.SniffMatch m = match.get();
            BatchFile anchorAppraisal = appraisalBySetKey.get(m.anchor().setKey());
            if (anchorAppraisal == null) continue;

            f.setPropertySetName(anchorAppraisal.getPropertySetName());
            String note = "Linked to order \"" + m.anchor().displayName() + "\" by document content ("
                    + m.reason() + "; confidence " + m.confidence() + ").";
            f.setDocumentQualityFlags(f.getDocumentQualityFlags() == null
                    ? note : f.getDocumentQualityFlags() + "\n" + note);
            linkedNotes.add("\"" + f.getFilename() + "\" → order \"" + m.anchor().displayName()
                    + "\" (" + m.reason() + ")");
            log.info("Batch {} — content sniff linked '{}' ({}) to order group '{}' ({}, confidence {})",
                    batch.getParentBatchId(), f.getFilename(), f.getFileType(),
                    m.anchor().displayName(), m.reason(), m.confidence());
        }

        if (!linkedNotes.isEmpty()) {
            String note = linkedNotes.size() + " supporting document(s) were automatically linked to their "
                    + "orders by the identifiers stated inside the document:\n" + String.join("\n", linkedNotes);
            String existing = batch.getIntakeWarnings();
            batch.setIntakeWarnings(existing == null || existing.isBlank() ? note : existing + "\n" + note);
        }
    }

    private void cleanupStaging(Path stagingDir) {
        try {
            if (Files.exists(stagingDir)) {
                try (var paths = Files.walk(stagingDir)) {
                    paths.sorted((a, b) -> b.compareTo(a)).forEach(p -> {
                        try { Files.deleteIfExists(p); } catch (IOException ignored) { }
                    });
                }
            }
        } catch (IOException e) {
            log.warn("Failed to clean up staging dir {}: {}", stagingDir, e.getMessage());
        }
    }

    /** Canonical type-folder keyword for a folder segment, or null if it names no doc type. */
    private static String typeFolderKeyword(String segment) {
        if (segment == null) return null;
        String s = segment.trim().toLowerCase();
        if (s.startsWith("appraisal")) return "appraisal"; // covers appraisal_xml too
        if (s.startsWith("engagement") || s.startsWith("eagagement")
                || s.equals("order") || s.equals("orders")) return "engagement";
        if (s.startsWith("contract") || s.startsWith("purchase") || s.startsWith("agreement")) return "contract";
        return null;
    }

    private static FileType fileTypeForFolder(String keyword) {
        return switch (keyword) {
            case "engagement" -> FileType.ENGAGEMENT;
            case "contract" -> FileType.CONTRACT;
            default -> FileType.APPRAISAL;
        };
    }

    /**
     * Classify a PDF by filename when the ZIP gives no type folder (flat order layout).
     * Contract/engagement keywords win; anything else defaults to APPRAISAL and is
     * flagged for review so nothing is dropped and no order is left without an anchor.
     */
    private static FileType classifyPdfByFilename(String filename) {
        String n = filename == null ? "" : filename.toLowerCase();
        if (n.contains("engagement") || n.contains("eng letter") || n.contains("engage")
                || n.contains("order form") || n.contains("assignment")) {
            return FileType.ENGAGEMENT;
        }
        if (n.contains("contract") || n.contains("purchase") || n.contains("agreement")
                || n.contains("as-is") || n.contains("as is") || n.contains("addendum")
                || n.contains("disclosure") || n.contains("hoa") || n.contains("counter")) {
            return FileType.CONTRACT;
        }
        return FileType.APPRAISAL;
    }

    /** MISMO 2.6 GSE appraisal XML detection by header sniff. */
    private static boolean isMismoXml(byte[] bytes) {
        String header = new String(bytes, 0, Math.min(bytes.length, 2048),
                java.nio.charset.StandardCharsets.UTF_8);
        return header.contains("VALUATION_RESPONSE") || header.contains("MISMO")
                || header.contains("ValuationResponse") || header.contains("UCDP_");
    }

    /**
     * The batch-local order-folder path for a ZIP entry: the folder chain up to (but
     * not including) a type folder, or the full folder chain when there is none.
     * Null when the file sits at the ZIP root with no enclosing folder.
     *   "EQSS/xBatch/appraisal/f.pdf" → "EQSS/xBatch"
     *   "VIKAS/1/1/appraisal/f.pdf"   → "VIKAS/1/1"
     *   "xml1/1/f.pdf"                → "xml1/1"   (flat, no type folder)
     *   "appraisal/f.pdf"             → null       (type folder at root, single order)
     *   "f.pdf"                       → null
     */
    static String orderGroupKey(String entryPath) {
        if (entryPath == null || entryPath.isBlank()) return null;
        List<String> segs = new ArrayList<>();
        for (String p : entryPath.replace("\\", "/").split("/")) {
            if (!p.isBlank()) segs.add(p);
        }
        if (segs.size() < 2) return null; // file at root, no folder
        int fileIdx = segs.size() - 1;
        int typeIdx = -1;
        for (int i = 0; i < fileIdx; i++) {
            if (typeFolderKeyword(segs.get(i)) != null) typeIdx = i; // deepest type folder wins
        }
        int endExclusive = typeIdx >= 0 ? typeIdx : fileIdx;
        if (endExclusive <= 0) return null;
        return String.join("/", segs.subList(0, endExclusive));
    }

    /** Leaf filename of a path, original case. */
    private static String leafName(String path) {
        if (path == null || path.isBlank()) return "";
        String t = path.replace("\\", "/");
        while (t.endsWith("/")) t = t.substring(0, t.length() - 1);
        int s = t.lastIndexOf('/');
        return s >= 0 ? t.substring(s + 1) : t;
    }

    /** Last folder segment of a folder path (order label), or null. */
    private static String leafSegment(String folderPath) {
        if (folderPath == null || folderPath.isBlank()) return null;
        String seg = leafName(folderPath).trim();
        return seg.isBlank() ? null : seg;
    }

    /** Filename without its extension. */
    private static String baseName(String filename) {
        if (filename == null) return null;
        String n = leafName(filename);
        int dot = n.lastIndexOf('.');
        return (dot > 0 ? n.substring(0, dot) : n).trim();
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

            // A group with no appraisal is a pool of unlinked documents, not one
            // order — "3 engagement letters found, confirm which applies" would be
            // nonsense there (they belong to 3 different orders). warnIncompleteSets
            // reports that situation truthfully.
            if (appraisals == 0) {
                continue;
            }

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
     * Warn about order groups that are missing required documents — truthfully.
     *
     * Two different situations must never be conflated:
     *  - MISSING: the document is genuinely not in this upload → QC proceeds with
     *    it marked "not provided"; it can be attached to the order later.
     *  - UNLINKED CANDIDATE EXISTS: the document IS in this batch but is not
     *    attached to any order → the fix is the in-app Assign button, never
     *    re-uploading the ZIP.
     * A folder with no appraisal is not an order at all — it is a pool of
     * unlinked documents awaiting assignment.
     */
    private void warnIncompleteSets(Batch batch, Set<String> distinctSets) {
        Set<String> appraisalSets = batch.getFiles().stream()
                .filter(f -> f.getFileType() == FileType.APPRAISAL)
                .map(BatchFile::getPropertySetName)
                .filter(Objects::nonNull)
                .collect(java.util.stream.Collectors.toSet());
        long unlinkedEngagements = batch.getFiles().stream()
                .filter(f -> f.getFileType() == FileType.ENGAGEMENT)
                .filter(f -> f.getPropertySetName() == null || !appraisalSets.contains(f.getPropertySetName()))
                .count();

        List<String> warnings = new ArrayList<>();
        for (String setName : distinctSets) {
            List<BatchFile> setFiles = batch.getFiles().stream()
                    .filter(f -> setName.equals(f.getPropertySetName()))
                    .toList();
            boolean hasAppraisal  = setFiles.stream().anyMatch(f -> f.getFileType() == FileType.APPRAISAL);
            boolean hasEngagement = setFiles.stream().anyMatch(f -> f.getFileType() == FileType.ENGAGEMENT);

            if (!hasAppraisal) {
                warnings.add("Folder \"" + setName + "\" contains " + setFiles.size()
                        + " supporting document(s) but no appraisal — these are unlinked documents, not an "
                        + "order. Assign each one to its order with the Assign button in this batch.");
                log.warn("Batch {} folder '{}' holds only supporting documents — unlinked pool",
                        batch.getParentBatchId(), setName);
            } else if (!hasEngagement) {
                if (unlinkedEngagements > 0) {
                    warnings.add("Order \"" + setName + "\" has no engagement letter linked, but "
                            + unlinkedEngagements + " unlinked engagement letter(s) exist in this batch — "
                            + "assign the correct one with the Assign button before running QC.");
                } else {
                    warnings.add("Order \"" + setName + "\": no engagement letter was included in this upload. "
                            + "QC can still run and will treat it as not provided; attach the letter to this "
                            + "order when it becomes available.");
                }
                log.warn("Batch {} order '{}' has no engagement letter linked ({} unlinked candidate(s) in batch)",
                        batch.getParentBatchId(), setName, unlinkedEngagements);
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
        // An appraisal's order group (propertySetName) already links its supporting docs —
        // a supporting file in the same group is resolvable even if its orderId differs.
        Set<String> appraisalSets = batch.getFiles().stream()
                .filter(f -> f.getFileType() == FileType.APPRAISAL)
                .map(BatchFile::getPropertySetName)
                .filter(s -> s != null && !s.isBlank())
                .collect(java.util.stream.Collectors.toSet());

        for (BatchFile f : batch.getFiles()) {
            if (f.getFileType() == FileType.APPRAISAL) {
                continue;
            }
            String fOrderId = f.getOrderId();
            // Primary check: shares an appraisal's order group (folder-first grouping).
            boolean linked = f.getPropertySetName() != null && !f.getPropertySetName().isBlank()
                    && appraisalSets.contains(f.getPropertySetName());
            // Secondary check: orderId exact match
            if (!linked) {
                linked = fOrderId != null && !fOrderId.isBlank() && appraisalOrderIds.contains(fOrderId);
            }
            // Tertiary check: case-insensitive basename match (covers "ESCA-0019573.xml"
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
        manuallyAssignFile(supportingFileId, appraisalFileId, batchId, admin, false);
    }

    /**
     * As above, plus address/order-number cross-validation: even a manual assignment
     * is blocked when the document's own content confidently identifies it as
     * belonging to a DIFFERENT order in this batch (the reverse of the intake bug —
     * a human dropping the right-looking file into the wrong order). Catches this
     * before it reaches QC rather than after, when it would show up as a bewildering
     * cross-doc mismatch on the wrong order.
     *
     * {@code forceOverride=true} bypasses the check for the rare legitimate case
     * (e.g. the same engagement letter genuinely covers two orders) — the override
     * is recorded on the DocumentMatch for audit.
     *
     * @throws ValidationException with field "addressMismatch" when a conflicting
     *         match was found and {@code forceOverride} is false.
     */
    @Transactional
    public void manuallyAssignFile(Long supportingFileId, Long appraisalFileId, Long batchId, User admin,
                                   boolean forceOverride) {
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

        if (!forceOverride) {
            Optional<String> mismatch = detectAssignmentMismatch(supporting, appraisal);
            if (mismatch.isPresent()) {
                throw new ValidationException("addressMismatch", mismatch.get());
            }
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
                + " on " + java.time.LocalDate.now()
                + (forceOverride ? " (address-mismatch check overridden)" : ""));
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

        // A supporting file resolved to no Order at intake (no confident appraisal
        // match) now has an explicit human-confirmed match — link it to the
        // appraisal's Order retroactively so it's part of that order's document
        // cluster instead of staying permanently unresolved.
        if (appraisal.getOrder() != null && !appraisal.getOrder().equals(supporting.getOrder())) {
            supporting.setOrder(appraisal.getOrder());
            batchFileRepository.save(supporting);
            orderStatusService.recompute(appraisal.getOrder());
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
     * Cross-validate a proposed manual assignment against document content. Scores
     * {@code supporting}'s text against EVERY appraisal anchor in the batch (not just
     * the target) — if the document confidently identifies a DIFFERENT order than the
     * one the admin is assigning it to, that is a real mismatch worth blocking. A
     * unique match confirming the target, a tie, or no signal at all (unreadable PDF,
     * generic template with no identifiers) are all treated as "cannot disprove" and
     * allowed through — this check only fires on positive contrary evidence, never on
     * absence of evidence, matching intake's own "never fail on missing signal" rule.
     */
    private Optional<String> detectAssignmentMismatch(BatchFile supporting, BatchFile appraisal) {
        Batch batch = appraisal.getBatch();
        List<BatchFile> appraisals = batch.getFiles().stream()
                .filter(f -> f.getFileType() == FileType.APPRAISAL && f.isActive())
                .toList();
        if (appraisals.size() <= 1) return Optional.empty(); // nothing else to conflict with

        Map<String, DocumentContentSniffer.OrderIdentity> identityBySet = contentSniffer.extractOrderIdentities(batch);
        Map<String, BatchFile> appraisalBySetKey = new HashMap<>();
        List<DocumentContentSniffer.Anchor> anchors = new ArrayList<>();
        for (BatchFile a : appraisals) {
            String key = setKey(a.getPropertySetName());
            appraisalBySetKey.putIfAbsent(key, a);
            anchors.add(contentSniffer.anchorFor(a, identityBySet.get(key)));
        }

        String text = contentSniffer.sniffableText(supporting);
        List<DocumentContentSniffer.SniffMatch> top = contentSniffer.candidatesAtTopScore(text, anchors);
        if (top.size() != 1) return Optional.empty(); // no signal, or tied — cannot disprove the assignment

        DocumentContentSniffer.SniffMatch m = top.get(0);
        String targetKey = setKey(appraisal.getPropertySetName());
        if (m.anchor().setKey().equals(targetKey)) return Optional.empty(); // confirms the assignment

        return Optional.of("\"" + supporting.getFilename() + "\" appears to belong to a different order — its "
                + m.reason() + ", which points to \"" + m.anchor().displayName() + "\", not \""
                + (appraisal.getPropertySetName() != null ? appraisal.getPropertySetName() : appraisal.getFilename())
                + "\". Re-check before assigning, or confirm to override.");
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

    /** Strip characters that are unsafe in filesystem path segments. */
    private static String sanitizeFolderName(String name) {
        return name.replaceAll("[/\\\\:*?\"<>|]", "_").trim();
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
