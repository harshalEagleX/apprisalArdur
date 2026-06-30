package com.shal;

import com.shal.common.entity.*;
import com.shal.common.repository.*;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.support.TransactionTemplate;

import java.time.LocalDateTime;
import java.util.List;
import java.util.UUID;
import java.util.stream.Collectors;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Layer 5 — query plan and index regression tests.
 *
 * These tests use PostgreSQL's EXPLAIN ANALYZE to verify that high-traffic
 * queries against the critical tables use index scans rather than sequential
 * scans. A seq scan on a growing table is not wrong — but a seq scan where an
 * index obviously exists is usually a missing or unused index that will degrade
 * under production load.
 *
 * Seeded rows give the planner real data so it selects the optimal plan.
 * A table with zero rows often gets a Seq Scan even with an index because the
 * planner knows the whole table fits in one page anyway.
 *
 * Critical indexes verified:
 *   idx_qc_result_batchfile  — qc_result(batch_file_id)
 *   idx_batch_file_batch     — batch_file(batch_id)
 *   idx_batch_file_status    — batch_file(status)
 */
@SpringBootTest
class QueryPlanTest {

    @PersistenceContext
    private EntityManager em;

    @Autowired private ClientRepository clientRepository;
    @Autowired private UserRepository userRepository;
    @Autowired private BatchRepository batchRepository;
    @Autowired private BatchFileRepository batchFileRepository;
    @Autowired private QCResultRepository qcResultRepository;
    @Autowired private QCRuleResultRepository qcRuleResultRepository;
    @Autowired private TransactionTemplate tx;

    private String tag;
    private long batchId;
    private long fileId;
    private long qcResultId;

    @BeforeEach
    void seed() {
        tag = "QPT_" + UUID.randomUUID().toString().substring(0, 8).toUpperCase();
        tx.executeWithoutResult(s -> {
            Client c = clientRepository.save(
                    Client.builder().name(tag).code(tag).status("ACTIVE").build());
            User u = userRepository.save(User.builder()
                    .username(tag).password("x").role(Role.ADMIN).fullName(tag).build());
            Batch b = batchRepository.save(Batch.builder()
                    .parentBatchId(tag).client(c).status(BatchStatus.REVIEW_PENDING).createdBy(u).build());
            batchId = b.getId();

            // Seed multiple files so the table has real rows and the planner picks the index
            BatchFile mainFile = null;
            for (int i = 0; i < 5; i++) {
                BatchFile f = batchFileRepository.save(BatchFile.builder()
                        .batch(b).fileType(FileType.APPRAISAL)
                        .filename(tag + "_file_" + i + ".pdf")
                        .storagePath("/test/" + tag + "/" + i + ".pdf")
                        .status(FileStatus.COMPLETED).build());
                if (i == 0) mainFile = f;
            }
            fileId = mainFile.getId();

            // Seed one QCResult for the main file
            QCResult r = QCResult.builder()
                    .batchFile(mainFile).qcDecision(QCDecision.TO_VERIFY).totalRules(3).build();
            r.setProcessedAt(LocalDateTime.now());
            qcResultId = qcResultRepository.save(r).getId();
        });

        // Run ANALYZE so the planner has fresh stats on our seeded rows
        tx.executeWithoutResult(s ->
                em.createNativeQuery("ANALYZE batch_file, qc_result").executeUpdate());
    }

    @AfterEach
    void cleanup() {
        tx.executeWithoutResult(s -> {
            qcRuleResultRepository.findByQcResultId(qcResultId).forEach(qcRuleResultRepository::delete);
            qcResultRepository.findById(qcResultId).ifPresent(qcResultRepository::delete);
            batchFileRepository.findByBatchId(batchId).forEach(batchFileRepository::delete);
            batchRepository.findById(batchId).ifPresent(batchRepository::delete);
            userRepository.findByUsername(tag).ifPresent(userRepository::delete);
            clientRepository.findAll().stream().filter(c -> tag.equals(c.getCode()))
                    .forEach(clientRepository::delete);
        });
    }

    // ── qc_result.batch_file_id index ────────────────────────────────────────

    @Test
    void qcResult_byBatchFileId_usesIndexScan() {
        String plan = tx.execute(s -> explainAnalyze(
                "SELECT * FROM qc_result WHERE batch_file_id = " + fileId));
        assertThat(plan)
                .as("qc_result.batch_file_id must use an index scan, not a sequential scan.\n"
                        + "Plan:\n" + plan)
                .containsIgnoringCase("Index");
    }

    // ── batch_file.batch_id index ─────────────────────────────────────────────

    @Test
    void batchFile_byBatchId_usesIndexScan() {
        String plan = tx.execute(s -> explainAnalyze(
                "SELECT * FROM batch_file WHERE batch_id = " + batchId));
        assertThat(plan)
                .as("batch_file.batch_id must use an index scan, not a sequential scan.\n"
                        + "Plan:\n" + plan)
                .containsIgnoringCase("Index");
    }

    // ── batch_file.status index ───────────────────────────────────────────────

    @Test
    void batchFile_byBatchIdAndStatus_usesIndexScan() {
        String plan = tx.execute(s -> explainAnalyze(
                "SELECT * FROM batch_file WHERE batch_id = " + batchId
                        + " AND status = 'ERROR'"));
        assertThat(plan)
                .as("batch_file(batch_id, status) filter must use an index.\n"
                        + "Plan:\n" + plan)
                .containsIgnoringCase("Index");
    }

    // ── QCResult TO_VERIFY query (reviewer queue critical path) ──────────────

    @Test
    void qcResult_pendingVerification_usesIndexOnDecision() {
        String plan = tx.execute(s -> explainAnalyze(
                "SELECT * FROM qc_result WHERE qc_decision = 'TO_VERIFY' "
                        + "AND final_decision IS NULL AND superseded_at IS NULL"));
        // The reviewer queue hits this query on every page load — it must be index-backed.
        assertThat(plan)
                .as("Pending reviewer queue query must not do a full sequential scan.\n"
                        + "Plan:\n" + plan)
                .containsIgnoringCase("Index");
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    @SuppressWarnings("unchecked")
    private String explainAnalyze(String sql) {
        // Disable seq scan in this session so small-table tests don't fool the planner into
        // ignoring existing indexes — without this PostgreSQL picks Seq Scan for ~39 rows.
        em.createNativeQuery("SET LOCAL enable_seqscan = off").executeUpdate();
        List<Object> rows = em.createNativeQuery("EXPLAIN ANALYZE " + sql).getResultList();
        return rows.stream().map(Object::toString).collect(Collectors.joining("\n"));
    }
}
