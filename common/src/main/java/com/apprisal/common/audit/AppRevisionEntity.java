package com.apprisal.common.audit;

import jakarta.persistence.*;
import org.hibernate.envers.RevisionEntity;
import org.hibernate.envers.RevisionNumber;
import org.hibernate.envers.RevisionTimestamp;

import java.io.Serializable;
import java.time.Instant;

@Entity
@Table(name = "revision_info")
@RevisionEntity(AppRevisionListener.class)
public class AppRevisionEntity implements Serializable {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE, generator = "revision_seq")
    @SequenceGenerator(name = "revision_seq", sequenceName = "revision_info_id_seq", allocationSize = 1)
    @RevisionNumber
    @Column(name = "id")
    private Integer id;

    @RevisionTimestamp
    @Column(name = "timestamp", nullable = false)
    private long timestamp;

    @Column(name = "username", length = 100)
    private String username;

    @Column(name = "ip_address", length = 50)
    private String ipAddress;

    @Column(name = "correlation_id", length = 64)
    private String correlationId;

    public Integer getId()               { return id; }
    public long    getTimestamp()        { return timestamp; }
    public Instant getRevisionInstant()  { return Instant.ofEpochMilli(timestamp); }

    public String getUsername()              { return username; }
    public void   setUsername(String v)      { this.username = v; }
    public String getIpAddress()             { return ipAddress; }
    public void   setIpAddress(String v)     { this.ipAddress = v; }
    public String getCorrelationId()         { return correlationId; }
    public void   setCorrelationId(String v) { this.correlationId = v; }
}
