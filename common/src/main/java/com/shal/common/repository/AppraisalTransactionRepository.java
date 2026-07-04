package com.shal.common.repository;

import com.shal.common.entity.AppraisalTransaction;
import com.shal.common.entity.OrderDocumentStatus;
import com.shal.common.entity.TransactionStatus;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

@Repository
public interface AppraisalTransactionRepository extends JpaRepository<AppraisalTransaction, Long> {

    Optional<AppraisalTransaction> findByTransactionRef(String transactionRef);

    List<AppraisalTransaction> findByStatus(TransactionStatus status);

    @Query("SELECT t FROM AppraisalTransaction t WHERE t.client.id = :clientId ORDER BY t.createdAt DESC")
    Page<AppraisalTransaction> findByClientId(@Param("clientId") Long clientId, Pageable pageable);

    @Query("SELECT t FROM AppraisalTransaction t WHERE t.amcCode = :amcCode AND t.orderNumber = :orderNumber ORDER BY t.revisionNumber DESC")
    List<AppraisalTransaction> findByAmcAndOrder(
            @Param("amcCode") String amcCode,
            @Param("orderNumber") String orderNumber);

    /** Count transactions per status for dashboard. */
    @Query("SELECT t.status, COUNT(t) FROM AppraisalTransaction t GROUP BY t.status")
    List<Object[]> countByStatus();

    // ── Order (foundation) list/detail support ──────────────────────────────

    // NOTE: CAST(:search AS string) is required, not cosmetic — see the identical
    // note on BatchRepository.searchAdmin. Postgres resolves the LOWER(CONCAT(...))
    // function signature at plan time even when ":search IS NULL" short-circuits
    // the OR — an untyped null binds as bytea, so LOWER(bytea) fails.
    //
    // client must be fetched too: OrderApiController.toSummary() reads
    // order.getClient() after this query's own transaction has closed
    // (open-in-view=false) — a missing fetch throws LazyInitializationException.
    @EntityGraph(attributePaths = {"client", "assignedReviewer"})
    @Query("""
        SELECT t FROM AppraisalTransaction t
        WHERE (:clientId IS NULL OR t.client.id = :clientId)
          AND (:documentStatus IS NULL OR t.documentStatus = :documentStatus)
          AND (:search IS NULL OR LOWER(t.transactionRef) LIKE LOWER(CONCAT('%', CAST(:search AS string), '%'))
                                OR LOWER(t.propertyAddress) LIKE LOWER(CONCAT('%', CAST(:search AS string), '%')))
        ORDER BY t.updatedAt DESC
        """)
    Page<AppraisalTransaction> search(
            @Param("clientId") Long clientId,
            @Param("documentStatus") OrderDocumentStatus documentStatus,
            @Param("search") String search,
            Pageable pageable);

    @Query("SELECT t.documentStatus, COUNT(t) FROM AppraisalTransaction t GROUP BY t.documentStatus")
    List<Object[]> countByDocumentStatus();

    /** Single-order detail fetch with client eagerly loaded (see note on {@link #search}). */
    @EntityGraph(attributePaths = {"client", "assignedReviewer"})
    @Query("SELECT t FROM AppraisalTransaction t WHERE t.id = :id")
    Optional<AppraisalTransaction> findWithClientById(@Param("id") Long id);

    /**
     * A reviewer's own work queue — every Order allocated to them, optionally filtered
     * by document status. Order-level assignment means a reviewer sees exactly the
     * orders routed to them, not whole batches.
     */
    @EntityGraph(attributePaths = {"client", "assignedReviewer"})
    @Query("""
        SELECT t FROM AppraisalTransaction t
        WHERE t.assignedReviewer.id = :reviewerId
          AND (:documentStatus IS NULL OR t.documentStatus = :documentStatus)
        ORDER BY t.updatedAt DESC
        """)
    Page<AppraisalTransaction> findByAssignedReviewer(
            @Param("reviewerId") Long reviewerId,
            @Param("documentStatus") OrderDocumentStatus documentStatus,
            Pageable pageable);

    /** Unassigned orders (no reviewer yet), optionally client-scoped — the auto-assign pool. */
    @EntityGraph(attributePaths = {"client"})
    @Query("""
        SELECT t FROM AppraisalTransaction t
        WHERE t.assignedReviewer IS NULL
          AND (:clientId IS NULL OR t.client.id = :clientId)
        ORDER BY t.createdAt ASC
        """)
    List<AppraisalTransaction> findUnassigned(@Param("clientId") Long clientId);

    /** Current review load for a reviewer — used to balance auto-assignment. */
    long countByAssignedReviewer_Id(Long reviewerId);
}
