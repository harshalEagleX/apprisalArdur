package com.apprisal.common.repository;

import com.apprisal.common.entity.OperatorSession;
import com.apprisal.common.entity.OperatorSession.Status;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

@Repository
public interface OperatorSessionRepository extends JpaRepository<OperatorSession, Long> {

    Optional<OperatorSession> findBySessionToken(String token);

    List<OperatorSession> findByUserIdAndStatus(Long userId, Status status);

    Page<OperatorSession> findByUserId(Long userId, Pageable pageable);

    @Query("SELECT s FROM OperatorSession s WHERE s.user.id = :userId AND s.startedAt >= :from ORDER BY s.startedAt DESC")
    List<OperatorSession> findByUserIdSince(@Param("userId") Long userId, @Param("from") LocalDateTime from);

    @Query("""
        SELECT s.user.id, SUM(s.activeMinutes), SUM(s.filesProcessed), SUM(s.correctionsMade)
        FROM OperatorSession s
        WHERE s.startedAt >= :from
        GROUP BY s.user.id
        """)
    List<Object[]> aggregateByUserSince(@Param("from") LocalDateTime from);

    @Query("SELECT SUM(s.filesProcessed) FROM OperatorSession s WHERE s.user.id = :userId")
    Long totalFilesProcessedByUser(@Param("userId") Long userId);

    @Query("SELECT SUM(s.activeMinutes) FROM OperatorSession s WHERE s.user.id = :userId")
    Long totalActiveMinutesByUser(@Param("userId") Long userId);

    @Query("SELECT COUNT(s) FROM OperatorSession s WHERE s.status = :status")
    long countByStatus(@Param("status") Status status);
}
