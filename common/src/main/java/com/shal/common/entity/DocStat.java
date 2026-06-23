package com.shal.common.entity;

import com.shal.common.util.AppTime;
import jakarta.persistence.*;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;

/**
 * Per-appraisal QC timing record — the "docStats" feature.
 *
 * One row per processed appraisal (per QCResult). Holds the real, measured
 * per-stage / per-section / per-rule timings reported by the Python engine,
 * plus denormalized identity + headline fields so the admin list view can be
 * rendered and searched without loading the child collections.
 *
 * Java-owned table, managed by JPA (ddl-auto=update) per the project DB policy.
 */
@Entity
@Table(name = "doc_stat",
       indexes = {
           @Index(name = "idx_doc_stat_qc_result", columnList = "qc_result_id"),
           @Index(name = "idx_doc_stat_batch",     columnList = "batch_id"),
           @Index(name = "idx_doc_stat_created",   columnList = "created_at DESC"),
           @Index(name = "idx_doc_stat_filename",  columnList = "filename")
       })
public class DocStat {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    // Link back to the QC result this timing belongs to (one timing per result).
    @OneToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "qc_result_id")
    private QCResult qcResult;

    // ── Denormalized identity (for list/search without joins) ──────────────────
    @Column(name = "batch_file_id") private Long batchFileId;
    @Column(name = "batch_id")      private Long batchId;
    @Column(name = "client_id")     private Long clientId;
    @Column(name = "filename")      private String filename;
    @Column(name = "client_name")   private String clientName;
    @Column(name = "qc_decision", length = 32) private String qcDecision;

    // ── Headline timings (all real perf_counter measurements, milliseconds) ────
    @Column(name = "total_ms")             private Double totalMs;
    @Column(name = "rule_engine_ms")       private Double ruleEngineMs;
    @Column(name = "measured_pipeline_ms") private Double measuredPipelineMs;
    @Column(name = "rule_count")           private Integer ruleCount;

    @Column(name = "slowest_stage_label")   private String slowestStageLabel;
    @Column(name = "slowest_stage_ms")      private Double slowestStageMs;
    @Column(name = "slowest_section_label") private String slowestSectionLabel;
    @Column(name = "slowest_section_ms")    private Double slowestSectionMs;
    @Column(name = "slowest_rule_id")       private String slowestRuleId;
    @Column(name = "slowest_rule_name")     private String slowestRuleName;
    @Column(name = "slowest_rule_ms")       private Double slowestRuleMs;

    // ── Groq/LLM telemetry totals for this run (measured, not estimated) ───────
    @Column(name = "llm_calls")              private Integer llmCalls;
    @Column(name = "llm_inference_ms")       private Double llmInferenceMs;
    @Column(name = "llm_throttle_wait_ms")   private Double llmThrottleWaitMs;
    @Column(name = "rate_limit_hits")        private Integer rateLimitHits;

    @Column(name = "created_at") private LocalDateTime createdAt;

    // ── Breakdown children ─────────────────────────────────────────────────────
    @OneToMany(mappedBy = "docStat", cascade = CascadeType.ALL, orphanRemoval = true)
    private List<DocStatStage> stages = new ArrayList<>();

    @OneToMany(mappedBy = "docStat", cascade = CascadeType.ALL, orphanRemoval = true)
    private List<DocStatSection> sections = new ArrayList<>();

    @OneToMany(mappedBy = "docStat", cascade = CascadeType.ALL, orphanRemoval = true)
    private List<DocStatRule> rules = new ArrayList<>();

    @PrePersist
    protected void onCreate() { if (createdAt == null) createdAt = AppTime.now(); }

    public void addStage(DocStatStage s)   { s.setDocStat(this); stages.add(s); }
    public void addSection(DocStatSection s){ s.setDocStat(this); sections.add(s); }
    public void addRule(DocStatRule r)     { r.setDocStat(this); rules.add(r); }

    public static Builder builder() { return new Builder(); }

    public static class Builder {
        private final DocStat d = new DocStat();
        public Builder qcResult(QCResult v)         { d.qcResult = v;          return this; }
        public Builder batchFileId(Long v)          { d.batchFileId = v;       return this; }
        public Builder batchId(Long v)              { d.batchId = v;           return this; }
        public Builder clientId(Long v)             { d.clientId = v;          return this; }
        public Builder filename(String v)           { d.filename = v;          return this; }
        public Builder clientName(String v)         { d.clientName = v;        return this; }
        public Builder qcDecision(String v)         { d.qcDecision = v;        return this; }
        public Builder totalMs(Double v)            { d.totalMs = v;           return this; }
        public Builder ruleEngineMs(Double v)       { d.ruleEngineMs = v;      return this; }
        public Builder measuredPipelineMs(Double v) { d.measuredPipelineMs = v; return this; }
        public Builder ruleCount(Integer v)         { d.ruleCount = v;         return this; }
        public Builder slowestStageLabel(String v)  { d.slowestStageLabel = v; return this; }
        public Builder slowestStageMs(Double v)     { d.slowestStageMs = v;    return this; }
        public Builder slowestSectionLabel(String v){ d.slowestSectionLabel = v; return this; }
        public Builder slowestSectionMs(Double v)   { d.slowestSectionMs = v;  return this; }
        public Builder slowestRuleId(String v)      { d.slowestRuleId = v;     return this; }
        public Builder slowestRuleName(String v)    { d.slowestRuleName = v;   return this; }
        public Builder slowestRuleMs(Double v)      { d.slowestRuleMs = v;     return this; }
        public Builder llmCalls(Integer v)          { d.llmCalls = v;          return this; }
        public Builder llmInferenceMs(Double v)     { d.llmInferenceMs = v;    return this; }
        public Builder llmThrottleWaitMs(Double v)  { d.llmThrottleWaitMs = v; return this; }
        public Builder rateLimitHits(Integer v)     { d.rateLimitHits = v;     return this; }
        public DocStat build()                      { return d; }
    }

    // ── Getters ────────────────────────────────────────────────────────────────
    public Long getId()                  { return id; }
    public QCResult getQcResult()        { return qcResult; }
    public Long getBatchFileId()         { return batchFileId; }
    public Long getBatchId()             { return batchId; }
    public Long getClientId()            { return clientId; }
    public String getFilename()          { return filename; }
    public String getClientName()        { return clientName; }
    public String getQcDecision()        { return qcDecision; }
    public Double getTotalMs()           { return totalMs; }
    public Double getRuleEngineMs()      { return ruleEngineMs; }
    public Double getMeasuredPipelineMs(){ return measuredPipelineMs; }
    public Integer getRuleCount()        { return ruleCount; }
    public String getSlowestStageLabel() { return slowestStageLabel; }
    public Double getSlowestStageMs()    { return slowestStageMs; }
    public String getSlowestSectionLabel(){ return slowestSectionLabel; }
    public Double getSlowestSectionMs()  { return slowestSectionMs; }
    public String getSlowestRuleId()     { return slowestRuleId; }
    public String getSlowestRuleName()   { return slowestRuleName; }
    public Double getSlowestRuleMs()     { return slowestRuleMs; }
    public Integer getLlmCalls()         { return llmCalls; }
    public Double getLlmInferenceMs()    { return llmInferenceMs; }
    public Double getLlmThrottleWaitMs() { return llmThrottleWaitMs; }
    public Integer getRateLimitHits()    { return rateLimitHits; }
    public LocalDateTime getCreatedAt()  { return createdAt; }
    public List<DocStatStage> getStages()     { return stages; }
    public List<DocStatSection> getSections() { return sections; }
    public List<DocStatRule> getRules()       { return rules; }
}
