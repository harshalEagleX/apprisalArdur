package com.shal.qc.service;

import com.shal.common.dto.python.PythonQCResponse;
import com.shal.common.dto.python.PythonRuleResult;
import com.shal.common.entity.*;
import com.shal.common.repository.*;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.support.TransactionTemplate;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Regression coverage for batch-status computation and the scope field round-trip.
 *
 * (1) recomputeBatchStatusFromActiveResults — all results finalised → COMPLETED
 * (2) errored file (no QCResult) blocks completion → REVIEW_PENDING
 * (3) DISMISSED file does NOT block completion → COMPLETED  [Fix 1 follow-up]
 * (4) scope column persists correctly from syntheticResponse  [Fix 6]
 * (5) PythonRuleResult.needsVerification() contract for all recognized statuses
 *
 * Uses the real Postgres DB (same as RerunGuardIntegrationTests).
 * recomputeBatchStatusFromActiveResults is package-private — test lives in same package.
 */
@SpringBootTest
class BatchStatusDeterminationTest {

    @Autowired private QCProcessingService qcProcessingService;
    @Autowired private ClientRepository clientRepository;
    @Autowired private UserRepository userRepository;
    @Autowired private BatchRepository batchRepository;
    @Autowired private BatchFileRepository batchFileRepository;
    @Autowired private QCResultRepository qcResultRepository;
    @Autowired private QCRuleResultRepository qcRuleResultRepository;
    @Autowired private ProcessingMetricsRepository processingMetricsRepository;
    @Autowired private JdbcTemplate jdbc;
    @Autowired private TransactionTemplate tx;

    @BeforeEach
    void dropStaleStatusCheckConstraints() {
        // ddl-auto=update created these constraints before DISMISSED was added to FileStatus
        jdbc.execute("ALTER TABLE batch_file DROP CONSTRAINT IF EXISTS batch_file_status_check");
        jdbc.execute("ALTER TABLE batch_file_aud DROP CONSTRAINT IF EXISTS batch_file_aud_status_check");
    }

    // ── (1) All finalised → COMPLETED ────────────────────────────────────────

    @Test
    void recompute_allResultsFinalised_returnsCompleted() {
        String tag = "STA_ALL_" + uuid();
        long[] ids = new long[3];
        seed(tag, ids, QCDecision.TO_VERIFY, FinalDecision.PASS, FileStatus.COMPLETED);
        try {
            BatchStatus status = tx.execute(s -> qcProcessingService.recomputeBatchStatusFromActiveResults(ids[0]));
            assertThat(status).isEqualTo(BatchStatus.COMPLETED);
        } finally {
            cleanup(tag, ids);
        }
    }

    // ── (2) Errored file blocks completion ───────────────────────────────────

    @Test
    void recompute_erroredFilePresent_blocksCompletion() {
        String tag = "STA_ERR_" + uuid();
        long[] ids = new long[3];
        seed(tag, ids, QCDecision.TO_VERIFY, FinalDecision.PASS, FileStatus.COMPLETED);

        long[] errId = new long[1];
        tx.executeWithoutResult(s -> {
            Batch batch = batchRepository.findById(ids[0]).orElseThrow();
            errId[0] = batchFileRepository.save(BatchFile.builder()
                    .batch(batch).fileType(FileType.APPRAISAL)
                    .filename(tag + "_err.pdf").status(FileStatus.ERROR).build()).getId();
        });
        try {
            BatchStatus status = tx.execute(s -> qcProcessingService.recomputeBatchStatusFromActiveResults(ids[0]));
            assertThat(status)
                    .as("errored appraisal file with no QCResult must prevent silent completion")
                    .isEqualTo(BatchStatus.REVIEW_PENDING);
        } finally {
            tx.executeWithoutResult(s -> batchFileRepository.findById(errId[0]).ifPresent(batchFileRepository::delete));
            cleanup(tag, ids);
        }
    }

    // ── (3) DISMISSED file does NOT block completion ──────────────────────────

    @Test
    void recompute_dismissedFilePresent_doesNotBlockCompletion() {
        String tag = "STA_DISM_" + uuid();
        long[] ids = new long[3];
        seed(tag, ids, QCDecision.TO_VERIFY, FinalDecision.PASS, FileStatus.COMPLETED);

        long[] dismId = new long[1];
        tx.executeWithoutResult(s -> {
            Batch batch = batchRepository.findById(ids[0]).orElseThrow();
            dismId[0] = batchFileRepository.save(BatchFile.builder()
                    .batch(batch).fileType(FileType.APPRAISAL)
                    .filename(tag + "_dismissed.pdf").status(FileStatus.DISMISSED).build()).getId();
        });
        try {
            BatchStatus status = tx.execute(s -> qcProcessingService.recomputeBatchStatusFromActiveResults(ids[0]));
            assertThat(status)
                    .as("DISMISSED is the terminal accept-failure state — must not block batch completion")
                    .isEqualTo(BatchStatus.COMPLETED);
        } finally {
            tx.executeWithoutResult(s -> batchFileRepository.findById(dismId[0]).ifPresent(batchFileRepository::delete));
            cleanup(tag, ids);
        }
    }

    // ── (4) scope column persists from PythonQCResponse ──────────────────────

    @Test
    void scopeField_persistsCorrectly_throughPersistPythonResult() {
        String tag = "STA_SCOPE_" + uuid();
        long[] ids = new long[3];
        seed(tag, ids, QCDecision.TO_VERIFY, null, FileStatus.COMPLETED);
        try {
            qcProcessingService.persistPythonResult(ids[1], syntheticResponseWithScope(),
                    QCModelConfig.defaults(), 0L, 0);

            QCResult active = tx.execute(s -> qcResultRepository.findByBatchFileId(ids[1]).orElseThrow());
            List<QCRuleResult> rules = tx.execute(s -> qcRuleResultRepository.findByQcResultId(active.getId()));

            assertThat(rules).isNotEmpty();
            assertThat(rules.stream().map(QCRuleResult::getScope).toList())
                    .containsExactlyInAnyOrder("per_document", "cross_document", "semantic");
        } finally {
            cleanup(tag, ids);
        }
    }

