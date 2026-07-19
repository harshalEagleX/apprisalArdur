package com.shal.qc.service;

import com.shal.common.dto.shalqc.ShalqcResponse;
import com.shal.common.dto.shalqc.ShalqcCard;
import com.shal.common.entity.*;
import com.shal.common.repository.*;
import com.shal.common.service.FileMatchingService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.support.TransactionTemplate;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Regression coverage for Fix 3 (low document-match confidence forces TO_VERIFY)
 * and Fix 2 (ambiguous match warning written to Batch.intakeWarnings).
 *
 * (1) Auto-pass result with high-confidence engagement match stays AUTO_PASS
 * (2) Auto-pass result with low-confidence (< 0.82) engagement match → downgraded TO_VERIFY
 * (3) Auto-pass result with low-confidence contract match → downgraded TO_VERIFY (F3 follow-up)
 * (4) LOW-confidence engagement AND contract: worst one triggers the downgrade
 * (5) Ambiguous DocumentMatch (matchWarning set) → warning written to batch.intakeWarnings
 *
 * Seeds DocumentMatch rows directly (bypasses FileMatchingService) so confidence is
 * deterministic and tests are not sensitive to the matching waterfall.
 */
@SpringBootTest
class MatchConfidenceIntegrationTests {

    @Autowired private QCProcessingService qcProcessingService;
    @Autowired private FileMatchingService fileMatchingService;
    @Autowired private ClientRepository clientRepository;
    @Autowired private UserRepository userRepository;
    @Autowired private BatchRepository batchRepository;
    @Autowired private BatchFileRepository batchFileRepository;
    @Autowired private QCResultRepository qcResultRepository;
    @Autowired private QCRuleResultRepository qcRuleResultRepository;
    @Autowired private DocumentMatchRepository documentMatchRepository;
    @Autowired private ProcessingMetricsRepository processingMetricsRepository;
    @Autowired private TransactionTemplate tx;

    // ── (1) High-confidence engagement → stays AUTO_PASS ─────────────────────

    @Test
    void highConfidenceEngagement_autoPassStaysAutoPass() {
        String tag = "MC_HIGH_" + uuid();
        long[] ids = seedScenario(tag, 1.0, null);
        try {
            qcProcessingService.persistShalqcResult(ids[1], autoPassResponse(),
                    QCModelConfig.defaults(), 0L, 0);
            QCResult r = tx.execute(s -> qcResultRepository.findByBatchFileId(ids[1]).orElseThrow());
            assertThat(r.getQcDecision())
                    .as("confidence=1.0 is clean — AUTO_PASS must NOT be downgraded")
                    .isEqualTo(QCDecision.AUTO_PASS);
            assertThat(r.getReviewerNotes()).as("no reviewer note on clean match").isNull();
        } finally {
            cleanup(tag, ids);
        }
    }

    // ── (2) Low-confidence engagement → downgraded TO_VERIFY ─────────────────

    @Test
    void lowConfidenceEngagement_autoPassDowngradedToVerify() {
        String tag = "MC_LOWENG_" + uuid();
        long[] ids = seedScenario(tag, 0.70, null); // below 0.82 threshold
        try {
            qcProcessingService.persistShalqcResult(ids[1], autoPassResponse(),
                    QCModelConfig.defaults(), 0L, 0);
            QCResult r = tx.execute(s -> qcResultRepository.findByBatchFileId(ids[1]).orElseThrow());
            assertThat(r.getQcDecision())
                    .as("confidence=0.70 (single-file fallback tier) must force review")
                    .isEqualTo(QCDecision.TO_VERIFY);
            assertThat(r.getReviewerNotes())
                    .as("reviewer note explains the reason")
                    .contains("Engagement letter")
                    .contains("70%");
            assertThat(r.getVerifyCount())
                    .as("verifyCount incremented for the synthetic review item")
                    .isGreaterThan(0);
        } finally {
            cleanup(tag, ids);
        }
    }

    // ── (3) Low-confidence contract → downgraded TO_VERIFY ───────────────────

