package com.shal.common.repository;

import com.shal.common.entity.Notification;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;

public interface NotificationRepository extends JpaRepository<Notification, Long> {

    List<Notification> findByRecipient_IdOrderByCreatedAtDesc(Long recipientId, Pageable pageable);

    long countByRecipient_IdAndReadFalse(Long recipientId);

    @Modifying
    @Query("UPDATE Notification n SET n.read = true, n.readAt = CURRENT_TIMESTAMP "
            + "WHERE n.recipient.id = :recipientId AND n.read = false")
    int markAllReadForRecipient(@Param("recipientId") Long recipientId);
}