    // ── (5) PythonRuleResult.needsVerification() — pure record method ─────────

    @Test
    void needsVerification_trueForAllReviewStatuses() {
        for (String s : List.of("fail", "verify", "review", "extraction_failed",
                "ocr_low_confidence", "system_error", "source_missing", "cross_doc_mismatch")) {
            assertThat(rule(s, false).needsVerification())
                    .as("status '%s' must require verification", s).isTrue();
        }
    }

    @Test
    void needsVerification_falseForNonActionableStatuses() {
        for (String s : List.of("pass", "not_applicable", "skipped")) {
            assertThat(rule(s, false).needsVerification())
                    .as("status '%s' without reviewRequired=true must NOT require verification", s).isFalse();
        }
    }

    @Test
    void needsVerification_reviewRequiredFlagOverridesStatus() {
        assertThat(rule("pass", true).needsVerification())
                .as("reviewRequired=true overrides a pass status").isTrue();
        assertThat(rule("not_applicable", true).needsVerification())
                .as("reviewRequired=true overrides not_applicable").isTrue();
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    /** Seed one batch+file+result. ids = [batchId, fileId, qcResultId] */
    private void seed(String tag, long[] ids, QCDecision decision,
                      FinalDecision finalDecision, FileStatus fileStatus) {
        tx.executeWithoutResult(s -> {
            Client c = clientRepository.save(
                    Client.builder().name(tag).code(tag).status("ACTIVE").build());
            User u = userRepository.save(User.builder()
                    .username(tag).password("x").role(Role.ADMIN).fullName(tag).build());
            Batch b = batchRepository.save(Batch.builder()
                    .parentBatchId(tag).client(c).status(BatchStatus.REVIEW_PENDING).createdBy(u).build());
            BatchFile f = batchFileRepository.save(BatchFile.builder()
                    .batch(b).fileType(FileType.APPRAISAL).filename(tag + ".pdf").status(fileStatus).build());
            QCResult r = QCResult.builder().batchFile(f).qcDecision(decision).totalRules(2).build();
            r.setProcessedAt(LocalDateTime.now());
            if (finalDecision != null) {
                r.setFinalDecision(finalDecision);
                r.setReviewedAt(LocalDateTime.now());
                r.setReviewedBy(u);
            }
            r = qcResultRepository.save(r);
            ids[0] = b.getId(); ids[1] = f.getId(); ids[2] = r.getId();
        });
    }

    private void cleanup(String tag, long[] ids) {
        tx.executeWithoutResult(s -> {
            // processing_metrics has FK → qc_result; delete metrics FIRST
            if (ids[0] != 0) processingMetricsRepository.deleteByBatchId(ids[0]);
            if (ids[2] != 0) qcRuleResultRepository.findByQcResultId(ids[2]).forEach(qcRuleResultRepository::delete);
            if (ids[1] != 0) {
                qcResultRepository.findAllByBatchFileIdOrderByProcessedAtDesc(ids[1])
                        .forEach(r -> { qcRuleResultRepository.findByQcResultId(r.getId()).forEach(qcRuleResultRepository::delete); qcResultRepository.delete(r); });
            }
            if (ids[0] != 0) {
                batchFileRepository.findByBatchId(ids[0]).forEach(batchFileRepository::delete);
                batchRepository.findById(ids[0]).ifPresent(batchRepository::delete);
            }
            userRepository.findByUsername(tag).ifPresent(userRepository::delete);
            clientRepository.findAll().stream().filter(c -> tag.equals(c.getCode()))
                    .forEach(clientRepository::delete);
        });
    }

    /** Minimal PythonRuleResult — 24 fields in record declaration order */
    private static PythonRuleResult rule(String status, boolean reviewRequired) {
        return new PythonRuleResult(
                "R-1", "Test rule", "SUBJECT", status, "msg",
                "STANDARD", null, null,        // actionItem, details
                null, null,                    // appraisalValue, engagementValue
                0.9, null, null,               // confidence, extractedValue, expectedValue
                null, null, null,              // verifyQuestion, rejectionText, evidence
                reviewRequired, null,          // reviewRequired, targetField
                null, null, null, null, null,  // sourcePage, bboxX, bboxY, bboxW, bboxH
                null                           // scope
        );
    }

    /** Response with one rule of each scope value */
    private static PythonQCResponse syntheticResponseWithScope() {
        return new PythonQCResponse(
                "1.0", true, 5, 1, "test",
                Map.of(), Map.of(),
                3, "qc-test", 3, 0, 0,
                "doc", "job", false, null,
                "groq", "gpt-oss-120b", null,
                false, List.of(),
                false, List.of(),
                List.of(
                    scopedRule("S-1",   "pass", "per_document"),
                    scopedRule("G-1",   "pass", "cross_document"),
                    scopedRule("SEM-1", "pass", "semantic")
                ),
                List.of(), List.of(), List.of(), null);
    }

    private static PythonRuleResult scopedRule(String ruleId, String status, String scope) {
        return new PythonRuleResult(
                ruleId, "Test rule", "SUBJECT", status, "msg",
                "STANDARD", null, null,
                null, null,
                0.9, null, null,
                null, null, null,
                false, null,
                null, null, null, null, null,
                scope
        );
    }

    private static String uuid() {
        return UUID.randomUUID().toString().substring(0, 8).toUpperCase();
    }
}
