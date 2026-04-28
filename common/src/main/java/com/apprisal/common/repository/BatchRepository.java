package com.apprisal.common.repository;

import com.apprisal.common.entity.Batch;
import com.apprisal.common.entity.BatchStatus;
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
public interface BatchRepository extends JpaRepository<Batch, Long> {

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

    // Efficient TopN queries for dashboards
    List<Batch> findTop10ByOrderByCreatedAtDesc();

    List<Batch> findTop5ByClientIdOrderByCreatedAtDesc(Long clientId);

    List<Batch> findTop10ByAssignedReviewerIdOrderByUpdatedAtDesc(Long reviewerId);
}
