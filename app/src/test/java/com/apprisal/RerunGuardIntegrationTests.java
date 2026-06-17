package com.apprisal;

import com.apprisal.common.entity.*;
import com.apprisal.common.repository.*;
import com.apprisal.qc.service.VerificationService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.support.TransactionTemplate;

import java.time.LocalDateTime;
import java.util.List;
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
 *      history query still returns both rows.
 * The seeded graph is cleaned up afterward.
 */
@SpringBootTest
class RerunGuardIntegrationTests {

    private final VerificationService verificationService;
    private final ClientRepository clientRepository;
    private final UserRepository userRepository;
    private final BatchRepository batchRepository;
    private final BatchFileRepository batchFileRepository;
    private final QCResultRepository qcResultRepository;
    private final TransactionTemplate tx;

    @Autowired
    RerunGuardIntegrationTests(VerificationService verificationService,
                               ClientRepository clientRepository,
                               UserRepository userRepository,
                               BatchRepository batchRepository,
                               BatchFileRepository batchFileRepository,
                               QCResultRepository qcResultRepository,
                               TransactionTemplate tx) {
        this.verificationService = verificationService;
        this.clientRepository = clientRepository;
        this.userRepository = userRepository;
        this.batchRepository = batchRepository;
        this.batchFileRepository = batchFileRepository;
        this.qcResultRepository = qcResultRepository;
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
}
