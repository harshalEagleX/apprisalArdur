package com.apprisal.common.repository;

import com.apprisal.common.entity.QCDecision;
import com.apprisal.common.entity.QCResult;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

/**
 * Repository for QCResult entities.
 */
@Repository
public interface QCResultRepository extends JpaRepository<QCResult, Long> {

    /**
     * Find QC result for a specific batch file.
     */
    Optional<QCResult> findByBatchFileId(Long batchFileId);

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

    /**
     * Find all QC results with a specific decision type.
     */
    List<QCResult> findByQcDecision(QCDecision qcDecision);
    long countByQcDecision(QCDecision qcDecision);

    /**
     * Find all TO_VERIFY results that haven't been reviewed (ADMIN: all).
     */
    @Query("""
        SELECT DISTINCT qr FROM QCResult qr
        JOIN FETCH qr.batchFile bf
        JOIN FETCH bf.batch b
        LEFT JOIN FETCH b.assignedReviewer
        WHERE qr.qcDecision = 'TO_VERIFY'
          AND qr.finalDecision IS NULL
        ORDER BY qr.failedCount DESC, qr.verifyCount DESC, qr.updatedAt ASC
        """)
    List<QCResult> findPendingVerification();

    /**
     * Find TO_VERIFY results assigned to a specific reviewer (REVIEWER: own batches only).
     */
    @Query("""
        SELECT DISTINCT qr FROM QCResult qr
        JOIN FETCH qr.batchFile bf
        JOIN FETCH bf.batch b
        JOIN FETCH b.assignedReviewer reviewer
        WHERE qr.qcDecision = 'TO_VERIFY'
          AND qr.finalDecision IS NULL
          AND reviewer.id = :reviewerId
        ORDER BY qr.failedCount DESC, qr.verifyCount DESC, qr.updatedAt ASC
        """)
    List<QCResult> findPendingVerificationForReviewer(@Param("reviewerId") Long reviewerId);

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
     * Check if a batch file already has a QC result.
     */
    boolean existsByBatchFileId(Long batchFileId);
}
