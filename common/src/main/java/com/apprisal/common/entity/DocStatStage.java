package com.apprisal.common.entity;

import jakarta.persistence.*;

/**
 * One extraction/QC pipeline phase's measured duration (a child of {@link DocStat}).
 * e.g. "Appraisal OCR + field extraction", "QC rule evaluation".
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
    @Column(name = "label")               private String label;
    @Column(name = "ms")                  private Double ms;
    @Column(name = "pct_of_pipeline")     private Double pctOfPipeline;
    @Column(name = "ordinal")             private Integer ordinal;

    protected DocStatStage() {}

    public DocStatStage(String stage, String label, Double ms, Double pctOfPipeline, Integer ordinal) {
        this.stage = stage; this.label = label; this.ms = ms;
        this.pctOfPipeline = pctOfPipeline; this.ordinal = ordinal;
    }

    public void setDocStat(DocStat d) { this.docStat = d; }

    public Long getId()             { return id; }
    public String getStage()        { return stage; }
    public String getLabel()        { return label; }
    public Double getMs()           { return ms; }
    public Double getPctOfPipeline(){ return pctOfPipeline; }
    public Integer getOrdinal()     { return ordinal; }
}
