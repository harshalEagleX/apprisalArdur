package com.apprisal.common.entity;

import jakarta.persistence.*;

/**
 * One extraction/QC pipeline phase's measured duration (a child of {@link DocStat}).
 * Identified by its stable {@code stage} key (e.g. "subject_llm", "rules"); the human
 * display name is NOT stored — it is derived from the key at render time
 * (frontend/lib/stageLabels.ts), so wording changes never require a backfill.
 * (The legacy doc_stat_stage.label column is left in place but no longer written.)
 */
@Entity
@Table(name = "doc_stat_stage",
       indexes = { @Index(name = "idx_doc_stat_stage_parent", columnList = "doc_stat_id") })
public class DocStatStage {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "doc_stat_id", nullable = false)
    private DocStat docStat;

    @Column(name = "stage", length = 64)  private String stage;
    @Column(name = "ms")                  private Double ms;
    @Column(name = "pct_of_pipeline")     private Double pctOfPipeline;
    // Groq cost split when this stage made LLM calls (measured).
    @Column(name = "llm_calls")           private Integer llmCalls;
    @Column(name = "inference_ms")        private Double inferenceMs;
    @Column(name = "throttle_wait_ms")    private Double throttleWaitMs;
    @Column(name = "ordinal")             private Integer ordinal;

    protected DocStatStage() {}

    public DocStatStage(String stage, Double ms, Double pctOfPipeline,
                        Integer llmCalls, Double inferenceMs, Double throttleWaitMs, Integer ordinal) {
        this.stage = stage; this.ms = ms;
        this.pctOfPipeline = pctOfPipeline; this.llmCalls = llmCalls;
        this.inferenceMs = inferenceMs; this.throttleWaitMs = throttleWaitMs; this.ordinal = ordinal;
    }

    public void setDocStat(DocStat d) { this.docStat = d; }

    public Long getId()             { return id; }
    public String getStage()        { return stage; }
    public Double getMs()           { return ms; }
    public Double getPctOfPipeline(){ return pctOfPipeline; }
    public Integer getLlmCalls()    { return llmCalls; }
    public Double getInferenceMs()  { return inferenceMs; }
    public Double getThrottleWaitMs(){ return throttleWaitMs; }
    public Integer getOrdinal()     { return ordinal; }
}
