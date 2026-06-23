package com.shal;

import com.shal.common.entity.Batch;
import com.shal.common.entity.BatchStatus;
import com.shal.common.entity.Client;
import com.shal.common.entity.Role;
import com.shal.common.entity.User;
import com.shal.common.repository.BatchRepository;
import com.shal.common.repository.ClientRepository;
import com.shal.common.repository.UserRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;

/**
 * Regression for the admin batch-list status filter returning HTTP 500
 * ("ERROR: function lower(bytea) does not exist").
 *
 * When a status filter is applied with no search term, {@code :search} is null.
 * Postgres still resolves {@code LOWER(CONCAT('%', :search, '%'))} at plan time
 * even though {@code :search IS NULL} short-circuits the OR, and an untyped null
 * binds as {@code bytea} -> SQLGrammarException. BatchRepository.searchAdminBatches
 * casts {@code :search} to string to pin the parameter type.
 *
 * The bug threw at query EXECUTION regardless of row count, so these run against
 * the real Postgres with whatever data exists. Surfaced by load-testing
 * /api/admin/batches?status=COMPLETED against 5k synthetic rows.
 */
@SpringBootTest
class BatchSearchRepositoryTests {

    @Autowired
    BatchRepository batchRepository;

    @Autowired
    ClientRepository clientRepository;

    @Autowired
    UserRepository userRepository;

    @Test
    void statusFilterWithNullSearchDoesNotThrow() {
        assertThatCode(() -> batchRepository.searchAdminBatches(
                BatchStatus.COMPLETED, null, PageRequest.of(0, 20)))
                .doesNotThrowAnyException();
    }

    @Test
    void searchTermWithNullStatusDoesNotThrow() {
        assertThatCode(() -> batchRepository.searchAdminBatches(
                null, "anything", PageRequest.of(0, 20)))
                .doesNotThrowAnyException();
    }

    @Test
    void statusAndSearchTogetherDoNotThrow() {
        assertThatCode(() -> batchRepository.searchAdminBatches(
                BatchStatus.COMPLETED, "x", PageRequest.of(0, 20)))
                .doesNotThrowAnyException();
    }

    /**
     * Behavioral correctness (not just "doesn't throw"): the status filter must return
     * ONLY rows of that status. Seeds one COMPLETED + one REVIEW_PENDING batch under a
     * unique tag, then filters by COMPLETED + tag and asserts the result includes the
     * completed batch and excludes the pending one. @Transactional rolls the seed back.
     */
    @Test
    @Transactional
    void statusFilterReturnsOnlyMatchingStatus() {
        String tag = "BSRT-" + UUID.randomUUID().toString().substring(0, 8);
        User creator = userRepository.saveAndFlush(
                User.builder().username(tag).password("x").role(Role.ADMIN).fullName("BatchSearch IT").build());
        Client client = clientRepository.saveAndFlush(
                Client.builder().name("BatchSearch IT").code(tag).status("ACTIVE").build());
        Batch completed = batchRepository.saveAndFlush(
                Batch.builder().parentBatchId(tag + "-C").client(client).createdBy(creator).status(BatchStatus.COMPLETED).build());
        Batch pending = batchRepository.saveAndFlush(
                Batch.builder().parentBatchId(tag + "-P").client(client).createdBy(creator).status(BatchStatus.REVIEW_PENDING).build());

        Page<Batch> page = batchRepository.searchAdminBatches(
                BatchStatus.COMPLETED, tag, PageRequest.of(0, 50));

        List<Long> ids = page.getContent().stream().map(Batch::getId).toList();
        assertThat(ids).contains(completed.getId()).doesNotContain(pending.getId());
    }
}
