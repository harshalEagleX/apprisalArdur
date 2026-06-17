package com.apprisal;

import com.apprisal.common.dto.python.PythonQCResponse;
import com.apprisal.common.entity.*;
import com.apprisal.common.repository.*;
import com.apprisal.qc.service.QCModelConfig;
import com.apprisal.qc.service.QCProcessingService;
import com.apprisal.qc.service.VerificationService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.support.TransactionTemplate;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * Live integration coverage for the re-run data-integrity guards against the
 * real Postgres the app uses. This closes the exact production race the user
 * flagged: a reviewer has a report open while an admin re-runs QC (full batch
 * or a single file). The re-run stamps {@code supersededAt} on the prior
 * QCResult and creates a new active one; any reviewer write to the superseded
 * result would be silently lost.
 *
 * It proves:
 *  (1) acceptAll on a superseded result is rejected with a clear "reload" signal
 *      (VerificationService.assertDocumentCurrent — the D2/D3 guard),
 *  (2) rejectAll on a superseded result is likewise rejected,
 *  (3) the active-result query excludes the superseded row and returns ONLY the
 *      current result (what every reviewer queue relies on), while the full
 *      history query still returns both rows,
 *  (4) R2: a re-run of a result a reviewer actively holds carries that lock onto
 *      the new result — the holder reloads cleanly while a different reviewer is
 *      blocked, closing the window where the file could be grabbed.
 * The seeded graph is cleaned up afterward.
 */
@SpringBootTest
class RerunGuardIntegrationTests {

    private final VerificationService verificationService;
    private final QCProcessingService qcProcessingService;
    private final ClientRepository clientRepository;
    private final UserRepository userRepository;
    private final BatchRepository batchRepository;
    private final BatchFileRepository batchFileRepository;
    private final QCResultRepository qcResultRepository;
    private final ProcessingMetricsRepository processingMetricsRepository;
    private final AuditLogRepository auditLogRepository;
    private final TransactionTemplate tx;

    @Autowired
    RerunGuardIntegrationTests(VerificationService verificationService,
                               QCProcessingService qcProcessingService,
                               ClientRepository clientRepository,
                               UserRepository userRepository,
                               BatchRepository batchRepository,
                               BatchFileRepository batchFileRepository,
                               QCResultRepository qcResultRepository,
                               ProcessingMetricsRepository processingMetricsRepository,
                               AuditLogRepository auditLogRepository,
                               TransactionTemplate tx) {
        this.verificationService = verificationService;
        this.qcProcessingService = qcProcessingService;
        this.clientRepository = clientRepository;
        this.userRepository = userRepository;
        this.batchRepository = batchRepository;
        this.batchFileRepository = batchFileRepository;
        this.qcResultRepository = qcResultRepository;
        this.processingMetricsRepository = processingMetricsRepository;
        this.auditLogRepository = auditLogRepository;
        this.tx = tx;
    }

