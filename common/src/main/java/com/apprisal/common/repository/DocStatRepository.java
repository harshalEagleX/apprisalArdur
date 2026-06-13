package com.apprisal.common.repository;

import com.apprisal.common.entity.DocStat;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.Optional;

@Repository
public interface DocStatRepository extends JpaRepository<DocStat, Long> {

    Optional<DocStat> findByQcResultId(Long qcResultId);

    /**
     * Searchable, paginated list for the admin docStats view. A blank search
     * returns everything (most recent first); otherwise it matches the appraisal
     * filename or client name case-insensitively, and an exact batch id.
     */
    @Query("""
        SELECT d FROM DocStat d
        WHERE (:q IS NULL OR :q = ''
               OR LOWER(d.filename) LIKE LOWER(CONCAT('%', :q, '%'))
               OR LOWER(d.clientName) LIKE LOWER(CONCAT('%', :q, '%'))
               OR CAST(d.batchId AS string) = :q)
          AND (:batchId IS NULL OR d.batchId = :batchId)
        """)
    Page<DocStat> search(@Param("q") String q,
                         @Param("batchId") Long batchId,
                         Pageable pageable);

    /** Per-batch rollup rows: count + summed/avg timings, grouped by batch. */
    @Query("""
        SELECT d.batchId, MAX(d.clientName), COUNT(d),
               SUM(d.totalMs), SUM(d.ruleEngineMs), AVG(d.totalMs), MAX(d.createdAt)
        FROM DocStat d
        WHERE d.batchId IS NOT NULL
        GROUP BY d.batchId
        ORDER BY MAX(d.createdAt) DESC
        """)
    java.util.List<Object[]> batchRollup(Pageable pageable);

    void deleteByBatchId(Long batchId);
}