    @Test
    void lowConfidenceContract_autoPassDowngradedToVerify() {
        String tag = "MC_LOWCON_" + uuid();
        // high engagement confidence (0.95) but low contract confidence (0.80)
        long[] ids = seedScenario(tag, 0.95, 0.80);
        try {
            qcProcessingService.persistShalqcResult(ids[1], autoPassResponse(),
                    QCModelConfig.defaults(), 0L, 0);
            QCResult r = tx.execute(s -> qcResultRepository.findByBatchFileId(ids[1]).orElseThrow());
            assertThat(r.getQcDecision())
                    .as("low contract confidence (0.80 < 0.82) must downgrade even when engagement is clean")
                    .isEqualTo(QCDecision.TO_VERIFY);
            assertThat(r.getReviewerNotes())
                    .contains("Contract");
        } finally {
            cleanup(tag, ids);
        }
    }

    // ── (4) Worst of engagement/contract used ────────────────────────────────

    @Test
    void worstConfidenceUsed_whenBothPairsLow() {
        String tag = "MC_WORST_" + uuid();
        // Both below threshold; contract is worse
        long[] ids = seedScenario(tag, 0.78, 0.70);
        try {
            qcProcessingService.persistShalqcResult(ids[1], autoPassResponse(),
                    QCModelConfig.defaults(), 0L, 0);
            QCResult r = tx.execute(s -> qcResultRepository.findByBatchFileId(ids[1]).orElseThrow());
            assertThat(r.getQcDecision()).isEqualTo(QCDecision.TO_VERIFY);
            // The note should name the worst offender (contract at 0.70)
            assertThat(r.getReviewerNotes()).contains("Contract").contains("70%");
        } finally {
            cleanup(tag, ids);
        }
    }

    // ── (5) Match warning written to Batch.intakeWarnings ────────────────────

