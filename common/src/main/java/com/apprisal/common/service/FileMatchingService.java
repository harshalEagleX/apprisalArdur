package com.apprisal.common.service;

import com.apprisal.common.entity.BatchFile;
import com.apprisal.common.entity.FileType;
import com.apprisal.common.repository.BatchFileRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

/**
 * Service for matching appraisal files with their corresponding engagement
 * letters.
 * Uses orderId extracted from filename (e.g., appraisal_001.pdf → orderId =
 * "001").
 */
@Service
public class FileMatchingService {

    private static final Logger log = LoggerFactory.getLogger(FileMatchingService.class);

    private final BatchFileRepository batchFileRepository;

    public FileMatchingService(BatchFileRepository batchFileRepository) {
        this.batchFileRepository = batchFileRepository;
    }

    /**
     * Find the engagement letter that matches an appraisal file.
     * Matching is done by orderId extracted from filename.
     *
     * @param appraisalFile The appraisal file to find engagement for
     * @return Optional containing the matching engagement file, or empty if not
     *         found
     */
    public Optional<BatchFile> findEngagementForAppraisal(BatchFile appraisalFile) {
        if (appraisalFile.getFileType() != FileType.APPRAISAL) {
            throw new IllegalArgumentException("Expected APPRAISAL file type, got: " + appraisalFile.getFileType());
        }

        String orderId = appraisalFile.getOrderId();
        if (orderId == null || orderId.isBlank()) {
            log.warn("Appraisal file {} has no orderId, cannot match with engagement", appraisalFile.getFilename());
            return Optional.empty();
        }

        List<BatchFile> engagements = batchFileRepository.findByBatchIdAndOrderIdAndFileType(
                appraisalFile.getBatch().getId(),
                orderId,
                FileType.ENGAGEMENT);

        if (engagements.isEmpty()) {
            log.warn("No engagement found for appraisal {} (orderId={})",
                    appraisalFile.getFilename(), orderId);
            return Optional.empty();
        }

        if (engagements.size() > 1) {
            log.warn("Multiple engagements ({}) found for orderId={}, using first one",
                    engagements.size(), orderId);
        }

        BatchFile engagement = engagements.get(0);
        log.debug("Found engagement {} for appraisal {} (orderId={})",
                engagement.getFilename(), appraisalFile.getFilename(), orderId);

        return Optional.of(engagement);
    }

    /**
     * Get all matched file pairs for a batch.
     *
     * @param batchId The batch ID
     * @return List of file pairs (appraisal + optional engagement)
     */
    public List<FilePair> getMatchedPairs(Long batchId) {
        List<BatchFile> appraisals = batchFileRepository.findByBatchIdAndFileType(batchId, FileType.APPRAISAL);
        List<FilePair> pairs = new ArrayList<>();

        for (BatchFile appraisal : appraisals) {
            if (appraisal.getFilename().startsWith("._")) continue;

            Optional<BatchFile> engagement = findEngagementForAppraisal(appraisal);
            Optional<BatchFile> contract   = findContractForAppraisal(appraisal);
            pairs.add(new FilePair(appraisal, engagement.orElse(null), contract.orElse(null)));
        }

        log.info("Found {} file pairs for batch {}", pairs.size(), batchId);
        return pairs;
    }

    public Optional<BatchFile> findContractForAppraisal(BatchFile appraisalFile) {
        String orderId = appraisalFile.getOrderId();
        if (orderId == null || orderId.isBlank()) return Optional.empty();

        List<BatchFile> contracts = batchFileRepository.findByBatchIdAndOrderIdAndFileType(
                appraisalFile.getBatch().getId(), orderId, FileType.CONTRACT);

        return contracts.isEmpty() ? Optional.empty() : Optional.of(contracts.get(0));
    }

    /**
     * Extract orderId from filename.
     * Pattern: {type}_{orderId}.pdf → returns orderId
     * Example: appraisal_001.pdf → "001"
     */
    public static String extractOrderId(String filename) {
        if (filename == null || filename.isBlank()) {
            return null;
        }

        // Remove extension
        String baseName = filename.replaceAll("\\.[^.]+$", "");

        // Extract part after last underscore
        int lastUnderscore = baseName.lastIndexOf('_');
        if (lastUnderscore >= 0 && lastUnderscore < baseName.length() - 1) {
            return baseName.substring(lastUnderscore + 1);
        }

        // Fallback: use full basename
        return baseName;
    }

    /**
     * DTO representing a matched pair of appraisal and engagement files.
     */
    public static class FilePair {
        private final BatchFile appraisal;
        private final BatchFile engagement;
        private final BatchFile contract;

        public FilePair(BatchFile appraisal, BatchFile engagement) {
            this(appraisal, engagement, null);
        }

        public FilePair(BatchFile appraisal, BatchFile engagement, BatchFile contract) {
            this.appraisal  = appraisal;
            this.engagement = engagement;
            this.contract   = contract;
        }

        public BatchFile getAppraisal()  { return appraisal; }
        public BatchFile getEngagement() { return engagement; }
        public BatchFile getContract()   { return contract; }

        public boolean hasEngagement() { return engagement != null; }
        public boolean hasContract()   { return contract != null; }

        public Path getAppraisalPath() {
            return Paths.get(appraisal.getStoragePath());
        }

        public Path getEngagementPath() {
            return engagement != null ? Paths.get(engagement.getStoragePath()) : null;
        }

        public Path getContractPath() {
            return contract != null ? Paths.get(contract.getStoragePath()) : null;
        }
    }
}