    @Test
    void supersededResult_rejectsReviewerWrites_andIsExcludedFromActiveQuery() {
        String tag = "RERUN_IT_" + UUID.randomUUID().toString().substring(0, 8);
        long[] ids = new long[4]; // batchId, fileId, supersededQcId, activeQcId
        User[] reviewerHolder = new User[1];

        try {
            tx.executeWithoutResult(s -> {
                Client client = clientRepository.save(Client.builder()
                        .name("Rerun IT").code(tag).status("ACTIVE").build());
                User reviewer = userRepository.save(User.builder()
                        .username(tag).password("x").role(Role.REVIEWER).fullName("IT Reviewer").build());
                Batch batch = batchRepository.save(Batch.builder()
                        .parentBatchId(tag).client(client).status(BatchStatus.REVIEW_PENDING)
                        .createdBy(reviewer).build());
                BatchFile file = batchFileRepository.save(BatchFile.builder()
                        .batch(batch).fileType(FileType.APPRAISAL).filename(tag + ".pdf")
                        .status(FileStatus.COMPLETED).build());

                // Prior run, now superseded by a re-run (the reviewer's stale handle).
                QCResult superseded = QCResult.builder()
                        .batchFile(file).qcDecision(QCDecision.TO_VERIFY).totalRules(3)
                        .build();
                superseded.setProcessedAt(LocalDateTime.now().minusMinutes(10));
                superseded.setSupersededAt(LocalDateTime.now().minusMinutes(1));
                superseded = qcResultRepository.save(superseded);

                // Current active run from the re-run (supersededAt IS NULL).
                QCResult active = QCResult.builder()
                        .batchFile(file).qcDecision(QCDecision.TO_VERIFY).totalRules(3)
                        .build();
                active.setProcessedAt(LocalDateTime.now());
                active = qcResultRepository.save(active);

                ids[0] = batch.getId();
                ids[1] = file.getId();
                ids[2] = superseded.getId();
                ids[3] = active.getId();
                reviewerHolder[0] = reviewer;
            });

            User reviewer = reviewerHolder[0];

            // (1) Bulk-pass on the superseded result is blocked with a reload signal.
            assertThatThrownBy(() -> verificationService.acceptAll(ids[2], reviewer, "looks fine"))
                    .isInstanceOf(IllegalStateException.class)
                    .hasMessageContaining("no longer the current");

            // (2) Bulk-fail on the superseded result is blocked the same way.
            assertThatThrownBy(() -> verificationService.rejectAll(ids[2], reviewer, "rejecting the stale copy"))
                    .isInstanceOf(IllegalStateException.class)
                    .hasMessageContaining("no longer the current");

            // (3) The active-result query returns ONLY the current row (reviewer queues
            //     rely on this exclusion); the history query returns both versions.
            assertThat(qcResultRepository.findByBatchFileId(ids[1]))
                    .as("active query must skip the superseded row")
                    .isPresent()
                    .get()
                    .extracting(QCResult::getId)
                    .isEqualTo(ids[3]);

            List<QCResult> history = qcResultRepository.findAllByBatchFileIdOrderByProcessedAtDesc(ids[1]);
            assertThat(history).as("full history keeps both runs").hasSize(2);
            assertThat(history.get(0).getId()).as("newest first").isEqualTo(ids[3]);
        } finally {
            tx.executeWithoutResult(s -> {
                qcResultRepository.findAllByBatchFileIdOrderByProcessedAtDesc(ids[1])
                        .forEach(qcResultRepository::delete);
                batchFileRepository.findById(ids[1]).ifPresent(batchFileRepository::delete);
                batchRepository.findById(ids[0]).ifPresent(batchRepository::delete);
                userRepository.findByUsername(tag).ifPresent(userRepository::delete);
                clientRepository.findAll().stream().filter(c -> tag.equals(c.getCode()))
                        .forEach(clientRepository::delete);
            });
        }
    }

