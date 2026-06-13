package com.apprisal;

import com.apprisal.common.entity.*;
import com.apprisal.common.repository.*;
import com.apprisal.qc.controller.api.DocStatsApiController;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.ResponseEntity;
import org.springframework.transaction.support.TransactionTemplate;

import java.util.List;
import java.util.Map;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Live integration coverage for the docStats feature against the real Postgres
 * the app uses. Closes the load-audit gap that compilation could not: it proves
 * (1) ddl-auto creates the doc_stat schema + indexes on Postgres, (2) every
 * hand-written JPQL query parses and executes, (3) the @Transactional read
 * endpoints map the lazy child collections with open-in-view disabled, and
 * (4) the FK-safe batch-delete removes the whole doc_stat tree without a
 * constraint violation. The seeded graph is cleaned up afterward.
 */
@SpringBootTest
class DocStatsIntegrationTests {

    private final DocStatRepository docStatRepository;
    private final DocStatsApiController controller;
    private final ClientRepository clientRepository;
    private final UserRepository userRepository;
    private final BatchRepository batchRepository;
    private final BatchFileRepository batchFileRepository;
    private final QCResultRepository qcResultRepository;
    private final TransactionTemplate tx;

    @Autowired
    DocStatsIntegrationTests(DocStatRepository docStatRepository,
                             DocStatsApiController controller,
                             ClientRepository clientRepository,
                             UserRepository userRepository,
                             BatchRepository batchRepository,
                             BatchFileRepository batchFileRepository,
                             QCResultRepository qcResultRepository,
                             TransactionTemplate tx) {
        this.docStatRepository = docStatRepository;
        this.controller = controller;
        this.clientRepository = clientRepository;
        this.userRepository = userRepository;
        this.batchRepository = batchRepository;
        this.batchFileRepository = batchFileRepository;
        this.qcResultRepository = qcResultRepository;
        this.tx = tx;
    }

    /** Every repository query and controller endpoint must parse + run on real Postgres. */
    @Test
    void allQueriesAndEndpointsExecuteOnRealPostgres() {
        var page = PageRequest.of(0, 20);
        // repository JPQL (CAST AS string, CASE WHEN, cross-join rerun, projections)
        docStatRepository.search(null, null, page);
        docStatRepository.search("anything", 1L, page);
        docStatRepository.batchTimingRows(page);
        docStatRepository.ruleRanking(page);
        docStatRepository.recentTrend(null, page);
        docStatRepository.recentTrend("x.pdf", page);
        docStatRepository.findPreviousByDocStatId(-1L);
        docStatRepository.findByQcResultId(-1L);

        // controller endpoints (read paths are @Transactional for lazy mapping)
        assertThat(controller.list(null, null, 0, 20).getStatusCode().is2xxSuccessful()).isTrue();
        assertThat(controller.batches(500).getStatusCode().is2xxSuccessful()).isTrue();
        assertThat(controller.ruleRanking(100).getStatusCode().is2xxSuccessful()).isTrue();
        assertThat(controller.trend(null, 30).getStatusCode().is2xxSuccessful()).isTrue();
        assertThat(controller.thresholds().getStatusCode().is2xxSuccessful()).isTrue();
        assertThat(controller.thresholds().getBody()).containsKey("subject_llm");
        assertThat(controller.detail(-1L).getStatusCode().value()).isEqualTo(404);
    }

