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
               SUM(CASE WHEN r.llmCalls > 0 THEN 1 ELSE 0 END), AVG(r.confidence)
        FROM DocStatRule r
        WHERE r.ruleId IS NOT NULL
        GROUP BY r.ruleId
        ORDER BY AVG(r.ms) DESC
        """)
    java.util.List<Object[]> ruleRanking(Pageable pageable);

    /**
     * Recent runs for a time-series trend (oldest→newest is reversed in the
     * controller). Optionally scoped to one appraisal filename so you can watch
     * the same file's timing across re-runs after a code change.
     * Columns: id, createdAt, filename, totalMs, ruleEngineMs, llmInferenceMs, llmThrottleWaitMs.
     */
    @Query("""
        SELECT d.id, d.createdAt, d.filename, d.totalMs, d.ruleEngineMs,
               d.llmInferenceMs, d.llmThrottleWaitMs
        FROM DocStat d
        WHERE (:filename IS NULL OR d.filename = :filename)
        ORDER BY d.createdAt DESC
        """)
    java.util.List<Object[]> recentTrend(@Param("filename") String filename, Pageable pageable);

    /**
     * The timing of the run this docStat superseded — its qcResult's rerunOf.
     * Enables a before/after comparison after re-running QC on the same file.
     */
    @Query("""
        SELECT prev FROM DocStat prev, DocStat cur
        WHERE cur.id = :id AND prev.qcResult.id = cur.qcResult.rerunOf.id
        """)
    Optional<DocStat> findPreviousByDocStatId(@Param("id") Long id);

    // ── FK-safe cascade delete for a batch ─────────────────────────────────────
    // Bulk JPQL deletes bypass entity orphanRemoval, so children must be deleted
    // before parents, and doc_stat (which FKs to qc_result) before qc_result.
    @org.springframework.data.jpa.repository.Modifying(clearAutomatically = true, flushAutomatically = true)
    @Query("DELETE FROM DocStatRule r WHERE r.docStat.id IN (SELECT d.id FROM DocStat d WHERE d.batchId = :batchId)")
    int deleteRulesByBatchId(@Param("batchId") Long batchId);

    @org.springframework.data.jpa.repository.Modifying(clearAutomatically = true, flushAutomatically = true)
    @Query("DELETE FROM DocStatSection s WHERE s.docStat.id IN (SELECT d.id FROM DocStat d WHERE d.batchId = :batchId)")
    int deleteSectionsByBatchId(@Param("batchId") Long batchId);

    @org.springframework.data.jpa.repository.Modifying(clearAutomatically = true, flushAutomatically = true)
    @Query("DELETE FROM DocStatStage s WHERE s.docStat.id IN (SELECT d.id FROM DocStat d WHERE d.batchId = :batchId)")
    int deleteStagesByBatchId(@Param("batchId") Long batchId);

    @org.springframework.data.jpa.repository.Modifying(clearAutomatically = true, flushAutomatically = true)
    @Query("DELETE FROM DocStat d WHERE d.batchId = :batchId")
    int deleteByBatchId(@Param("batchId") Long batchId);

    /** Delete a batch's whole docStat tree (children first), FK-safe. */
    default int deleteTreeByBatchId(Long batchId) {
        deleteRulesByBatchId(batchId);
        deleteSectionsByBatchId(batchId);
        deleteStagesByBatchId(batchId);
        return deleteByBatchId(batchId);
    }
}
