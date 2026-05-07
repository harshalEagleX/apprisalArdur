package com.apprisal.common.repository;

import com.apprisal.common.entity.AuditLog;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.time.LocalDateTime;
import java.util.List;

@Repository
public interface AuditLogRepository extends JpaRepository<AuditLog, Long> {

    Page<AuditLog> findByUserId(Long userId, Pageable pageable);

    List<AuditLog> findByEntityTypeAndEntityId(String entityType, Long entityId);

    @Query("SELECT al FROM AuditLog al LEFT JOIN FETCH al.user WHERE al.entityType = :entityType AND al.entityId IN :ids ORDER BY al.createdAt ASC")
    List<AuditLog> findByEntityTypeAndEntityIdIn(@Param("entityType") String entityType, @Param("ids") List<Long> ids);

    @Query("SELECT al FROM AuditLog al LEFT JOIN FETCH al.user WHERE al.user.id = :userId ORDER BY al.createdAt DESC LIMIT 500")
    List<AuditLog> findRecentByUserId(@Param("userId") Long userId);

    Page<AuditLog> findByAction(String action, Pageable pageable);

    Page<AuditLog> findByCreatedAtBetween(LocalDateTime start, LocalDateTime end, Pageable pageable);

    List<AuditLog> findTop10ByOrderByCreatedAtDesc();

    List<AuditLog> findTop10ByUserIdOrderByCreatedAtDesc(Long userId);
}
