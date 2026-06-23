package com.shal.common.entity;

import com.shal.common.util.AppTime;
import jakarta.persistence.*;

import java.time.LocalDateTime;

/**
 * Append-only business event stream used for lifecycle, audit, and automation.
 */
@Entity
@Table(name = "business_event",
       indexes = {
           @Index(name = "idx_business_event_type_time", columnList = "event_type, occurred_at"),
           @Index(name = "idx_business_event_batch_time", columnList = "batch_id, occurred_at"),
           @Index(name = "idx_business_event_qc_time", columnList = "qc_result_id, occurred_at"),
           @Index(name = "idx_business_event_corr", columnList = "correlation_id")
       })
public class BusinessEvent {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "event_type", nullable = false, length = 100)
    private String eventType;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "actor_user_id")
    private User actor;

    @Column(name = "actor_role", length = 50)
    private String actorRole;

    @Column(name = "entity_type", length = 100)
    private String entityType;

    @Column(name = "entity_id")
    private Long entityId;

    @Column(name = "batch_id")
    private Long batchId;

    @Column(name = "batch_file_id")
    private Long batchFileId;

    @Column(name = "qc_result_id")
    private Long qcResultId;

    @Column(name = "rule_result_id")
    private Long ruleResultId;

    @Column(name = "correlation_id", length = 64)
    private String correlationId;

    @Column(name = "source_layer", length = 50)
    private String sourceLayer;

    @Column(length = 50)
    private String outcome;

    @Column(name = "payload_json", columnDefinition = "TEXT")
    private String payloadJson;

    @Column(name = "occurred_at", nullable = false)
    private LocalDateTime occurredAt;

    @PrePersist
    protected void onCreate() {
        if (occurredAt == null) {
            occurredAt = AppTime.now();
        }
    }

    @PreUpdate
    @PreRemove
    protected void rejectMutation() {
        throw new UnsupportedOperationException("Business events are append-only");
    }

    public Long getId() { return id; }
    public String getEventType() { return eventType; }
    public void setEventType(String eventType) { this.eventType = eventType; }
    public User getActor() { return actor; }
    public void setActor(User actor) { this.actor = actor; }
    public String getActorRole() { return actorRole; }
    public void setActorRole(String actorRole) { this.actorRole = actorRole; }
    public String getEntityType() { return entityType; }
    public void setEntityType(String entityType) { this.entityType = entityType; }
    public Long getEntityId() { return entityId; }
    public void setEntityId(Long entityId) { this.entityId = entityId; }
    public Long getBatchId() { return batchId; }
    public void setBatchId(Long batchId) { this.batchId = batchId; }
    public Long getBatchFileId() { return batchFileId; }
    public void setBatchFileId(Long batchFileId) { this.batchFileId = batchFileId; }
    public Long getQcResultId() { return qcResultId; }
    public void setQcResultId(Long qcResultId) { this.qcResultId = qcResultId; }
    public Long getRuleResultId() { return ruleResultId; }
    public void setRuleResultId(Long ruleResultId) { this.ruleResultId = ruleResultId; }
    public String getCorrelationId() { return correlationId; }
    public void setCorrelationId(String correlationId) { this.correlationId = correlationId; }
    public String getSourceLayer() { return sourceLayer; }
    public void setSourceLayer(String sourceLayer) { this.sourceLayer = sourceLayer; }
    public String getOutcome() { return outcome; }
    public void setOutcome(String outcome) { this.outcome = outcome; }
    public String getPayloadJson() { return payloadJson; }
    public void setPayloadJson(String payloadJson) { this.payloadJson = payloadJson; }
    public LocalDateTime getOccurredAt() { return occurredAt; }
    public void setOccurredAt(LocalDateTime occurredAt) { this.occurredAt = occurredAt; }
}
