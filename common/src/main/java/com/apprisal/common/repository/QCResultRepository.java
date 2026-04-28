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

    /**
     * Find all QC results for a batch.
     */
    @Query("SELECT qr FROM QCResult qr WHERE qr.batchFile.batch.id = :batchId")
    List<QCResult> findByBatchId(@Param("batchId") Long batchId);

    /**
     * Find all QC results with a specific decision type.
     */
    List<QCResult> findByQcDecision(QCDecision qcDecision);

    /**
     * Find all TO_VERIFY results that haven't been reviewed.
     */
    @Query("SELECT qr FROM QCResult qr WHERE qr.qcDecision = 'TO_VERIFY' AND qr.finalDecision IS NULL")
    List<QCResult> findPendingVerification();

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
