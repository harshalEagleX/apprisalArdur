package com.apprisal.common.repository;

import com.apprisal.common.entity.QCDecision;
import com.apprisal.common.entity.QCResult;
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.jpa.repository.QueryHints;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.time.LocalDateTime;
import jakarta.persistence.QueryHint;

import java.util.List;
import java.util.Optional;

/**
 * Repository for QCResult entities.
 */
@Repository
public interface QCResultRepository extends JpaRepository<QCResult, Long> {

    /**
     * Find the active (non-superseded) QC result for a batch file.
     *
     * After rerun support was added, multiple QCResults can exist per BatchFile
     * (historical results keep supersededAt set). This method always returns the
     * ONE currently-active result. Use findAllByBatchFileIdOrderByProcessedAtDesc
     * when you need the full version history.
     */
    @Query("""
        SELECT qr FROM QCResult qr
        WHERE qr.batchFile.id = :batchFileId
          AND qr.supersededAt IS NULL
        """)
    Optional<QCResult> findByBatchFileId(@Param("batchFileId") Long batchFileId);

    /**
     * Acquire an exclusive row-level lock on a QCResult before mutating its
     * review-session state. Use this instead of {@link #findById} whenever the
     * caller is about to grant or check a review lock, to prevent two concurrent
     * requests from both passing the "no active lock" check (TOCTOU race).
     *
     * Must be called inside a @Transactional method — the lock is released when
     * the surrounding transaction commits or rolls back.
     */
    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @QueryHints({ @QueryHint(name = "jakarta.persistence.lock.timeout", value = "5000") })
    @Query("SELECT qr FROM QCResult qr WHERE qr.id = :qcResultId")
    Optional<QCResult> findByIdForUpdate(@Param("qcResultId") Long qcResultId);

    @Query("""
        SELECT qr FROM QCResult qr
        JOIN FETCH qr.batchFile bf
        JOIN FETCH bf.batch b
        LEFT JOIN FETCH b.assignedReviewer
        WHERE qr.id = :qcResultId
        """)
    Optional<QCResult> findWithBatchFileAndBatchById(@Param("qcResultId") Long qcResultId);

    /**
     * Find all QC results for a batch.
     */
    @Query("SELECT qr FROM QCResult qr WHERE qr.batchFile.batch.id = :batchId")
    List<QCResult> findByBatchId(@Param("batchId") Long batchId);

    @Query("SELECT COUNT(qr) FROM QCResult qr WHERE qr.batchFile.batch.id = :batchId")
    long countByBatchId(@Param("batchId") Long batchId);

    @Modifying(clearAutomatically = true, flushAutomatically = true)
    @Query("DELETE FROM QCResult qr WHERE qr.batchFile.batch.id = :batchId")
    int deleteByBatchId(@Param("batchId") Long batchId);

    /**
     * Find all QC results with a specific decision type.
     */
    List<QCResult> findByQcDecision(QCDecision qcDecision);
    long countByQcDecision(QCDecision qcDecision);

    /**
     * Count results with a given decision within a window, excluding superseded
     * reruns — for analytics so a rerun does not double-count the old + new result
     * and the breakdown reflects the selected period, not all time.
     */
    @Query("""
        SELECT COUNT(qr) FROM QCResult qr
        WHERE qr.qcDecision = :decision
          AND qr.supersededAt IS NULL
          AND qr.processedAt >= :from
        """)
    long countActiveByQcDecisionSince(@Param("decision") QCDecision decision,
                                      @Param("from") LocalDateTime from);

    /**
     * Paginated pending queue — ADMIN view (all clients).
     *
     * AUTO_FAIL batches are routed to reviewer sign-off, so the queue is not
     * limited to TO_VERIFY only. Count query avoids the JOIN FETCH so Spring
     * Data can compute the total correctly.
     */
    @Query(value = """
        SELECT DISTINCT qr FROM QCResult qr
        JOIN FETCH qr.batchFile bf
        JOIN FETCH bf.batch b
        LEFT JOIN FETCH b.assignedReviewer
        WHERE qr.qcDecision <> 'AUTO_PASS'
          AND qr.finalDecision IS NULL
          AND qr.supersededAt IS NULL
        ORDER BY qr.failedCount DESC, qr.verifyCount DESC, qr.updatedAt ASC
        """,
        countQuery = """
        SELECT COUNT(DISTINCT qr) FROM QCResult qr
        WHERE qr.qcDecision <> 'AUTO_PASS'
          AND qr.finalDecision IS NULL
          AND qr.supersededAt IS NULL
        """)
    org.springframework.data.domain.Page<QCResult> findPendingVerificationPaged(
            org.springframework.data.domain.Pageable pageable);

