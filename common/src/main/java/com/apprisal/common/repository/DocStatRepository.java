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

    /**
     * Raw per-file timing rows for percentile computation, newest first.
     * Columns: batchId, clientName, totalMs, ruleEngineMs, measuredPipelineMs, createdAt.
     * Percentiles are computed in Java (DB-agnostic) over these rows.
     */
    @Query("""
        SELECT d.batchId, d.clientName, d.totalMs, d.ruleEngineMs, d.measuredPipelineMs, d.createdAt
        FROM DocStat d
        WHERE d.batchId IS NOT NULL
        ORDER BY d.createdAt DESC
        """)
    java.util.List<Object[]> batchTimingRows(Pageable pageable);

    /**
     * Cumulative per-rule ranking across the whole corpus:
     * ruleId, ruleName, section, AVG(ms), MAX(ms), SUM(llmCalls), runs, llmRuns.
     * llmRuns = number of runs where this rule made at least one LLM call;
     * the %-LLM is llmRuns/runs, computed by the caller.
     */
    @Query("""
        SELECT r.ruleId, MAX(r.ruleName), MAX(r.section),
               AVG(r.ms), MAX(r.ms), COALESCE(SUM(r.llmCalls), 0), COUNT(r),
               SUM(CASE WHEN r.llmCalls > 0 THEN 1 ELSE 0 END)
        FROM DocStatRule r
        WHERE r.ruleId IS NOT NULL
        GROUP BY r.ruleId
        ORDER BY AVG(r.ms) DESC
        """)
    java.util.List<Object[]> ruleRanking(Pageable pageable);

    void deleteByBatchId(Long batchId);
}
