package com.shal.common.repository;

import com.shal.common.entity.BatchFile;
import com.shal.common.entity.FileStatus;
import com.shal.common.entity.FileType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface BatchFileRepository extends JpaRepository<BatchFile, Long> {

    List<BatchFile> findByBatchId(Long batchId);

    List<BatchFile> findByBatchIdAndFileType(Long batchId, FileType fileType);

    List<BatchFile> findByBatchIdAndStatus(Long batchId, FileStatus status);

    /**
     * Find files by batch, orderId, and type - for matching appraisal with
     * engagement. Returns List to handle possible duplicates.
     */
    List<BatchFile> findByBatchIdAndOrderIdAndFileType(Long batchId, String orderId, FileType fileType);

    /** Find files scoped to a specific property set within a batch. */
    List<BatchFile> findByBatchIdAndPropertySetNameAndFileType(Long batchId, String propertySetName, FileType fileType);

    /** True when a file with the given id belongs to the given batch. Used to validate partial re-QC requests. */
    boolean existsByIdAndBatchId(Long id, Long batchId);

    /** Find all files that belong to a specific property set in a batch. */
    List<BatchFile> findByBatchIdAndPropertySetName(Long batchId, String propertySetName);

    /**
     * Find all files with a specific orderId in a batch.
     */
    List<BatchFile> findByBatchIdAndOrderId(Long batchId, String orderId);

    // order is fetched too: QCProcessingService.processFilePair reads
    // appraisal.getOrder() after this method's own transaction has already closed
    // (the long Python/OCR call deliberately runs without holding a DB transaction),
    // so the association must already be populated or it throws
    // LazyInitializationException ("no session") on the detached entity.
    @Query("""
        SELECT bf FROM BatchFile bf
        JOIN FETCH bf.batch b
        LEFT JOIN FETCH b.assignedReviewer
        LEFT JOIN FETCH bf.order
        WHERE bf.id = :batchFileId
        """)
    java.util.Optional<BatchFile> findWithBatchAndReviewerById(@Param("batchFileId") Long batchFileId);

    @Query("SELECT COUNT(bf) FROM BatchFile bf WHERE bf.batch.id = :batchId")
    long countByBatchId(@Param("batchId") Long batchId);

    @Query("SELECT COUNT(bf) FROM BatchFile bf WHERE bf.batch.assignedReviewer.id = :reviewerId")
    long countByReviewerId(@Param("reviewerId") Long reviewerId);

    long countByBatchIdAndFileType(Long batchId, FileType fileType);

    @Query("SELECT COUNT(bf) FROM BatchFile bf WHERE bf.batch.id = :batchId AND bf.status = :status")
    long countByBatchIdAndStatus(@Param("batchId") Long batchId, @Param("status") FileStatus status);

    @Query("SELECT COUNT(bf) FROM BatchFile bf WHERE bf.batch.client.id = :clientId AND bf.status = :status")
    long countByClientIdAndStatus(@Param("clientId") Long clientId, @Param("status") FileStatus status);

    /** Per-client file totals in one grouped query: [clientId, totalFiles]. */
    @Query("""
        SELECT bf.batch.client.id, COUNT(bf)
        FROM BatchFile bf
        WHERE bf.batch.client.id IS NOT NULL
        GROUP BY bf.batch.client.id
        """)
    List<Object[]> clientFileCounts();

    /**
     * Bulk file load for multiple batches in one query.
     * JOIN FETCH batch so callers can group by batch.id without LAZY loads.
     * Replaces the N per-batch findByBatchId() calls in AuditGraphController.
     */
    @Query("SELECT f FROM BatchFile f JOIN FETCH f.batch WHERE f.batch.id IN :batchIds ORDER BY f.batch.id, f.id")
    List<BatchFile> findByBatchIdIn(@Param("batchIds") List<Long> batchIds);

    // ── Order identity resolution (cross-batch) ─────────────────────────────

    /**
     * Cross-batch content-hash dedup lookup: is there already a document with
     * this exact content that's linked to a resolved Order? Used to detect a
     * pure re-upload before creating a new Order.
     *
     * Written as explicit JPQL (not a derived method name) because the
     * "order" property name collides with Spring Data's "OrderBy" method-name
     * keyword parsing.
     */
    @Query("""
        SELECT bf FROM BatchFile bf
        WHERE bf.contentHash = :contentHash AND bf.order IS NOT NULL
        ORDER BY bf.createdAt ASC
        """)
    List<BatchFile> findByContentHashLinkedToOrder(@Param("contentHash") String contentHash);

    /** Cross-batch orderId identity match, scoped to the same client. */
    @Query("""
        SELECT bf FROM BatchFile bf
        WHERE bf.order IS NOT NULL
          AND bf.orderId = :orderId
          AND bf.batch.client.id = :clientId
        ORDER BY bf.createdAt ASC
        """)
    List<BatchFile> findByOrderIdStringAndClientId(@Param("orderId") String orderId, @Param("clientId") Long clientId);

    /** Cross-batch propertySetName identity match, scoped to the same client. */
    @Query("""
        SELECT bf FROM BatchFile bf
        WHERE bf.order IS NOT NULL
          AND bf.propertySetName = :propertySetName
          AND bf.batch.client.id = :clientId
        ORDER BY bf.createdAt ASC
        """)
    List<BatchFile> findByPropertySetNameAndClientId(@Param("propertySetName") String propertySetName, @Param("clientId") Long clientId);

    /**
     * Active (non-superseded) documents for a resolved Order. Joins bf.batch so the
     * Batch @SQLRestriction (deleted_at IS NULL) applies — a soft-deleted batch's
     * documents must never count toward an Order, keeping the Order summary count
     * consistent with the detail view (findAllByOrderId).
     */
    @Query("SELECT bf FROM BatchFile bf JOIN bf.batch b WHERE bf.order.id = :orderId AND bf.supersededAt IS NULL")
    List<BatchFile> findActiveByOrderId(@Param("orderId") Long orderId);

    @Query("SELECT bf FROM BatchFile bf WHERE bf.order.id = :orderId AND bf.fileType = :fileType AND bf.supersededAt IS NULL")
    List<BatchFile> findActiveByOrderIdAndFileType(@Param("orderId") Long orderId, @Param("fileType") FileType fileType);

    /**
     * All documents (active + superseded) ever linked to a resolved Order — version
     * history. batch is fetched too: OrderApiController.toDetail() reads
     * f.getBatch().getId() for each document after this query's own transaction has
     * closed (open-in-view=false) — a missing fetch throws LazyInitializationException.
     */
    @Query("SELECT bf FROM BatchFile bf LEFT JOIN FETCH bf.batch WHERE bf.order.id = :orderId ORDER BY bf.createdAt DESC")
    List<BatchFile> findAllByOrderId(@Param("orderId") Long orderId);

    /** Batch-membership rollup: which batches touched this Order. */
    @Query("SELECT DISTINCT bf.batch.id FROM BatchFile bf WHERE bf.order.id = :orderId")
    List<Long> findDistinctBatchIdsByOrderId(@Param("orderId") Long orderId);

    /** Total documents (active + superseded) still linked to an Order — used to detect an
     * orphaned Order after its last referencing batch is deleted. */
    @Query("SELECT COUNT(bf) FROM BatchFile bf WHERE bf.order.id = :orderId")
    long countAllByOrderId(@Param("orderId") Long orderId);

    /** Legacy files (ingested before Order resolution existed) awaiting one-time backfill. */
    @Query("SELECT bf FROM BatchFile bf WHERE bf.order IS NULL")
    List<BatchFile> findUnresolvedOrderFiles();

    @Query("SELECT COUNT(bf) FROM BatchFile bf WHERE bf.order IS NULL")
    long countUnresolvedOrderFiles();
}
