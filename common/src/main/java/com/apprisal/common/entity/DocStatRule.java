package com.apprisal.common.entity;

import jakarta.persistence.*;

/**
 * One QC rule's measured evaluation time (a child of {@link DocStat}).
 * The {@code ms} is the wall-clock time the engine spent running that rule.
 */
@Entity
@Table(name = "doc_stat_rule",
       indexes = {
           @Index(name = "idx_doc_stat_rule_parent", columnList = "doc_stat_id"),
           // the cumulative ranking GROUP BY rule_id scans this table — index it
           @Index(name = "idx_doc_stat_rule_ruleid", columnList = "rule_id")
       })
public class DocStatRule {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "doc_stat_id", nullable = false)
    private DocStat docStat;

    @Column(name = "rule_id", length = 32)  private String ruleId;
    @Column(name = "rule_name")             private String ruleName;
    @Column(name = "section", length = 64)  private String section;
    @Column(name = "status", length = 24)   private String status;
    @Column(name = "ms")                    private Double ms;
    // The rule's headline confidence — pairs time with output quality.
    @Column(name = "confidence")            private Double confidence;
    // Groq cost when this rule made LLM calls (measured); 0 for pure-deterministic rules.
    @Column(name = "llm_calls")             private Integer llmCalls;
    @Column(name = "llm_ms")                private Double llmMs;
    @Column(name = "throttle_ms")           private Double throttleMs;
    @Column(name = "ordinal")               private Integer ordinal;

    protected DocStatRule() {}

    public DocStatRule(String ruleId, String ruleName, String section, String status,
                       Double ms, Double confidence, Integer llmCalls, Double llmMs,
                       Double throttleMs, Integer ordinal) {
        this.ruleId = ruleId; this.ruleName = ruleName; this.section = section;
        this.status = status; this.ms = ms; this.confidence = confidence;
        this.llmCalls = llmCalls; this.llmMs = llmMs; this.throttleMs = throttleMs;
        this.ordinal = ordinal;
    }

    public void setDocStat(DocStat d) { this.docStat = d; }

    public Long getId()         { return id; }
    public String getRuleId()   { return ruleId; }
    public String getRuleName() { return ruleName; }
    public String getSection()  { return section; }
    public String getStatus()   { return status; }
    public Double getMs()       { return ms; }
    public Double getConfidence(){ return confidence; }
    public Integer getLlmCalls(){ return llmCalls; }
    public Double getLlmMs()    { return llmMs; }
    public Double getThrottleMs(){ return throttleMs; }
    public Integer getOrdinal() { return ordinal; }
}
