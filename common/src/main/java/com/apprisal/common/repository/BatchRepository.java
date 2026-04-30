package com.apprisal.common.repository;

import com.apprisal.common.entity.Batch;
import com.apprisal.common.entity.BatchStatus;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

@Repository
public interface BatchRepository extends JpaRepository<Batch, Long> {

    /**
     * Eagerly load client and assignedReviewer on the paginated list.
     *
     * Without this, both associations are LAZY. When the Hibernate session closes after
     * findAll() returns (open-in-view=false), any access to b.getClient() or
     * b.getAssignedReviewer() from outside a transaction throws LazyInitializationException.
     *
     * @EntityGraph uses LEFT JOIN (not JOIN FETCH), so it is safe with pagination —
     * Hibernate does not load the full result set into memory before paginating.
     */
    @Override
    @EntityGraph(attributePaths = {"client", "assignedReviewer"})
    Page<Batch> findAll(org.springframework.data.domain.Pageable pageable);

    @EntityGraph(attributePaths = {"files"})
    Optional<Batch> findWithFilesById(Long id);

    List<Batch> findByClientId(Long clientId);

    Page<Batch> findByClientId(Long clientId, Pageable pageable);

    List<Batch> findByStatus(BatchStatus status);

    List<Batch> findByAssignedReviewerId(Long reviewerId);

    Page<Batch> findByAssignedReviewerId(Long reviewerId, Pageable pageable);

    List<Batch> findByCreatedById(Long userId);

    @Query("SELECT COUNT(b) FROM Batch b WHERE b.client.id = :clientId")
    long countByClientId(@Param("clientId") Long clientId);

    @Query("SELECT COUNT(b) FROM Batch b WHERE b.client.id = :clientId AND b.status = :status")
    long countByClientIdAndStatus(@Param("clientId") Long clientId, @Param("status") BatchStatus status);

    @Query("SELECT COUNT(b) FROM Batch b WHERE b.status = :status")
    long countByStatus(@Param("status") BatchStatus status);

    @Query("SELECT COUNT(b) FROM Batch b WHERE b.assignedReviewer.id = :reviewerId AND b.status = :status")
    long countByAssignedReviewerIdAndStatus(@Param("reviewerId") Long reviewerId, @Param("status") BatchStatus status);

    List<Batch> findByAssignedReviewerIdAndStatus(Long reviewerId, BatchStatus status);

    // Duplicate upload detection
    Optional<Batch> findByFileHash(String fileHash);

    /**
     * Atomically claim a batch before dispatching async QC work.
     * This closes the double-click race where two HTTP requests both saw UPLOADED
     * and launched parallel qc-worker threads for the same batch.
     */
    @Modifying(clearAutomatically = true, flushAutomatically = true)
    @Query("""
        UPDATE Batch b
        SET b.status = com.apprisal.common.entity.BatchStatus.QC_PROCESSING,
            b.errorMessage = null,
            b.updatedAt = CURRENT_TIMESTAMP,
            b.version = b.version + 1
        WHERE b.id = :batchId
          AND b.status IN (
            com.apprisal.common.entity.BatchStatus.UPLOADED,
            com.apprisal.common.entity.BatchStatus.VALIDATING,
            com.apprisal.common.entity.BatchStatus.ERROR
          )
        """)
    int markQcProcessingIfTriggerable(@Param("batchId") Long batchId);

    /**
     * Return a running batch to UPLOADED after an admin stop request.
     * The existing uploaded files remain available, so the admin can run QC again.
     */
    @Modifying(clearAutomatically = true, flushAutomatically = true)
    @Query("""
        UPDATE Batch b
        SET b.status = com.apprisal.common.entity.BatchStatus.UPLOADED,
            b.errorMessage = :message,
            b.updatedAt = CURRENT_TIMESTAMP,
            b.version = b.version + 1
        WHERE b.id = :batchId
          AND b.status = com.apprisal.common.entity.BatchStatus.QC_PROCESSING
        """)
    int markUploadedIfQcProcessing(@Param("batchId") Long batchId, @Param("message") String message);

    /**
     * Find batches stuck in QC_PROCESSING whose updatedAt is older than the given cutoff.
     * Used by StuckBatchReconciler to detect and recover incomplete processing runs.
     *
     * A batch is "stuck" when:
     *   - The async QC thread crashed or the JVM was killed mid-processing
     *   - Python rejected the request and Java never updated the status
     *   - The processing thread timed out without catching the exception
     */
    @Query("""
        SELECT b FROM Batch b
        WHERE b.status = com.apprisal.common.entity.BatchStatus.QC_PROCESSING
          AND b.updatedAt < :cutoff
        ORDER BY b.updatedAt ASC
        """)
    List<Batch> findStuckInQcProcessing(@Param("cutoff") LocalDateTime cutoff);

    // Efficient TopN queries for dashboards
    List<Batch> findTop10ByOrderByCreatedAtDesc();

    List<Batch> findTop5ByClientIdOrderByCreatedAtDesc(Long clientId);

    List<Batch> findTop10ByAssignedReviewerIdOrderByUpdatedAtDesc(Long reviewerId);
}