    /**
     * Paginated pending queue — REVIEWER view (only their assigned batches).
     */
    @Query(value = """
        SELECT DISTINCT qr FROM QCResult qr
        JOIN FETCH qr.batchFile bf
        JOIN FETCH bf.batch b
        JOIN FETCH b.assignedReviewer reviewer
        WHERE qr.qcDecision <> 'AUTO_PASS'
          AND qr.finalDecision IS NULL
          AND qr.supersededAt IS NULL
          AND reviewer.id = :reviewerId
        ORDER BY qr.failedCount DESC, qr.verifyCount DESC, qr.updatedAt ASC
        """,
        countQuery = """
        SELECT COUNT(DISTINCT qr) FROM QCResult qr
        WHERE qr.qcDecision <> 'AUTO_PASS'
          AND qr.finalDecision IS NULL
          AND qr.supersededAt IS NULL
          AND qr.batchFile.batch.assignedReviewer.id = :reviewerId
        """)
    org.springframework.data.domain.Page<QCResult> findPendingVerificationForReviewerPaged(
            @Param("reviewerId") Long reviewerId,
            org.springframework.data.domain.Pageable pageable);

    /**
     * Non-paginated variants retained for internal callers that need the full list
     * (e.g., the stuck-batch reconciler). Prefer the paged variants in API handlers.
     */
    @Query("""
        SELECT DISTINCT qr FROM QCResult qr
        JOIN FETCH qr.batchFile bf
        JOIN FETCH bf.batch b
        LEFT JOIN FETCH b.assignedReviewer
        WHERE qr.qcDecision <> 'AUTO_PASS'
          AND qr.finalDecision IS NULL
          AND qr.supersededAt IS NULL
        ORDER BY qr.failedCount DESC, qr.verifyCount DESC, qr.updatedAt ASC
        """)
    List<QCResult> findPendingVerification();

    /**
     * Find reviewer-routed results assigned to a specific reviewer.
     */
    @Query("""
        SELECT DISTINCT qr FROM QCResult qr
        JOIN FETCH qr.batchFile bf
        JOIN FETCH bf.batch b
        JOIN FETCH b.assignedReviewer reviewer
        WHERE qr.qcDecision <> 'AUTO_PASS'
          AND qr.finalDecision IS NULL
          AND qr.supersededAt IS NULL
          AND reviewer.id = :reviewerId
        ORDER BY qr.failedCount DESC, qr.verifyCount DESC, qr.updatedAt ASC
        """)
    List<QCResult> findPendingVerificationForReviewer(@Param("reviewerId") Long reviewerId);

    @Query("""
        SELECT COUNT(qr) FROM QCResult qr
        WHERE qr.qcDecision <> 'AUTO_PASS'
          AND qr.finalDecision IS NULL
          AND qr.supersededAt IS NULL
        """)
    long countPendingReviewerWork();

    @Query("""
        SELECT COUNT(qr) FROM QCResult qr
        WHERE qr.qcDecision <> 'AUTO_PASS'
          AND qr.finalDecision IS NULL
          AND qr.supersededAt IS NULL
          AND qr.batchFile.batch.assignedReviewer.id = :reviewerId
        """)
    long countPendingReviewerWorkForReviewer(@Param("reviewerId") Long reviewerId);

    /**
     * 30 most-recently-submitted results across all reviewers.
     */
    @Query("""
        SELECT qr FROM QCResult qr
        JOIN FETCH qr.batchFile
        WHERE qr.finalDecision IS NOT NULL
        ORDER BY qr.reviewedAt DESC
        LIMIT 30
        """)
    List<QCResult> findRecentlyReviewed();

