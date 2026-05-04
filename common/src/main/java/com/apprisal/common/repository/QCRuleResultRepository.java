package com.apprisal.common.repository;

import com.apprisal.common.entity.QCRuleResult;
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.time.LocalDateTime;

/**
 * Repository for QCRuleResult entities.
 */
@Repository
public interface QCRuleResultRepository extends JpaRepository<QCRuleResult, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("""
        SELECT rr FROM QCRuleResult rr
        JOIN FETCH rr.qcResult qr
        LEFT JOIN FETCH qr.batchFile bf
        WHERE rr.id = :id
        """)
    java.util.Optional<QCRuleResult> findByIdForUpdate(@Param("id") Long id);

    /**
     * Find all rule results for a QC result.
     */
    List<QCRuleResult> findByQcResultId(Long qcResultId);

    @Modifying(clearAutomatically = true, flushAutomatically = true)
    @Query("""
        DELETE FROM QCRuleResult rr
        WHERE rr.qcResult.id IN (
            SELECT qr.id FROM QCResult qr WHERE qr.batchFile.batch.id = :batchId
        )
        """)
    int deleteByBatchId(@Param("batchId") Long batchId);

    /**
     * Find all rule results that need verification.
     */
    List<QCRuleResult> findByNeedsVerificationTrue();

    /**
     * Find rule results by status.
     */
    List<QCRuleResult> findByStatus(String status);

    /**
     * Find all VERIFY/FAIL/system-error results that need reviewer action for a QC result.
     */
    @Query("SELECT rr FROM QCRuleResult rr WHERE rr.qcResult.id = :qcResultId AND rr.needsVerification = true ORDER BY rr.id ASC")
    List<QCRuleResult> findVerificationItemsForQcResult(@Param("qcResultId") Long qcResultId);

    /**
     * Find unverified rule results for a QC result.
     */
    @Query("""
        SELECT rr FROM QCRuleResult rr
        WHERE rr.qcResult.id = :qcResultId
          AND rr.needsVerification = true
          AND (rr.reviewerVerified IS NULL OR rr.overridePending = true)
        ORDER BY rr.id ASC
        """)
    List<QCRuleResult> findPendingVerificationForQcResult(@Param("qcResultId") Long qcResultId);

    /**
     * Count rule results by status for a QC result.
     */
    @Query("SELECT rr.status, COUNT(rr) FROM QCRuleResult rr WHERE rr.qcResult.id = :qcResultId GROUP BY rr.status")
    List<Object[]> countByStatusForQcResult(@Param("qcResultId") Long qcResultId);

    /**
     * Count reviewer progress in one cheap aggregate query.
     * Returns: totalRules, totalToVerify, pending.
     */
    @Query("""
        SELECT COUNT(rr),
               SUM(CASE WHEN rr.needsVerification = true THEN 1 ELSE 0 END),
               SUM(CASE WHEN rr.needsVerification = true
                         AND (rr.reviewerVerified IS NULL OR rr.overridePending = true)
                        THEN 1 ELSE 0 END)
        FROM QCRuleResult rr
        WHERE rr.qcResult.id = :qcResultId
        """)
    List<Object[]> progressCountsForQcResult(@Param("qcResultId") Long qcResultId);

    @Query("""
        SELECT rr FROM QCRuleResult rr
        JOIN FETCH rr.qcResult qr
        JOIN FETCH qr.batchFile bf
        WHERE rr.needsVerification = true
          AND rr.reviewerVerified IS NULL
          AND rr.firstPresentedAt IS NOT NULL
          AND rr.firstPresentedAt < :cutoff
        ORDER BY rr.firstPresentedAt ASC
        """)
    List<QCRuleResult> findOverdueReviewItems(@Param("cutoff") LocalDateTime cutoff);

    @Query("""
        SELECT rr.overrideRequestedBy.id, COUNT(rr)
        FROM QCRuleResult rr
        WHERE rr.overrideRequestedBy IS NOT NULL
          AND rr.overrideRequestedAt >= :from
        GROUP BY rr.overrideRequestedBy.id
        ORDER BY COUNT(rr) DESC
        """)
    List<Object[]> countFailOverridesByReviewerSince(@Param("from") LocalDateTime from);

    @Query("""
        SELECT rr.qcResult.reviewedBy.id, AVG(rr.decisionLatencyMs), COUNT(rr)
        FROM QCRuleResult rr
        WHERE rr.decisionLatencyMs IS NOT NULL
          AND rr.verifiedAt >= :from
          AND rr.qcResult.reviewedBy IS NOT NULL
        GROUP BY rr.qcResult.reviewedBy.id
        HAVING COUNT(rr) >= 10
        ORDER BY AVG(rr.decisionLatencyMs) ASC
        """)
    List<Object[]> averageDecisionLatencyByReviewerSince(@Param("from") LocalDateTime from);
}
