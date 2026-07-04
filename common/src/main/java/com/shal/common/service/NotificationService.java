package com.shal.common.service;

import com.shal.common.entity.AppraisalTransaction;
import com.shal.common.entity.Notification;
import com.shal.common.entity.User;
import com.shal.common.repository.NotificationRepository;
import com.shal.common.util.AppTime;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

/**
 * Creates and reads in-app notifications. Currently the only producer is order
 * assignment (a reviewer is told when they receive an order), but the API is
 * generic so any future event can push a notification.
 *
 * Notification creation must never break the action that triggered it — callers
 * wrap {@link #notifyOrderAssigned} so an assignment still succeeds even if the
 * notification insert fails (graceful degradation, P-6).
 */
@Service
public class NotificationService {

    private static final Logger log = LoggerFactory.getLogger(NotificationService.class);

    private final NotificationRepository repository;

    public NotificationService(NotificationRepository repository) {
        this.repository = repository;
    }

    /** Notify a reviewer that they've been assigned an order. Best-effort — never throws. */
    @Transactional
    public void notifyOrderAssigned(User reviewer, AppraisalTransaction order, User actor) {
        if (reviewer == null || order == null) return;
        try {
            Notification n = new Notification();
            n.setRecipient(reviewer);
            n.setActor(actor);
            n.setType("ORDER_ASSIGNED");
            n.setTitle("New order assigned");
            n.setMessage("You've been assigned order " + order.getTransactionRef()
                    + (actor != null ? " by " + displayName(actor) : "") + ".");
            n.setLink("/reviewer");
            repository.save(n);
        } catch (Exception e) {
            log.warn("Failed to create ORDER_ASSIGNED notification for reviewer {}: {}",
                    reviewer.getId(), e.getMessage());
        }
    }

    @Transactional(readOnly = true)
    public List<Notification> recentFor(Long recipientId, int limit) {
        return repository.findByRecipient_IdOrderByCreatedAtDesc(recipientId, PageRequest.of(0, limit));
    }

    @Transactional(readOnly = true)
    public long unreadCount(Long recipientId) {
        return repository.countByRecipient_IdAndReadFalse(recipientId);
    }

    /** Mark one notification read — only if it belongs to this recipient. Returns true if updated. */
    @Transactional
    public boolean markRead(Long notificationId, Long recipientId) {
        return repository.findById(notificationId)
                .filter(n -> n.getRecipient() != null && recipientId.equals(n.getRecipient().getId()))
                .map(n -> {
                    if (!n.isRead()) {
                        n.setRead(true);
                        n.setReadAt(AppTime.now());
                        repository.save(n);
                    }
                    return true;
                })
                .orElse(false);
    }

    @Transactional
    public int markAllRead(Long recipientId) {
        return repository.markAllReadForRecipient(recipientId);
    }

    private static String displayName(User u) {
        return u.getFullName() != null && !u.getFullName().isBlank() ? u.getFullName() : u.getUsername();
    }
}
