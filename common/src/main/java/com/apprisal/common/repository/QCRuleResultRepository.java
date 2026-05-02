package com.apprisal.common.repository;

import com.apprisal.common.entity.QCRuleResult;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.List;

/**
 * Repository for QCRuleResult entities.
 */
@Repository
public interface QCRuleResultRepository extends JpaRepository<QCRuleResult, Long> {

    /**
     * Find all rule results for a QC result.
     */
    List<QCRuleResult> findByQcResultId(Long qcResultId);

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
}
