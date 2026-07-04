package com.shal.common.entity;

import com.shal.common.util.AppTime;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.PrePersist;
import jakarta.persistence.Table;

import java.time.LocalDateTime;

/**
 * An in-app notification delivered to one user (currently: a reviewer who was
 * assigned an order). Persisted so the notification bell shows history and an
 * unread badge across sessions. Java-owned table (JPA/Hibernate ddl-auto=update).
 */
@Entity
@Table(name = "notification", indexes = {
        @Index(name = "idx_notification_recipient", columnList = "recipient_id, is_read, created_at")
})
public class Notification {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    /** Who receives this notification. */
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "recipient_id", nullable = false)
    private User recipient;

    /** Who triggered it (the admin who assigned), optional. */
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "actor_id")
    private User actor;

    @Column(name = "type", length = 50, nullable = false)
    private String type;

    @Column(name = "title", length = 200, nullable = false)
    private String title;

    @Column(name = "message", columnDefinition = "text")
    private String message;

    /** Optional deep-link the frontend can navigate to (e.g. /admin/orders/123). */
    @Column(name = "link", length = 300)
    private String link;

    @Column(name = "is_read", nullable = false)
    private boolean read = false;

    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;

    @Column(name = "read_at")
    private LocalDateTime readAt;

    @PrePersist
    protected void onCreate() {
        if (createdAt == null) createdAt = AppTime.now();
    }

    public Notification() {
    }

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public User getRecipient() { return recipient; }
    public void setRecipient(User recipient) { this.recipient = recipient; }

    public User getActor() { return actor; }
    public void setActor(User actor) { this.actor = actor; }

    public String getType() { return type; }
    public void setType(String type) { this.type = type; }

    public String getTitle() { return title; }
    public void setTitle(String title) { this.title = title; }

    public String getMessage() { return message; }
    public void setMessage(String message) { this.message = message; }

    public String getLink() { return link; }
    public void setLink(String link) { this.link = link; }

    public boolean isRead() { return read; }
    public void setRead(boolean read) { this.read = read; }

    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime createdAt) { this.createdAt = createdAt; }

    public LocalDateTime getReadAt() { return readAt; }
    public void setReadAt(LocalDateTime readAt) { this.readAt = readAt; }
}