    @Test
    void ambiguousMatch_warningWrittenToBatchIntakeWarnings() {
        String tag = "MC_WARN_" + uuid();
        long[] ids = seedScenario(tag, 0.80, null); // 0.80 is the "multiple candidates" tier
        // Directly set matchWarning on the DocumentMatch row (simulates tier-2 ambiguity)
        tx.executeWithoutResult(s -> {
            documentMatchRepository.findByAppraisalFile_IdAndSupportingFileType(ids[1], FileType.ENGAGEMENT)
                    .ifPresent(dm -> {
                        dm.setMatchWarning("ENGAGEMENT match is ambiguous: selected \"engage1.pdf\" from 2 equally-plausible candidates (engage2.pdf). Verify the correct document was paired.");
                        documentMatchRepository.save(dm);
                    });
        });

        // Drive collectMatchWarnings + appendIntakeWarning via the component methods directly.
        // These are called inside processBatch (which needs real PDF files), so we exercise
        // the components in isolation here and trust the integration path calls them in order.
        String warnings = tx.execute(s -> fileMatchingService.collectMatchWarnings(ids[0]));
        assertThat(warnings)
                .as("ambiguousMatch warning must be collected for the batch")
                .contains("ambiguous")
                .contains("engage1.pdf");

        // Write it to the batch and confirm it persisted
        tx.executeWithoutResult(s -> qcProcessingService.appendIntakeWarning(ids[0], warnings));
        String stored = tx.execute(s -> batchRepository.findById(ids[0]).orElseThrow().getIntakeWarnings());
        assertThat(stored)
                .as("warning must be persisted on Batch.intakeWarnings")
                .contains("ambiguous");

        cleanup(tag, ids);
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    /**
     * Seed: one appraisal file + optional engagement + optional contract, with specified
     * match confidence. ids = [batchId, appraisalFileId].
     *
     * @param engagementConf confidence for the engagement DocumentMatch, or null to skip
     * @param contractConf   confidence for the contract DocumentMatch, or null to skip
     */
    private long[] seedScenario(String tag, Double engagementConf, Double contractConf) {
        long[] ids = new long[2];
        tx.executeWithoutResult(s -> {
            Client c = clientRepository.save(Client.builder().name(tag).code(tag).status("ACTIVE").build());
            User u = userRepository.save(User.builder()
                    .username(tag).password("x").role(Role.ADMIN).fullName(tag).build());
            Batch b = batchRepository.save(Batch.builder()
                    .parentBatchId(tag).client(c).status(BatchStatus.UPLOADED).createdBy(u).build());
            BatchFile appraisal = batchFileRepository.save(BatchFile.builder()
                    .batch(b).fileType(FileType.APPRAISAL).filename(tag + "_appraisal.pdf")
                    .storagePath("/test/" + tag + "/appraisal.pdf")
                    .status(FileStatus.COMPLETED).build());
            ids[0] = b.getId(); ids[1] = appraisal.getId();

            if (engagementConf != null) {
                BatchFile eng = batchFileRepository.save(BatchFile.builder()
                        .batch(b).fileType(FileType.ENGAGEMENT).filename(tag + "_engagement.pdf")
                        .storagePath("/test/" + tag + "/engagement.pdf")
                        .status(FileStatus.COMPLETED).build());
                DocumentMatch dm = new DocumentMatch();
                dm.setAppraisalFile(appraisal); dm.setSupportingFile(eng);
                dm.setSupportingFileType(FileType.ENGAGEMENT);
                dm.setMatchType("exact_order_id"); dm.setConfidenceScore(engagementConf);
                dm.setMatchReason("seeded for test");
                documentMatchRepository.save(dm);
            }
            if (contractConf != null) {
                BatchFile con = batchFileRepository.save(BatchFile.builder()
                        .batch(b).fileType(FileType.CONTRACT).filename(tag + "_contract.pdf")
                        .storagePath("/test/" + tag + "/contract.pdf")
                        .status(FileStatus.COMPLETED).build());
                DocumentMatch dm = new DocumentMatch();
                dm.setAppraisalFile(appraisal); dm.setSupportingFile(con);
                dm.setSupportingFileType(FileType.CONTRACT);
                dm.setMatchType("exact_order_id"); dm.setConfidenceScore(contractConf);
                dm.setMatchReason("seeded for test");
                documentMatchRepository.save(dm);
            }
        });
        return ids;
    }

    private void cleanup(String tag, long[] ids) {
        tx.executeWithoutResult(s -> {
            documentMatchRepository.findByAppraisalFile_Batch_Id(ids[0]).forEach(documentMatchRepository::delete);
            processingMetricsRepository.deleteByBatchId(ids[0]);
            qcResultRepository.findAllByBatchFileIdOrderByProcessedAtDesc(ids[1])
                    .forEach(r -> { qcRuleResultRepository.findByQcResultId(r.getId()).forEach(qcRuleResultRepository::delete); qcResultRepository.delete(r); });
            batchFileRepository.findByBatchId(ids[0]).forEach(batchFileRepository::delete);
            batchRepository.findById(ids[0]).ifPresent(batchRepository::delete);
            userRepository.findByUsername(tag).ifPresent(userRepository::delete);
            clientRepository.findAll().stream().filter(c -> tag.equals(c.getCode()))
                    .forEach(clientRepository::delete);
        });
    }

    /** Python response where all rules pass (no FAIL/VERIFY) → qcDecision=AUTO_PASS */
    /** A SHALqc all-pass response → AUTO_PASS (no not_satisfied, no review). */
    private static ShalqcResponse autoPassResponse() {
        ShalqcCard pass = new ShalqcCard(
                "S-1", "looks_good", "SUBJECT", "SATISFIED", "Subject", "check", "check",
                null, "ok", "", "", "looks satisfied", List.of(), null, Map.of(),
                null, 0.95, "text", false, List.of(), "judge_v2", "llm", 0.9,
                List.of("subject_x"), null, "informational");
        return new ShalqcResponse("ORD-1", "TEST", "OK", "v2",
                Map.of("satisfied", 1, "not_satisfied", 0, "review", 0,
                       "not_applicable", 0, "cannot_evaluate", 0),
                List.of(pass), List.of(), List.of(), List.of(), Map.of(),
                List.of(), List.of(), Map.of(), null, 0, false);
    }

    private static String uuid() {
        return UUID.randomUUID().toString().substring(0, 8).toUpperCase();
    }
}
