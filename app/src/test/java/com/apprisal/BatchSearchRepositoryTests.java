package com.apprisal;

import com.apprisal.common.entity.BatchStatus;
import com.apprisal.common.repository.BatchRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.domain.PageRequest;

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
}
