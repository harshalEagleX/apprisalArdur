package com.apprisal.common.entity;

import jakarta.persistence.*;
import java.time.LocalDateTime;

/**
 * Tracks every operator login session with performance metrics.
 * Powers the Operator Insights analytics section.
 */
@Entity
@Table(name = "operator_session",
       indexes = {
           @Index(name = "idx_op_session_user_start", columnList = "user_id, started_at DESC"),
           @Index(name = "idx_op_session_status",     columnList = "status")
       })
public class OperatorSession {

    public enum Status { ACTIVE, IDLE, ENDED }

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "user_id", nullable = false)
    private User user;

    @Column(name = "session_token", nullable = false, unique = true, length = 128)
    private String sessionToken;

    @Column(name = "started_at", nullable = false)
    private LocalDateTime startedAt;

    @Column(name = "last_active_at")
    private LocalDateTime lastActiveAt;

    @Column(name = "ended_at")
    private LocalDateTime endedAt;

    @Column(name = "ip_address", length = 50)
    private String ipAddress;

    @Column(name = "user_agent", length = 512)
    private String userAgent;

    @Column(name = "files_processed")
    private Integer filesProcessed = 0;

    @Column(name = "files_failed")
    private Integer filesFailed = 0;

    @Column(name = "corrections_made")
    private Integer correctionsMade = 0;

    @Column(name = "active_minutes")
    private Integer activeMinutes = 0;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 20)
    private Status status = Status.ACTIVE;

    @PrePersist
    protected void onCreate() {
        if (startedAt == null)  startedAt    = LocalDateTime.now();
        if (lastActiveAt == null) lastActiveAt = startedAt;
    }

    // ── Getters / Setters ─────────────────────────────────────────────────────
    public Long getId()                          { return id; }
    public User getUser()                        { return user; }
    public void setUser(User u)                  { this.user = u; }
    public String getSessionToken()              { return sessionToken; }
    public void setSessionToken(String v)        { this.sessionToken = v; }
    public LocalDateTime getStartedAt()          { return startedAt; }
    public void setStartedAt(LocalDateTime v)    { this.startedAt = v; }
    public LocalDateTime getLastActiveAt()       { return lastActiveAt; }
    public void setLastActiveAt(LocalDateTime v) { this.lastActiveAt = v; }
    public LocalDateTime getEndedAt()            { return endedAt; }
    public void setEndedAt(LocalDateTime v)      { this.endedAt = v; }
    public String getIpAddress()                 { return ipAddress; }
    public void setIpAddress(String v)           { this.ipAddress = v; }
    public String getUserAgent()                 { return userAgent; }
    public void setUserAgent(String v)           { this.userAgent = v; }
    public Integer getFilesProcessed()           { return filesProcessed; }
    public void setFilesProcessed(Integer v)     { this.filesProcessed = v; }
    public Integer getFilesFailed()              { return filesFailed; }
    public void setFilesFailed(Integer v)        { this.filesFailed = v; }
    public Integer getCorrectionsMade()          { return correctionsMade; }
    public void setCorrectionsMade(Integer v)    { this.correctionsMade = v; }
    public Integer getActiveMinutes()            { return activeMinutes; }
    public void setActiveMinutes(Integer v)      { this.activeMinutes = v; }
    public Status getStatus()                    { return status; }
    public void setStatus(Status v)              { this.status = v; }

    public static Builder builder() { return new Builder(); }
    public static class Builder {
        private final OperatorSession s = new OperatorSession();
        public Builder user(User v)          { s.user = v;          return this; }
        public Builder sessionToken(String v){ s.sessionToken = v;  return this; }
        public Builder ipAddress(String v)   { s.ipAddress = v;     return this; }
        public Builder userAgent(String v)   { s.userAgent = v;     return this; }
        public OperatorSession build()       { return s; }
    }
}
