package com.apprisal.common.entity;

import com.apprisal.common.util.AppTime;
import jakarta.persistence.*;
import java.time.LocalDateTime;

/**
 * Captures detailed OCR/ML performance data for every processed file.
 * Feeds the Processing Insights, OCR Insights, and ML Insights analytics sections.
 */
@Entity
@Table(name = "processing_metrics",
       indexes = {
           @Index(name = "idx_pm_qc_result",    columnList = "qc_result_id"),
           @Index(name = "idx_pm_created_at",   columnList = "created_at DESC"),
           @Index(name = "idx_pm_session",      columnList = "operator_session_id"),
           @Index(name = "idx_pm_cache_hit",    columnList = "cache_hit"),
           @Index(name = "idx_pm_model_version",columnList = "model_version")
       })
public class ProcessingMetrics {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "qc_result_id", nullable = false)
    private QCResult qcResult;

    @Column(name = "operator_session_id")
    private Long operatorSessionId;

    @Column(name = "correlation_id", length = 64)
    private String correlationId;

    // ── Timing ────────────────────────────────────────────────────────────────
    @Column(name = "total_processing_ms")
    private Long totalProcessingMs;

    @Column(name = "ocr_time_ms")
    private Long ocrTimeMs;

    @Column(name = "queue_wait_ms")
    private Long queueWaitMs;

    // ── OCR quality ───────────────────────────────────────────────────────────
    @Column(name = "ocr_confidence_avg")
    private Double ocrConfidenceAvg;

    @Column(name = "ocr_confidence_min")
    private Double ocrConfidenceMin;

    @Column(name = "fields_extracted")
    private Integer fieldsExtracted;

    @Column(name = "fields_low_confidence")
    private Integer fieldsLowConfidence;

    @Column(name = "extraction_method", length = 50)
    private String extractionMethod;

    @Column(name = "pages_processed")
    private Integer pagesProcessed;

    // ── Rules / ML ────────────────────────────────────────────────────────────
    @Column(name = "rule_pass_rate")
    private Double rulePassRate;

    @Column(name = "rules_total")
    private Integer rulesTotal;

    @Column(name = "rules_passed")
    private Integer rulesPassed;

    @Column(name = "rules_failed")
    private Integer rulesFailed;

    @Column(name = "rules_verify")
    private Integer rulesVerify;

    @Column(name = "model_version", length = 50)
    private String modelVersion;

    // ── Infrastructure ────────────────────────────────────────────────────────
    @Column(name = "retry_count")
    private Integer retryCount = 0;

    @Column(name = "cache_hit")
    private Boolean cacheHit = false;

    @Column(name = "file_size_bytes")
    private Long fileSizeBytes;

    @Column(name = "created_at")
    private LocalDateTime createdAt;

    @PrePersist
    protected void onCreate() { createdAt = AppTime.now(); }

    // ── Builder ───────────────────────────────────────────────────────────────
    public static Builder builder() { return new Builder(); }

    public static class Builder {
        private final ProcessingMetrics m = new ProcessingMetrics();
        public Builder qcResult(QCResult v)          { m.qcResult = v;             return this; }
        public Builder operatorSessionId(Long v)     { m.operatorSessionId = v;    return this; }
        public Builder correlationId(String v)       { m.correlationId = v;        return this; }
        public Builder totalProcessingMs(Long v)     { m.totalProcessingMs = v;    return this; }
        public Builder ocrTimeMs(Long v)             { m.ocrTimeMs = v;            return this; }
        public Builder queueWaitMs(Long v)           { m.queueWaitMs = v;          return this; }
        public Builder ocrConfidenceAvg(Double v)    { m.ocrConfidenceAvg = v;     return this; }
        public Builder ocrConfidenceMin(Double v)    { m.ocrConfidenceMin = v;     return this; }
        public Builder fieldsExtracted(Integer v)    { m.fieldsExtracted = v;      return this; }
        public Builder fieldsLowConfidence(Integer v){ m.fieldsLowConfidence = v;  return this; }
        public Builder extractionMethod(String v)    { m.extractionMethod = v;     return this; }
        public Builder pagesProcessed(Integer v)     { m.pagesProcessed = v;       return this; }
        public Builder rulePassRate(Double v)        { m.rulePassRate = v;         return this; }
        public Builder rulesTotal(Integer v)         { m.rulesTotal = v;           return this; }
        public Builder rulesPassed(Integer v)        { m.rulesPassed = v;          return this; }
        public Builder rulesFailed(Integer v)        { m.rulesFailed = v;          return this; }
        public Builder rulesVerify(Integer v)        { m.rulesVerify = v;          return this; }
        public Builder modelVersion(String v)        { m.modelVersion = v;         return this; }
        public Builder retryCount(Integer v)         { m.retryCount = v;           return this; }
        public Builder cacheHit(Boolean v)           { m.cacheHit = v;             return this; }
        public Builder fileSizeBytes(Long v)         { m.fileSizeBytes = v;        return this; }
        public ProcessingMetrics build()             { return m; }
    }

    // ── Getters ───────────────────────────────────────────────────────────────
    public Long getId()                     { return id; }
    public QCResult getQcResult()           { return qcResult; }
    public Long getOperatorSessionId()      { return operatorSessionId; }
    public String getCorrelationId()        { return correlationId; }
    public Long getTotalProcessingMs()      { return totalProcessingMs; }
    public Long getOcrTimeMs()              { return ocrTimeMs; }
    public Long getQueueWaitMs()            { return queueWaitMs; }
    public Double getOcrConfidenceAvg()     { return ocrConfidenceAvg; }
    public Double getOcrConfidenceMin()     { return ocrConfidenceMin; }
    public Integer getFieldsExtracted()     { return fieldsExtracted; }
    public Integer getFieldsLowConfidence() { return fieldsLowConfidence; }
    public String getExtractionMethod()     { return extractionMethod; }
    public Integer getPagesProcessed()      { return pagesProcessed; }
    public Double getRulePassRate()         { return rulePassRate; }
    public Integer getRulesTotal()          { return rulesTotal; }
    public Integer getRulesPassed()         { return rulesPassed; }
    public Integer getRulesFailed()         { return rulesFailed; }
    public Integer getRulesVerify()         { return rulesVerify; }
    public String getModelVersion()         { return modelVersion; }
    public Integer getRetryCount()          { return retryCount; }
    public Boolean getCacheHit()            { return cacheHit; }
    public Long getFileSizeBytes()          { return fileSizeBytes; }
    public LocalDateTime getCreatedAt()     { return createdAt; }
}
