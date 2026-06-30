package com.shal.common.repository;

import com.shal.common.entity.AppraisalTransaction;
import com.shal.common.entity.TransactionStatus;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
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
}
