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
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.stream.Collectors;

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
            Optional<BatchFile> fuzzyMatch = findBestFilenameMatch(appraisalFile, FileType.ENGAGEMENT);
            if (fuzzyMatch.isPresent()) {
                log.info("Matched engagement {} for appraisal {} using normalized filename fallback",
                        fuzzyMatch.get().getFilename(), appraisalFile.getFilename());
                return fuzzyMatch;
            }

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

        return contracts.isEmpty() ? findBestFilenameMatch(appraisalFile, FileType.CONTRACT) : Optional.of(contracts.get(0));
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

    private Optional<BatchFile> findBestFilenameMatch(BatchFile appraisalFile, FileType targetType) {
        List<BatchFile> candidates = batchFileRepository.findByBatchIdAndFileType(
                appraisalFile.getBatch().getId(), targetType);

        String appraisalKey = normalizedMatchKey(appraisalFile.getFilename());
        Set<String> appraisalTokens = matchTokens(appraisalFile.getFilename());

        BatchFile best = null;
        int bestScore = 0;
        for (BatchFile candidate : candidates) {
            if (candidate.getFilename() == null || candidate.getFilename().startsWith("._")) {
                continue;
            }

            String candidateKey = normalizedMatchKey(candidate.getFilename());
            int score = scoreMatch(appraisalKey, appraisalTokens, candidateKey, matchTokens(candidate.getFilename()));
            if (score > bestScore) {
                best = candidate;
                bestScore = score;
            }
        }

        return bestScore >= 2 ? Optional.of(best) : Optional.empty();
    }

    private static int scoreMatch(String appraisalKey, Set<String> appraisalTokens, String candidateKey, Set<String> candidateTokens) {
        if (appraisalKey.equals(candidateKey)) {
            return 100;
        }
        if (appraisalKey.contains(candidateKey) || candidateKey.contains(appraisalKey)) {
            return 50;
        }

        Set<String> overlap = new HashSet<>(appraisalTokens);
        overlap.retainAll(candidateTokens);

        boolean sharesNumber = overlap.stream().anyMatch(t -> t.matches("\\d+"));
        boolean sharesName = overlap.stream().anyMatch(t -> !t.matches("\\d+"));
        return sharesNumber && sharesName ? overlap.size() : 0;
    }

    private static Set<String> matchTokens(String filename) {
        String normalized = normalizedMatchKey(filename);
        if (normalized.isBlank()) {
            return Set.of();
        }
        return Arrays.stream(normalized.split(" "))
                .filter(token -> !token.isBlank())
                .collect(Collectors.toSet());
    }

    private static String normalizedMatchKey(String filename) {
        if (filename == null) {
            return "";
        }

        String value = filename.toLowerCase()
                .replaceAll("\\.[^.]+$", "")
                .replaceAll("[^a-z0-9]+", " ")
                .replaceAll("\\b(purchase|agreement|contract|order|form|appraisal|report|pdf)\\b", " ")
                .replaceAll("\\b(trace|terrace)\\b", "tr")
                .replaceAll("\\b(court)\\b", "ct")
                .replaceAll("\\b(circle)\\b", "cir")
                .replaceAll("\\b(street)\\b", "st")
                .replaceAll("\\b(road)\\b", "rd")
                .replaceAll("\\b(avenue)\\b", "ave")
                .replaceAll("\\b(north|south|east|west|n|s|e|w|ne|nw|se|sw|ct|cir|st|rd|ave|dr|ln|way)\\b", " ")
                .replaceAll("\\s+", " ")
                .trim();

        return value;
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
