package com.shal.common.service;

import com.shal.common.entity.BatchFile;
import com.shal.common.entity.DocumentMatch;
import com.shal.common.entity.FileType;
import com.shal.common.repository.BatchFileRepository;
import com.shal.common.repository.DocumentMatchRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.ObjectMapper;

import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Objects;
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
    private final DocumentMatchRepository documentMatchRepository;
    private final BusinessEventService businessEventService;
    private final ObjectMapper objectMapper;

    public FileMatchingService(BatchFileRepository batchFileRepository,
                               DocumentMatchRepository documentMatchRepository,
                               BusinessEventService businessEventService,
                               ObjectMapper objectMapper) {
        this.batchFileRepository = batchFileRepository;
        this.documentMatchRepository = documentMatchRepository;
        this.businessEventService = businessEventService;
        this.objectMapper = objectMapper;
    }

    /**
     * Find the engagement letter that matches an appraisal file.
     * Prefers same-set matching for multi-property batches.
     *
     * @param appraisalFile The appraisal file to find engagement for
     * @return Optional containing the matching engagement file, or empty if not found
     */
    @Transactional
    public Optional<BatchFile> findEngagementForAppraisal(BatchFile appraisalFile) {
        if (appraisalFile.getFileType() != FileType.APPRAISAL) {
            throw new IllegalArgumentException("Expected APPRAISAL file type, got: " + appraisalFile.getFileType());
        }
        return findSupportingFile(appraisalFile, FileType.ENGAGEMENT);
    }

    /**
     * Get all matched file pairs for a batch.
     *
     * For multi-property-set batches (where BatchFile.propertySetName is set),
     * engagement and contract matching is first attempted within the same set.
     * If no match is found within the set, a batch-wide fallback is tried.
     * This prevents cross-set matching (e.g., the engagement letter for "8234 E Pearson"
     * being incorrectly matched to the appraisal for "2307 Merrily Cir N").
     *
     * @param batchId The batch ID
     * @return List of file pairs (appraisal + optional engagement + optional contract)
     */
    @Transactional
    public List<FilePair> getMatchedPairs(Long batchId) {
        List<BatchFile> appraisals = batchFileRepository.findByBatchIdAndFileType(batchId, FileType.APPRAISAL);
        List<FilePair> pairs = new ArrayList<>();

        for (BatchFile appraisal : appraisals) {
            if (appraisal.getFilename() != null && appraisal.getFilename().startsWith("._")) {
                continue;
            }
            // Superseded means this exact document already exists (and was/being
            // processed) on its resolved Order — a pure re-upload duplicate that must
            // not trigger a second QC run.
            if (!appraisal.isActive()) {
                continue;
            }

            Optional<BatchFile> xml        = findSupportingFile(appraisal, FileType.APPRAISAL_XML);
            Optional<BatchFile> engagement = findSupportingFile(appraisal, FileType.ENGAGEMENT);
            Optional<BatchFile> contract   = findSupportingFile(appraisal, FileType.CONTRACT);
            pairs.add(new FilePair(appraisal, xml.orElse(null),
                                   engagement.orElse(null), contract.orElse(null)));
        }

        log.debug("Found {} file pairs for batch {}", pairs.size(), batchId);
        return pairs;
    }

    /**
     * Order-grained analogue of {@link #getMatchedPairs(Long)}: build one {@link FilePair} per
     * active appraisal belonging to the given Order, resolving each appraisal's supporting XML /
     * engagement / contract with the exact same set-aware matching used batch-wide. This is the
     * pairing entry point for Order-scoped QC (the Order, not the Batch, is the QC unit) so a run
     * touches only the order's own documents.
     */
    @Transactional
    public List<FilePair> getMatchedPairsForOrder(Long orderId) {
        List<BatchFile> appraisals = batchFileRepository.findActiveByOrderIdAndFileType(orderId, FileType.APPRAISAL);
        List<FilePair> pairs = new ArrayList<>();
        for (BatchFile appraisal : appraisals) {
            if (appraisal.getFilename() != null && appraisal.getFilename().startsWith("._")) {
                continue;
            }
            if (!appraisal.isActive()) {
                continue;
            }
            Optional<BatchFile> xml        = findSupportingFile(appraisal, FileType.APPRAISAL_XML);
            Optional<BatchFile> engagement = findSupportingFile(appraisal, FileType.ENGAGEMENT);
            Optional<BatchFile> contract   = findSupportingFile(appraisal, FileType.CONTRACT);
            pairs.add(new FilePair(appraisal, xml.orElse(null),
                                   engagement.orElse(null), contract.orElse(null)));
        }
        log.debug("Found {} file pair(s) for order {}", pairs.size(), orderId);
        return pairs;
    }

    /**
     * Find a supporting file (engagement or contract) for an appraisal.
     * When the appraisal has a propertySetName, candidates are first restricted to
     * the same set so that a multi-property ZIP never cross-matches documents.
     *
     * A manual_admin DocumentMatch (created via the admin assign UI) is always
     * honoured and never overwritten by auto-matching logic, even across Re-QC runs.
     */
    private Optional<BatchFile> findSupportingFile(BatchFile appraisal, FileType targetType) {
        // Respect manual admin assignments unconditionally — never overwrite with auto-matching.
        Optional<DocumentMatch> existingMatch = documentMatchRepository
                .findByAppraisalFile_IdAndSupportingFileType(appraisal.getId(), targetType);
        if (existingMatch.isPresent() && "manual_admin".equals(existingMatch.get().getMatchType())) {
            log.debug("Honouring manual admin assignment for appraisal {} type {}", appraisal.getFilename(), targetType);
            return Optional.ofNullable(existingMatch.get().getSupportingFile());
        }

        String setName = appraisal.getPropertySetName();
        if (setName != null && !setName.isBlank()) {
            // Try same-set match first
            List<BatchFile> setCandidates = batchFileRepository
                    .findByBatchIdAndPropertySetNameAndFileType(appraisal.getBatch().getId(), setName, targetType)
                    .stream().filter(BatchFile::isActive).toList();
            if (!setCandidates.isEmpty()) {
                // Use orderId within the set
                String orderId = appraisal.getOrderId();
                if (orderId != null && !orderId.isBlank()) {
                    Optional<BatchFile> exact = setCandidates.stream()
                            .filter(f -> orderId.equals(f.getOrderId()))
                            .min(Comparator.comparing(BatchFile::getId, Comparator.nullsLast(Long::compareTo)));
                    if (exact.isPresent()) {
                        persistMatch(appraisal, targetType,
                                new MatchOutcome(exact, "exact_order_id_in_set", 1.0,
                                        "Exact orderId match within set " + setName + ".",
                                        List.of(), List.of()));
                        return exact;
                    }
                }
                // Fallback: take first candidate in the same set
                BatchFile selected = setCandidates.stream()
                        .min(Comparator.comparing(BatchFile::getId, Comparator.nullsLast(Long::compareTo)))
                        .orElse(null);
                if (selected != null) {
                    double confidence = setCandidates.size() == 1 ? 0.95 : 0.80;
                    persistMatch(appraisal, targetType,
                            new MatchOutcome(Optional.of(selected), "set_first_candidate", confidence,
                                    "First " + targetType + " candidate within set " + setName + ".",
                                    setCandidates.size() > 1 ? setCandidates : List.of(), List.of()));
                    return Optional.of(selected);
                }
            }
            // Set had no candidates — fall through to global matching below
            log.info("No {} found in set '{}' for appraisal {} — trying batch-wide fallback",
                    targetType, setName, appraisal.getFilename());
        }
        // No set or no set-level match: use the original orderId / fuzzy logic
        return matchSupportingFile(appraisal, targetType).supportingFile();
    }

    @Transactional
    public Optional<BatchFile> findContractForAppraisal(BatchFile appraisalFile) {
        return findSupportingFile(appraisalFile, FileType.CONTRACT);
    }

    /**
     * Collect any ambiguous-match warnings across all document pairings for this
     * batch. Returns newline-joined warnings (empty string = all pairings clean).
     * Call after getMatchedPairs() so DocumentMatch rows already exist.
     */
    @Transactional(readOnly = true)
    public String collectMatchWarnings(Long batchId) {
        return documentMatchRepository.findByAppraisalFile_Batch_Id(batchId).stream()
                .map(DocumentMatch::getMatchWarning)
                .filter(w -> w != null && !w.isBlank())
                .collect(java.util.stream.Collectors.joining("\n"));
    }

    /**
     * Confidence score for the engagement letter paired with this appraisal file.
     * Returns empty when no match record exists (no engagement was found at all).
     */
    @Transactional(readOnly = true)
    public Optional<Double> getEngagementMatchConfidence(Long appraisalFileId) {
        return getSupportingMatchConfidence(appraisalFileId, FileType.ENGAGEMENT);
    }

    /**
     * Confidence score for the contract paired with this appraisal file.
     * Returns empty when no contract match record exists.
     */
    @Transactional(readOnly = true)
    public Optional<Double> getContractMatchConfidence(Long appraisalFileId) {
        return getSupportingMatchConfidence(appraisalFileId, FileType.CONTRACT);
    }

    @Transactional(readOnly = true)
    public Optional<Double> getSupportingMatchConfidence(Long appraisalFileId, FileType type) {
        return documentMatchRepository
                .findByAppraisalFile_IdAndSupportingFileType(appraisalFileId, type)
                .map(DocumentMatch::getConfidenceScore);
    }

    private MatchOutcome matchSupportingFile(BatchFile appraisalFile, FileType targetType) {
        if (appraisalFile.getFileType() != FileType.APPRAISAL) {
            throw new IllegalArgumentException("Expected APPRAISAL file type, got: " + appraisalFile.getFileType());
        }

        String orderId = appraisalFile.getOrderId();
        MatchOutcome outcome;
        if (orderId == null || orderId.isBlank()) {
            log.warn("Appraisal file {} has no orderId, cannot match with {}", appraisalFile.getFilename(), targetType);
            outcome = new MatchOutcome(Optional.empty(), "no_order_id", 0.0,
                    "Appraisal file has no orderId; " + targetType + " matching was skipped.",
                    List.of(), List.of());
        } else {
            List<BatchFile> exactMatches = batchFileRepository.findByBatchIdAndOrderIdAndFileType(
                    appraisalFile.getBatch().getId(), orderId, targetType)
                    .stream().filter(BatchFile::isActive).toList();

            if (!exactMatches.isEmpty()) {
                List<BatchFile> orderedMatches = exactMatches.stream()
                        .sorted(Comparator.comparing(BatchFile::getId, Comparator.nullsLast(Long::compareTo)))
                        .toList();
                BatchFile selected = orderedMatches.get(0);
                double confidence = orderedMatches.size() == 1 ? 1.0 : 0.80;
                String reason = orderedMatches.size() == 1
                        ? "Exact orderId match on " + orderId + "."
                        : "Multiple " + targetType + " files shared orderId " + orderId + "; first candidate selected.";
                if (orderedMatches.size() > 1) {
                    log.warn("Multiple {} files ({}) found for orderId={}, using first one",
                            targetType, orderedMatches.size(), orderId);
                }
                outcome = new MatchOutcome(Optional.of(selected), "exact_order_id", confidence, reason,
                        orderedMatches.size() > 1 ? orderedMatches : List.of(), List.of());
            } else {
                outcome = findBestFilenameMatch(appraisalFile, targetType);
            }
        }

        persistMatch(appraisalFile, targetType, outcome);
        return outcome;
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

    private MatchOutcome findBestFilenameMatch(BatchFile appraisalFile, FileType targetType) {
        List<BatchFile> candidates = batchFileRepository.findByBatchIdAndFileType(
                appraisalFile.getBatch().getId(), targetType)
                .stream().filter(BatchFile::isActive).toList();

        String appraisalKey = normalizedMatchKey(appraisalFile.getFilename());
        Set<String> appraisalTokens = matchTokens(appraisalFile.getFilename());

        BatchFile best = null;
        int bestScore = 0;
        List<ScoredCandidate> scored = new ArrayList<>();
        for (BatchFile candidate : candidates) {
            if (candidate.getFilename() == null || candidate.getFilename().startsWith("._")) {
                continue;
            }

            String candidateKey = normalizedMatchKey(candidate.getFilename());
            int score = scoreMatch(appraisalKey, appraisalTokens, candidateKey, matchTokens(candidate.getFilename()));
            scored.add(new ScoredCandidate(candidate, score));
            if (score > bestScore) {
                best = candidate;
                bestScore = score;
            }
        }

        scored.sort(Comparator.comparingInt(ScoredCandidate::score).reversed());
        final int selectedScore = bestScore;
        List<BatchFile> ambiguous = scored.stream()
                .filter(c -> c.score() > 0 && c.score() == selectedScore)
                .map(ScoredCandidate::file)
                .toList();
        List<BatchFile> rejected = scored.stream()
                .filter(c -> c.score() > 0 && c.score() < selectedScore)
                .limit(5)
                .map(ScoredCandidate::file)
                .toList();

        if (bestScore < 2 || best == null) {
            // Last resort: when there is exactly ONE file of this type in the batch AND
            // this is a single-order batch (exactly 1 appraisal), use it unambiguously.
            // Restricting to appraisalCount == 1 prevents a 3-order batch from silently
            // grabbing the wrong engagement letter when only one survives fuzzy scoring.
            long appraisalCount = batchFileRepository.countByBatchIdAndFileType(
                    appraisalFile.getBatch().getId(), FileType.APPRAISAL);
            if (candidates.size() == 1 && appraisalCount == 1) {
                BatchFile sole = candidates.get(0);
                log.info("Single-file fallback: using sole {} '{}' for appraisal '{}' (orderId/name match failed, 1 candidate, {} appraisals in batch)",
                        targetType, sole.getFilename(), appraisalFile.getFilename(), appraisalCount);
                return new MatchOutcome(Optional.of(sole), "single_file_fallback", 0.70,
                        "Only one " + targetType + " exists in this batch; selected by single-file fallback.",
                        List.of(), List.of());
            }
            log.warn("No {} found for appraisal {} using orderId or filename fallback",
                    targetType, appraisalFile.getFilename());
            return new MatchOutcome(Optional.empty(), "missing", 0.0,
                    "No " + targetType + " candidate matched by orderId or filename heuristics.",
                    List.of(), candidates);
        }

        double confidence = bestScore >= 100 ? 0.90 : bestScore >= 50 ? 0.78 : Math.min(0.70, 0.45 + (bestScore * 0.05));
        if (ambiguous.size() > 1) {
            confidence = Math.min(confidence, 0.72);
        }

        log.debug("Matched {} {} for appraisal {} via fallback (score={}, confidence={})",
                targetType, best.getFilename(), appraisalFile.getFilename(), bestScore, confidence);
        return new MatchOutcome(Optional.of(best), "fuzzy_name", confidence,
                "Filename heuristic selected best candidate with score " + bestScore + ".",
                ambiguous.size() > 1 ? ambiguous : List.of(), rejected);
    }

    private void persistMatch(BatchFile appraisalFile, FileType targetType, MatchOutcome outcome) {
        String ambiguousJson = toJson(outcome.ambiguousCandidates().stream().map(this::candidatePayload).toList());
        String rejectedJson = toJson(outcome.rejectedCandidates().stream().map(this::candidatePayload).toList());
        DocumentMatch match = documentMatchRepository
                .findByAppraisalFile_IdAndSupportingFileType(appraisalFile.getId(), targetType)
                .orElseGet(DocumentMatch::new);

        // Never overwrite a manual admin assignment with auto-matching results.
        if (match.getId() != null && "manual_admin".equals(match.getMatchType())) {
            return;
        }

        boolean isNew = match.getId() == null;
        boolean changed = isNew
                || !Objects.equals(match.getSupportingFile() != null ? match.getSupportingFile().getId() : null,
                        outcome.supportingFile().map(BatchFile::getId).orElse(null))
                || match.getSupportingFileType() != targetType
                || !Objects.equals(match.getMatchType(), outcome.matchType())
                || !Objects.equals(match.getConfidenceScore(), outcome.confidenceScore())
                || !Objects.equals(match.getMatchReason(), outcome.matchReason())
                || !Objects.equals(match.getAmbiguousCandidatesJson(), ambiguousJson)
                || !Objects.equals(match.getRejectedCandidatesJson(), rejectedJson);

        if (!changed) {
            return;
        }

        match.setAppraisalFile(appraisalFile);
        match.setSupportingFile(outcome.supportingFile().orElse(null));
        match.setSupportingFileType(targetType);
        match.setMatchType(outcome.matchType());
        match.setConfidenceScore(outcome.confidenceScore());
        match.setMatchReason(outcome.matchReason());
        match.setAmbiguousCandidatesJson(ambiguousJson);
        match.setRejectedCandidatesJson(rejectedJson);
        // Flag ambiguous picks so the admin is told to verify the pairing.
        // Multiple equally-plausible candidates means we guessed — record that.
        if (!outcome.ambiguousCandidates().isEmpty() && outcome.supportingFile().isPresent()) {
            String names = outcome.ambiguousCandidates().stream()
                    .map(BatchFile::getFilename)
                    .collect(java.util.stream.Collectors.joining(", "));
            match.setMatchWarning(targetType + " match is ambiguous: selected \""
                    + outcome.supportingFile().get().getFilename()
                    + "\" from " + (outcome.ambiguousCandidates().size() + 1)
                    + " equally-plausible candidates (" + names + "). Verify the correct document was paired.");
        } else {
            match.setMatchWarning(null);
        }

        DocumentMatch saved = documentMatchRepository.save(match);
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("supporting_file_type", targetType.name());
        payload.put("supporting_file_id", outcome.supportingFile().map(BatchFile::getId).orElse(null));
        payload.put("match_type", outcome.matchType());
        payload.put("confidence_score", outcome.confidenceScore());
        payload.put("match_reason", outcome.matchReason());

        businessEventService.record("FILE_MATCHED", null, "java",
                outcome.supportingFile().isPresent() ? "MATCHED" : "MISSING",
                "DocumentMatch", saved.getId(),
                appraisalFile.getBatch() != null ? appraisalFile.getBatch().getId() : null,
                appraisalFile.getId(), null, null, payload);
    }

    private Map<String, Object> candidatePayload(BatchFile file) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("id", file.getId());
        payload.put("filename", file.getFilename());
        payload.put("order_id", file.getOrderId());
        payload.put("file_type", file.getFileType() != null ? file.getFileType().name() : null);
        return payload;
    }

    private String toJson(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (Exception e) {
            log.warn("Could not serialize document match candidates: {}", e.getMessage());
            return "[]";
        }
    }

    // package-private (not private) so the pairing logic below is directly
    // testable: it decides WHICH engagement letter pairs with WHICH appraisal,
    // and a wrong pairing silently QCs a report against another order's letter.
    static int scoreMatch(String appraisalKey, Set<String> appraisalTokens, String candidateKey, Set<String> candidateTokens) {
        if (appraisalKey.isBlank() || candidateKey.isBlank()) {
            return 0;
        }
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

    static Set<String> matchTokens(String filename) {
        String normalized = normalizedMatchKey(filename);
        if (normalized.isBlank()) {
            return Set.of();
        }
        return Arrays.stream(normalized.split(" "))
                .filter(token -> !token.isBlank())
                .collect(Collectors.toSet());
    }

    static String normalizedMatchKey(String filename) {
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
     * Public filename-similarity score reused by the intake pipeline when it must
     * split several appraisals that share a single type folder into separate orders
     * (folder-first grouping, filename fallback). Higher = more similar; 0 = unrelated.
     * Same normalization/scoring the internal fuzzy matcher uses, so intake grouping
     * and QC-time pairing agree on what "the same property" means.
     */
    public static int filenameMatchScore(String a, String b) {
        return scoreMatch(normalizedMatchKey(a), matchTokens(a), normalizedMatchKey(b), matchTokens(b));
    }

    /** Public accessor for the normalized address/property key derived from a filename. */
    public static String filenameMatchKey(String filename) {
        return normalizedMatchKey(filename);
    }

    private record ScoredCandidate(BatchFile file, int score) {}

    private record MatchOutcome(Optional<BatchFile> supportingFile,
                                String matchType,
                                double confidenceScore,
                                String matchReason,
                                List<BatchFile> ambiguousCandidates,
                                List<BatchFile> rejectedCandidates) {}

    /**
     * DTO representing a matched set of appraisal, XML, engagement, and contract files.
     */
    public static class FilePair {
        private final BatchFile appraisal;
        private final BatchFile appraisalXml;   // MISMO 2.6 GSE XML, may be null
        private final BatchFile engagement;
        private final BatchFile contract;

        public FilePair(BatchFile appraisal, BatchFile engagement) {
            this(appraisal, null, engagement, null);
        }

        public FilePair(BatchFile appraisal, BatchFile engagement, BatchFile contract) {
            this(appraisal, null, engagement, contract);
        }

        public FilePair(BatchFile appraisal, BatchFile appraisalXml,
                        BatchFile engagement, BatchFile contract) {
            this.appraisal    = appraisal;
            this.appraisalXml = appraisalXml;
            this.engagement   = engagement;
            this.contract     = contract;
        }

        public BatchFile getAppraisal()    { return appraisal; }
        public BatchFile getAppraisalXml() { return appraisalXml; }
        public BatchFile getEngagement()   { return engagement; }
        public BatchFile getContract()     { return contract; }

        public boolean hasEngagement()   { return engagement != null; }
        public boolean hasContract()     { return contract != null; }
        public boolean hasAppraisalXml() { return appraisalXml != null; }

        public Path getAppraisalPath() {
            return Paths.get(appraisal.getStoragePath());
        }

        public Path getAppraisalXmlPath() {
            return appraisalXml != null ? Paths.get(appraisalXml.getStoragePath()) : null;
        }

        public Path getEngagementPath() {
            return engagement != null ? Paths.get(engagement.getStoragePath()) : null;
        }

        public Path getContractPath() {
            return contract != null ? Paths.get(contract.getStoragePath()) : null;
        }
    }
}
