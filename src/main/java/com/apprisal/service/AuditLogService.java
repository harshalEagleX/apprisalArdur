package com.apprisal.service;

import com.apprisal.entity.AuditLog;
import com.apprisal.entity.User;
import com.apprisal.repository.AuditLogRepository;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.lang.NonNull;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Objects;

/**
 * Service for managing audit logs - tracking all user actions.
 */
@Service
public class AuditLogService {

    private final AuditLogRepository auditLogRepository;

    public AuditLogService(AuditLogRepository auditLogRepository) {
        this.auditLogRepository = auditLogRepository;
    }

    @Transactional
    @SuppressWarnings("null")
    public @NonNull AuditLog log(User user, String action, String entityType, Long entityId, String details,
            String ipAddress,
            String userAgent) {
        AuditLog log = AuditLog.builder()
                .user(user)
                .action(action)
                .entityType(entityType)
                .entityId(entityId)
                .details(details)
                .ipAddress(ipAddress)
                .userAgent(userAgent)
                .build();
        return Objects.requireNonNull(auditLogRepository.save(log));
    }

    @Transactional
    public @NonNull AuditLog logSimple(User user, String action) {
        return log(user, action, null, null, null, null, null);
    }

    @Transactional
    public @NonNull AuditLog logEntity(User user, String action, String entityType, Long entityId) {
        return log(user, action, entityType, entityId, null, null, null);
    }

    public Page<AuditLog> getByUser(Long userId, Pageable pageable) {
        return auditLogRepository.findByUserId(userId, pageable);
    }

    public List<AuditLog> getByEntity(String entityType, Long entityId) {
        return auditLogRepository.findByEntityTypeAndEntityId(entityType, entityId);
    }

    public Page<AuditLog> getByAction(String action, Pageable pageable) {
        return auditLogRepository.findByAction(action, pageable);
    }

    public Page<AuditLog> getByDateRange(LocalDateTime start, LocalDateTime end, Pageable pageable) {
        return auditLogRepository.findByCreatedAtBetween(start, end, pageable);
    }

    public List<AuditLog> getRecentLogs() {
        return auditLogRepository.findTop10ByOrderByCreatedAtDesc();
    }

    public List<AuditLog> findByUserId(Long userId) {
        return auditLogRepository.findTop10ByUserIdOrderByCreatedAtDesc(userId);
    }

    public List<AuditLog> getRecentLogsByUser(Long userId) {
        return auditLogRepository.findTop10ByUserIdOrderByCreatedAtDesc(userId);
    }
}
