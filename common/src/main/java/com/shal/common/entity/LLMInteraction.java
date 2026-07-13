package com.shal.common.entity;

import com.shal.common.util.AppTime;
import jakarta.persistence.*;
import java.time.LocalDateTime;

/**
 * One stored LLM exchange for one checklist item, mirrored from the SHALqc
 * language response ({@code llm_interactions[]}). The reviewer card links here via
 * {@link QCRuleResult#getLlmInteractionId()} = {@link #interactionId}, so the
 * "why this verdict" drawer is a pure read (request packet + parsed response + the
 * raw model text + which model/lane judged it). Enables replay + audit.
 *
 * Not @Audited: machine-generated, high-volume; the audit trail for reviewer
 * decisions lives on QCRuleResult / BusinessEvent, not here.
 */
@Entity
@Table(name = "llm_interaction",
       indexes = {
           @Index(name = "idx_llm_interaction_qcresult", columnList = "qc_result_id"),
           @Index(name = "idx_llm_interaction_iid", columnList = "interaction_id", unique = true)
       })
public class LLMInteraction {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    /** The SHALqc-side interaction id (uuid) — what the card's llmInteractionId points at. */
    @Column(name = "interaction_id", nullable = false, length = 40)
    private String interactionId;

    @Column(name = "qc_result_id", nullable = false)
    private Long qcResultId;

    @Column(name = "item_id", length = 32)
    private String itemId;

    @Column(name = "call_type", length = 64)
    private String callType;

    @Column(name = "prompt_version", length = 32)
    private String promptVersion;

    @Column(name = "batch_id", length = 64)
    private String batchId;

    @Column(name = "provider", length = 24)
    private String provider;

    @Column(name = "model", length = 64)
    private String model;

    @Column(name = "latency_ms")
    private Double latencyMs;

    @Column(name = "cache_hit")
    private Boolean cacheHit = false;

    @Column(name = "request_json", columnDefinition = "TEXT")
    private String requestJson;

    @Column(name = "response_json", columnDefinition = "TEXT")
    private String responseJson;

    @Column(name = "raw_response", columnDefinition = "TEXT")
    private String rawResponse;

    @Column(name = "created_at")
    private LocalDateTime createdAt;

    public LLMInteraction() {}

    @PrePersist
    protected void onCreate() {
        createdAt = AppTime.now();
    }

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public String getInteractionId() { return interactionId; }
    public void setInteractionId(String interactionId) { this.interactionId = interactionId; }

    public Long getQcResultId() { return qcResultId; }
    public void setQcResultId(Long qcResultId) { this.qcResultId = qcResultId; }

    public String getItemId() { return itemId; }
    public void setItemId(String itemId) { this.itemId = itemId; }

    public String getCallType() { return callType; }
    public void setCallType(String callType) { this.callType = callType; }

    public String getPromptVersion() { return promptVersion; }
    public void setPromptVersion(String promptVersion) { this.promptVersion = promptVersion; }

    public String getBatchId() { return batchId; }
    public void setBatchId(String batchId) { this.batchId = batchId; }

    public String getProvider() { return provider; }
    public void setProvider(String provider) { this.provider = provider; }

    public String getModel() { return model; }
    public void setModel(String model) { this.model = model; }

    public Double getLatencyMs() { return latencyMs; }
    public void setLatencyMs(Double latencyMs) { this.latencyMs = latencyMs; }

    public Boolean getCacheHit() { return cacheHit; }
    public void setCacheHit(Boolean cacheHit) { this.cacheHit = cacheHit; }

    public String getRequestJson() { return requestJson; }
    public void setRequestJson(String requestJson) { this.requestJson = requestJson; }

    public String getResponseJson() { return responseJson; }
    public void setResponseJson(String responseJson) { this.responseJson = responseJson; }

    public String getRawResponse() { return rawResponse; }
    public void setRawResponse(String rawResponse) { this.rawResponse = rawResponse; }

    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime createdAt) { this.createdAt = createdAt; }
}
