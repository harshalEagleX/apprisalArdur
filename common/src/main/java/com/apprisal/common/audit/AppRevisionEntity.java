package com.apprisal.common.audit;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;
import org.hibernate.envers.DefaultRevisionEntity;
import org.hibernate.envers.RevisionEntity;

@Entity
@Table(name = "revision_info")
@RevisionEntity(AppRevisionListener.class)
public class AppRevisionEntity extends DefaultRevisionEntity {

    @Column(name = "username", length = 100)
    private String username;

    @Column(name = "ip_address", length = 50)
    private String ipAddress;

    @Column(name = "correlation_id", length = 64)
    private String correlationId;

    public String getUsername()        { return username; }
    public void   setUsername(String v){ this.username = v; }

    public String getIpAddress()        { return ipAddress; }
    public void   setIpAddress(String v){ this.ipAddress = v; }

    public String getCorrelationId()        { return correlationId; }
    public void   setCorrelationId(String v){ this.correlationId = v; }
}