    /**
     * R2: a re-run of a file whose result is actively held by a reviewer must carry that lock onto
     * the new result, so a *different* reviewer cannot grab it in the window before the original
     * reviewer reloads. Drives the real {@link QCProcessingService#persistPythonResult} re-run path
     * (which supersedes the prior result and creates the new one) and asserts the lock moved, then
     * proves the carried lock still blocks reviewer B while letting reviewer A back in.
     */
    @Test
    void rerun_carriesActiveReviewLockToNewResult_blockingOtherReviewers() {
        String tag = "RERUN_LOCK_IT_" + UUID.randomUUID().toString().substring(0, 8);
        long[] ids = new long[4]; // batchId, fileId, priorQcId, reviewerAId
        User[] reviewers = new User[2]; // A (lock holder), B (other)

        try {
            tx.executeWithoutResult(s -> {
                Client client = clientRepository.save(Client.builder()
                        .name("Rerun Lock IT").code(tag).status("ACTIVE").build());
                User reviewerA = userRepository.save(User.builder()
                        .username(tag + "_A").password("x").role(Role.REVIEWER).fullName("Reviewer A").build());
                User reviewerB = userRepository.save(User.builder()
                        .username(tag + "_B").password("x").role(Role.REVIEWER).fullName("Reviewer B").build());
                Batch batch = batchRepository.save(Batch.builder()
                        .parentBatchId(tag).client(client).status(BatchStatus.IN_REVIEW)
                        .createdBy(reviewerA).build());
                BatchFile file = batchFileRepository.save(BatchFile.builder()
                        .batch(batch).fileType(FileType.APPRAISAL).filename(tag + ".pdf")
                        .status(FileStatus.COMPLETED).build());

                // Prior active result, currently locked by reviewer A (live lock).
                QCResult prior = QCResult.builder()
                        .batchFile(file).qcDecision(QCDecision.TO_VERIFY).totalRules(2)
                        .build();
                prior.setProcessedAt(LocalDateTime.now().minusMinutes(5));
                prior.setReviewLockedBy(reviewerA);
                prior.setReviewSessionToken(UUID.randomUUID().toString());
                prior.setReviewStartedAt(LocalDateTime.now().minusMinutes(3));
                prior.setReviewLastActiveAt(LocalDateTime.now().minusSeconds(20));
                prior.setReviewLockExpiresAt(LocalDateTime.now().plusMinutes(10));
                prior = qcResultRepository.save(prior);

                ids[0] = batch.getId();
                ids[1] = file.getId();
                ids[2] = prior.getId();
                ids[3] = reviewerA.getId();
                reviewers[0] = reviewerA;
                reviewers[1] = reviewerB;
            });

            // Drive the real re-run persist path (supersedes prior, creates the new active result).
            qcProcessingService.persistPythonResult(ids[1], syntheticResponse(), QCModelConfig.defaults(), 0L, 0);

            // Prior result is now superseded.
            QCResult prior = qcResultRepository.findById(ids[2]).orElseThrow();
            assertThat(prior.getSupersededAt()).as("prior result superseded by the re-run").isNotNull();

            // New active result carries reviewer A's lock; the session token is fresh (null).
            QCResult active = qcResultRepository.findByBatchFileId(ids[1]).orElseThrow();
            assertThat(active.getId()).as("new result is not the prior one").isNotEqualTo(ids[2]);
            assertThat(active.getReviewLockedBy()).as("lock holder carried").isNotNull()
                    .extracting(User::getId).isEqualTo(ids[3]);
            assertThat(active.getReviewLockExpiresAt()).as("live lock carried")
                    .isNotNull().isAfter(LocalDateTime.now());
            assertThat(active.getReviewSessionToken()).as("session token NOT carried — fresh on reload").isNull();

            // The carried lock blocks a different reviewer ...
            assertThatThrownBy(() ->
                    verificationService.beginReviewSession(active.getId(), reviewers[1], false, null, null))
                    .isInstanceOf(IllegalStateException.class)
                    .hasMessageContaining("currently being reviewed");

            // ... but the original holder reloads cleanly and gets a fresh session token.
            QCResult reopened = verificationService.beginReviewSession(active.getId(), reviewers[0], false, null, null);
            assertThat(reopened.getReviewSessionToken()).as("holder gets a fresh session").isNotBlank();
            assertThat(reopened.getReviewLockedBy().getId()).isEqualTo(ids[3]);
        } finally {
            tx.executeWithoutResult(s -> {
                // The re-run + beginReviewSession emit business_event rows, which are APPEND-ONLY
                // (audit integrity) and whose actor FK pins the two seeded reviewers. We therefore
                // leave those reviewers in place by design and clean everything else: audit_log
                // (deletable), metrics, results, file, batch, then the client. Each run uses a
                // unique UUID tag, so the residual reviewer rows never collide.
                for (String u : List.of(tag + "_A", tag + "_B")) {
                    userRepository.findByUsername(u).ifPresent(usr ->
                            auditLogRepository.findRecentByUserId(usr.getId()).forEach(auditLogRepository::delete));
                }
                processingMetricsRepository.deleteByBatchId(ids[0]);
                qcResultRepository.findAllByBatchFileIdOrderByProcessedAtDesc(ids[1])
                        .forEach(qcResultRepository::delete);
                batchFileRepository.findById(ids[1]).ifPresent(batchFileRepository::delete);
                batchRepository.findById(ids[0]).ifPresent(batchRepository::delete);
                clientRepository.findAll().stream().filter(c -> tag.equals(c.getCode()))
                        .forEach(clientRepository::delete);
            });
        }
    }

    /** Minimal Python QC response for driving a re-run persist (no timing/docStats block). */
    private static PythonQCResponse syntheticResponse() {
        return new PythonQCResponse(
                true, 10, 1, "test",
                Map.of(), Map.of(),
                0, "qc-test", 0, 0, 0,
                "doc", "job", false, null,
                "groq", "gpt-oss-120b", null,
                false, List.of(),
                List.of(), List.of(), List.of(), List.of(),
                null);
    }
}
