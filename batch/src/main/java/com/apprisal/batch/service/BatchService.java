package com.apprisal.batch.service;

import com.apprisal.common.entity.*;
import com.apprisal.common.exception.BatchProcessingException;
import com.apprisal.common.exception.ResourceNotFoundException;
import com.apprisal.common.exception.ValidationException;
import com.apprisal.common.repository.BatchFileRepository;
import com.apprisal.common.repository.BatchRepository;
import com.apprisal.common.service.AuditLogService;
import com.apprisal.common.service.FileMatchingService;
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
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
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
    private final AuditLogService auditLogService;

    @Value("${app.storage.path:./uploads}")
    private String storagePath;

    public BatchService(BatchRepository batchRepository,
            BatchFileRepository batchFileRepository,
            AuditLogService auditLogService) {
        this.batchRepository = batchRepository;
        this.batchFileRepository = batchFileRepository;
        this.auditLogService = auditLogService;
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

    /**
     * Delete a batch and all its associated files.
     * 
     * @param batchId the batch ID to delete
     * @throws ResourceNotFoundException if batch not found
     */
    @Transactional
    public void deleteBatch(@NonNull Long batchId) {
        Batch batch = batchRepository.findById(batchId)
                .orElseThrow(() -> new ResourceNotFoundException("Batch", "id", batchId));

        log.info("Deleting batch {} with {} files", batch.getParentBatchId(), batch.getFiles().size());

        // Delete storage files
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
            Path batchDir = Paths.get(storagePath, batch.getClient().getId().toString(), batch.getParentBatchId());
            if (Files.exists(batchDir)) {
                Files.walk(batchDir)
                        .sorted((a, b) -> b.compareTo(a)) // Delete files before directories
                        .forEach(path -> {
                            try {
                                Files.deleteIfExists(path);
                            } catch (IOException e) {
                                log.warn("Failed to delete path {}: {}", path, e.getMessage());
                            }
                        });
            }
        } catch (IOException e) {
            log.warn("Failed to clean up batch directory: {}", e.getMessage());
        }

        // Database will cascade delete files due to orphanRemoval
        batchRepository.delete(batch);
        log.info("Batch {} deleted successfully", batch.getParentBatchId());
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
                return existing.get();
            }
        }

        String originalFilename = file.getOriginalFilename();
        String parentBatchId = originalFilename != null
                ? originalFilename.replace(".zip", "")
                : "BATCH_" + UUID.randomUUID().toString().substring(0, 8).toUpperCase();

        log.info("Creating batch '{}' for client '{}' by user '{}'",
                parentBatchId, client.getCode(), creator.getUsername());

        Batch batch = Batch.builder()
                .parentBatchId(parentBatchId)
                .client(client)
                .status(BatchStatus.VALIDATING)
                .createdBy(creator)
                .build();
        batch.setFileHash(fileHash);

        batch = Objects.requireNonNull(batchRepository.save(batch));

        try {
            Path batchDir = Paths.get(storagePath, client.getCode(), parentBatchId);
            Files.createDirectories(batchDir);
            extractAndValidateZip(file, batch, batchDir);
            batch.setStatus(BatchStatus.QC_PROCESSING);
            log.info("Batch '{}' processed successfully with {} files",
                    parentBatchId, batch.getFiles().size());
        } catch (ValidationException e) {
            log.warn("Batch validation failed for '{}': {}", parentBatchId, e.getMessage());
            batch.setStatus(BatchStatus.VALIDATION_FAILED);
            batch.setErrorMessage(e.getMessage());
            throw e;
        } catch (IOException e) {
            log.error("IO error processing batch '{}': {}", parentBatchId, e.getMessage(), e);
            batch.setStatus(BatchStatus.VALIDATION_FAILED);
            batch.setErrorMessage("Failed to process ZIP file: " + e.getMessage());
            throw new BatchProcessingException(batch.getId(), "Failed to process ZIP file: " + e.getMessage(), e);
        } catch (Exception e) {
            log.error("Unexpected error processing batch '{}': {}", parentBatchId, e.getMessage(), e);
            batch.setStatus(BatchStatus.ERROR);
            batch.setErrorMessage("Unexpected error: " + e.getMessage());
            throw new BatchProcessingException(batch.getId(), "Unexpected error: " + e.getMessage(), e);
        }

        batch = batchRepository.save(batch);
        auditLogService.logEntity(creator, "BATCH_UPLOAD", "Batch", batch.getId());

        return batch;
    }

    private void extractAndValidateZip(MultipartFile file, Batch batch, Path batchDir) throws IOException {
        boolean hasAppraisalFolder = false;
        boolean hasEngagementFolder = false;
        int entryCount = 0;

        try (ZipInputStream zis = new ZipInputStream(file.getInputStream())) {
            ZipEntry entry;
            while ((entry = zis.getNextEntry()) != null) {
                entryCount++;
                if (entryCount > MAX_ZIP_ENTRIES) {
                    throw new ValidationException("ZIP file contains too many entries (max: " + MAX_ZIP_ENTRIES + ")");
                }

                String entryName = entry.getName();

                // Security: prevent path traversal attacks
                if (entryName.contains("..")) {
                    throw new ValidationException("Invalid ZIP entry path: " + entryName);
                }

                if (entry.isDirectory()) {
                    if (entryName.toLowerCase().contains("appraisal")) {
                        hasAppraisalFolder = true;
                    }
                    if (entryName.toLowerCase().contains("engagement")) {
                        hasEngagementFolder = true;
                    }
                    continue;
                }

                if (!entryName.toLowerCase().endsWith(".pdf")) {
                    continue;
                }

                FileType fileType;
                String lower = entryName.toLowerCase();
                if (lower.contains("appraisal")) {
                    fileType = FileType.APPRAISAL;
                    hasAppraisalFolder = true;
                } else if (lower.contains("engagement") || lower.contains("eagagement") || lower.contains("order")) {
                    fileType = FileType.ENGAGEMENT;
                    hasEngagementFolder = true;
                } else if (lower.contains("contract") || lower.contains("purchase") || lower.contains("agreement")) {
                    fileType = FileType.CONTRACT;
                } else {
                    continue;
                }

                String filename = Paths.get(entryName).getFileName().toString();
                Path filePath = batchDir.resolve(fileType.name().toLowerCase()).resolve(filename);
                Files.createDirectories(filePath.getParent());
                Files.copy(zis, filePath, java.nio.file.StandardCopyOption.REPLACE_EXISTING);

                BatchFile batchFile = BatchFile.builder()
                        .batch(batch)
                        .fileType(fileType)
                        .filename(filename)
                        .originalPath(entryName)
                        .storagePath(filePath.toString())
                        .fileSize(Files.size(filePath))
                        .status(FileStatus.PENDING)
                        .orderId(FileMatchingService.extractOrderId(filename))
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
        Batch batch = batchRepository.findById(batchId)
                .orElseThrow(() -> new ResourceNotFoundException("Batch", "id", batchId));
        batch.setAssignedReviewer(reviewer);
        batch.setStatus(BatchStatus.REVIEW_PENDING);
        log.info("Assigned batch {} to reviewer {}", batchId, reviewer.getUsername());
        return batchRepository.save(batch);
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
}
