package com.apprisal.common.repository;

import com.apprisal.common.entity.ProcessingMetrics;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

@Repository
public interface ProcessingMetricsRepository extends JpaRepository<ProcessingMetrics, Long> {

    Optional<ProcessingMetrics> findByQcResultId(Long qcResultId);

    void deleteByQcResultId(Long qcResultId);

    @Modifying(clearAutomatically = true, flushAutomatically = true)
    @Query("""
        DELETE FROM ProcessingMetrics m
        WHERE m.qcResult.id IN (
            SELECT qr.id FROM QCResult qr WHERE qr.batchFile.batch.id = :batchId
        )
        """)
    int deleteByBatchId(@Param("batchId") Long batchId);

    @Transactional(readOnly = true)
    @Query("SELECT AVG(m.ocrConfidenceAvg) FROM ProcessingMetrics m WHERE m.createdAt >= :from")
    Double avgOcrConfidenceSince(@Param("from") LocalDateTime from);

    @Transactional(readOnly = true)
    @Query("SELECT AVG(m.totalProcessingMs) FROM ProcessingMetrics m WHERE m.createdAt >= :from")
    Double avgProcessingMsSince(@Param("from") LocalDateTime from);

    @Transactional(readOnly = true)
    @Query("SELECT AVG(m.rulePassRate) FROM ProcessingMetrics m WHERE m.createdAt >= :from")
    Double avgRulePassRateSince(@Param("from") LocalDateTime from);

    @Transactional(readOnly = true)
    @Query("SELECT COUNT(m) FROM ProcessingMetrics m WHERE m.cacheHit = true AND m.createdAt >= :from")
    long cacheHitCountSince(@Param("from") LocalDateTime from);

    @Transactional(readOnly = true)
    @Query("SELECT COUNT(m) FROM ProcessingMetrics m WHERE m.createdAt >= :from")
    long countSince(@Param("from") LocalDateTime from);

    @Transactional(readOnly = true)
    @Query("SELECT m.extractionMethod, COUNT(m) FROM ProcessingMetrics m WHERE m.createdAt >= :from GROUP BY m.extractionMethod")
    List<Object[]> countByExtractionMethodSince(@Param("from") LocalDateTime from);

    @Transactional(readOnly = true)
    @Query("SELECT m.modelVersion, AVG(m.rulePassRate), COUNT(m) FROM ProcessingMetrics m WHERE m.modelVersion IS NOT NULL AND m.createdAt >= :from GROUP BY m.modelVersion ORDER BY m.modelVersion")
    List<Object[]> modelVersionStats(@Param("from") LocalDateTime from);

    @Transactional(readOnly = true)
    @Query("""
        SELECT DATE(m.createdAt), AVG(m.ocrConfidenceAvg), AVG(m.rulePassRate), COUNT(m)
        FROM ProcessingMetrics m
        WHERE m.createdAt >= :from
        GROUP BY DATE(m.createdAt)
        ORDER BY DATE(m.createdAt)
        """)
    List<Object[]> dailyTrendSince(@Param("from") LocalDateTime from);
}