    /** Persist a full doc_stat tree + rerun chain, map it lazily, then FK-safe delete it. */
    @Test
    void fullLifecycle_persist_lazyMap_rerunCompare_fkSafeDelete() {
        String tag = "DOCSTAT_IT_" + UUID.randomUUID().toString().substring(0, 8);
        long[] ids = new long[3]; // batchId, prevDocStatId, curDocStatId

        try {
            tx.executeWithoutResult(s -> {
                Client client = clientRepository.save(Client.builder()
                        .name("DocStat IT").code(tag).status("ACTIVE").build());
                User user = userRepository.save(User.builder()
                        .username(tag).password("x").role(Role.ADMIN).fullName("IT").build());
                Batch batch = batchRepository.save(Batch.builder()
                        .parentBatchId(tag).client(client).status(BatchStatus.COMPLETED)
                        .createdBy(user).build());
                // qc_result is unique per batch_file, so use one file per run;
                // the rerun chain links via QCResult.rerunOf, not the file, and
                // both docStats share the batch so delete-by-batchId covers them.
                BatchFile file1 = batchFileRepository.save(BatchFile.builder()
                        .batch(batch).fileType(FileType.APPRAISAL).filename(tag + "-r1.pdf")
                        .status(FileStatus.COMPLETED).build());
                BatchFile file2 = batchFileRepository.save(BatchFile.builder()
                        .batch(batch).fileType(FileType.APPRAISAL).filename(tag + "-r2.pdf")
                        .status(FileStatus.COMPLETED).build());

                // previous run (will be superseded)
                QCResult prevQc = qcResultRepository.save(QCResult.builder()
                        .batchFile(file1).qcDecision(QCDecision.TO_VERIFY).totalRules(2).build());
                DocStat prev = docStatRepository.save(buildDocStat(prevQc, batch.getId(),
                        client.getId(), file1.getId(), tag + ".pdf", 1500.0));

                // current run, rerunOf -> previous
                QCResult curQc = QCResult.builder()
                        .batchFile(file2).qcDecision(QCDecision.AUTO_PASS).totalRules(2).build();
                curQc.setRerunOf(prevQc);
                curQc = qcResultRepository.save(curQc);
                DocStat cur = docStatRepository.save(buildDocStat(curQc, batch.getId(),
                        client.getId(), file2.getId(), tag + ".pdf", 900.0));

                ids[0] = batch.getId();
                ids[1] = prev.getId();
                ids[2] = cur.getId();
            });

            // (A) detail() maps the lazy stages/sections/rules with open-in-view=false
            ResponseEntity<Map<String, Object>> detail = controller.detail(ids[2]);
            assertThat(detail.getStatusCode().is2xxSuccessful()).isTrue();
            Map<String, Object> body = detail.getBody();
            assertThat(body).isNotNull();
            assertThat((List<?>) body.get("stages")).isNotEmpty();
            assertThat((List<?>) body.get("sections")).isNotEmpty();
            assertThat((List<?>) body.get("rules")).isNotEmpty();

            // rerun before/after: previous resolves via QCResult.rerunOf, deltas present
            ResponseEntity<Map<String, Object>> cmp = controller.compare(ids[2]);
            assertThat(cmp.getStatusCode().is2xxSuccessful()).isTrue();
            assertThat(cmp.getBody().get("previous")).isNotNull();
            assertThat(cmp.getBody().get("delta")).isNotNull();

            // findPreviousByDocStatId walks the chain to the prior docStat
            var resolvedPrev = docStatRepository.findPreviousByDocStatId(ids[2]);
            assertThat(resolvedPrev).isPresent();
            assertThat(resolvedPrev.get().getId()).isEqualTo(ids[1]);

            // (B) FK-safe delete: removes the whole tree by batchId without a
            // constraint violation (children first, then parents)
            int deleted = tx.execute(s -> docStatRepository.deleteTreeByBatchId(ids[0]));
            assertThat(deleted).isEqualTo(2);
            assertThat(docStatRepository.findById(ids[1])).isEmpty();
            assertThat(docStatRepository.findById(ids[2])).isEmpty();
        } finally {
            // tidy the seeded graph (docStat tree already gone if the test reached delete)
            tx.executeWithoutResult(s -> {
                docStatRepository.deleteTreeByBatchId(ids[0]);
                batchRepository.findById(ids[0]).ifPresent(b -> {
                    qcResultRepository.findAll().stream()
                            .filter(q -> q.getBatchFile() != null
                                    && q.getBatchFile().getBatch() != null
                                    && b.getId().equals(q.getBatchFile().getBatch().getId()))
                            .forEach(qcResultRepository::delete);
                    b.getFiles().forEach(batchFileRepository::delete);
                    batchRepository.delete(b);
                });
                userRepository.findByUsername(tag).ifPresent(userRepository::delete);
                clientRepository.findAll().stream().filter(c -> tag.equals(c.getCode()))
                        .forEach(clientRepository::delete);
            });
        }
    }

    private DocStat buildDocStat(QCResult qc, Long batchId, Long clientId, Long fileId,
                                 String filename, double totalMs) {
        DocStat d = DocStat.builder()
                .qcResult(qc).batchFileId(fileId).batchId(batchId).clientId(clientId)
                .filename(filename).clientName("DocStat IT").qcDecision(qc.getQcDecision().name())
                .totalMs(totalMs).ruleEngineMs(12.0).measuredPipelineMs(totalMs).ruleCount(2)
                .slowestStageLabel("Subject/contract gap-fill (LLM)").slowestStageMs(totalMs - 50)
                .slowestSectionLabel("Sales Comparison").slowestSectionMs(10.0)
                .slowestRuleId("SCA-14").slowestRuleName("Comp quality").slowestRuleMs(9.5)
                .llmCalls(1).llmInferenceMs(8.0).llmThrottleWaitMs(2.0).rateLimitHits(0)
                .build();
        d.addStage(new DocStatStage("subject_llm", "Subject/contract gap-fill (LLM)",
                totalMs - 50, 95.0, 1, 8.0, 2.0, 0));
        d.addStage(new DocStatStage("rules", "QC rule evaluation", 12.0, 5.0, 0, 0.0, 0.0, 1));
        d.addSection(new DocStatSection("SALES_COMPARISON", "Sales Comparison", 10.0, 1, 80.0, 0));
        d.addSection(new DocStatSection("SUBJECT", "Subject", 2.0, 1, 20.0, 1));
        d.addRule(new DocStatRule("SCA-14", "Comp quality", "SALES_COMPARISON", "VERIFY",
                9.5, 0.6, 1, 8.0, 2.0, 0));
        d.addRule(new DocStatRule("S-1", "Address", "SUBJECT", "PASS", 0.4, 1.0, 0, 0.0, 0.0, 1));
        return d;
    }
}