    /**
     * 30 most-recently-submitted results for a specific reviewer.
     */
    @Query("""
        SELECT qr FROM QCResult qr
        JOIN FETCH qr.batchFile
        WHERE qr.finalDecision IS NOT NULL
          AND qr.reviewedBy.id = :reviewerId
        ORDER BY qr.reviewedAt DESC
        LIMIT 30
        """)
    List<QCResult> findRecentlyReviewedForReviewer(@Param("reviewerId") Long reviewerId);

    /**
     * Check if a reviewer is assigned to the batch containing this QC result.
     */
    @Query("""
        SELECT CASE WHEN COUNT(qr) > 0 THEN TRUE ELSE FALSE END
        FROM QCResult qr
        WHERE qr.id = :qcResultId
          AND qr.batchFile.batch.assignedReviewer.id = :reviewerId
        """)
    boolean isReviewerAssigned(@Param("qcResultId") Long qcResultId, @Param("reviewerId") Long reviewerId);

    /**
     * Count QC results by decision type for a batch.
     */
    @Query("SELECT qr.qcDecision, COUNT(qr) FROM QCResult qr WHERE qr.batchFile.batch.id = :batchId GROUP BY qr.qcDecision")
    List<Object[]> countByDecisionForBatch(@Param("batchId") Long batchId);

    /**
     * Check if a batch file has an active (non-superseded) QC result.
     * Returns false for files whose only QCResult has been superseded by a rerun.
     */
    @Query("""
        SELECT CASE WHEN COUNT(qr) > 0 THEN TRUE ELSE FALSE END
        FROM QCResult qr
        WHERE qr.batchFile.id = :batchFileId
          AND qr.supersededAt IS NULL
        """)
    boolean existsByBatchFileId(@Param("batchFileId") Long batchFileId);

    /**
     * Find the active (non-superseded) QC result for a batch file.
     * There is at most one active result per file at any time.
     */
    @Query("""
        SELECT qr FROM QCResult qr
        WHERE qr.batchFile.id = :batchFileId
          AND qr.supersededAt IS NULL
        """)
    Optional<QCResult> findActiveByBatchFileId(@Param("batchFileId") Long batchFileId);

    /**
     * All QC results for a batch file — active + all historical reruns —
     * ordered newest first. Used for the QC history panel.
     */
    @Query("""
        SELECT qr FROM QCResult qr
        WHERE qr.batchFile.id = :batchFileId
        ORDER BY qr.processedAt DESC
        """)
    List<QCResult> findAllByBatchFileIdOrderByProcessedAtDesc(@Param("batchFileId") Long batchFileId);

    /**
     * Full rerun chain for a given QCResult — walks the rerunOf linked list.
     * Includes the provided result ID and all its ancestors, newest first.
     */
    @Query("""
        SELECT qr FROM QCResult qr
        WHERE qr.batchFile.id = (
            SELECT r.batchFile.id FROM QCResult r WHERE r.id = :qcResultId
        )
        ORDER BY qr.processedAt DESC
        """)
    List<QCResult> findVersionHistoryByQcResultId(@Param("qcResultId") Long qcResultId);

    /**
     * Single-statement counter refresh used after every reviewer decision.
     *
     * Replaces a load-mutate-save cycle that was forcing dirty-checks on the
     * entity's 138-item @OneToMany rule list and producing an Envers audit row
     * per save, costing ~1-2s per call. JPQL UPDATE bypasses both.
     */
    @Modifying
    @Query("""
        UPDATE QCResult qr
           SET qr.passedCount = :passedCount,
               qr.failedCount = :failedCount,
               qr.verifyCount = :verifyCount,
               qr.manualPassCount = :manualPassCount,
               qr.updatedAt = CURRENT_TIMESTAMP
         WHERE qr.id = :qcResultId
        """)
    int updateCounters(@Param("qcResultId") Long qcResultId,
                       @Param("passedCount") int passedCount,
                       @Param("failedCount") int failedCount,
                       @Param("verifyCount") int verifyCount,
                       @Param("manualPassCount") int manualPassCount);
}
