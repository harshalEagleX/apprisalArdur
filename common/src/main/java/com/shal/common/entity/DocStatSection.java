package com.shal.common.entity;

import jakarta.persistence.*;

/**
 * One QC section's measured rule-evaluation time (a child of {@link DocStat}).
 * e.g. SUBJECT, SALES_COMPARISON — summed from the per-rule timings.
 */
@Entity
@Table(name = "doc_stat_section",
       indexes = { @Index(name = "idx_doc_stat_section_parent", columnList = "doc_stat_id") })
public class DocStatSection {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "doc_stat_id", nullable = false)
    private DocStat docStat;

    @Column(name = "section", length = 64) private String section;
    @Column(name = "label")                private String label;
    @Column(name = "ms")                   private Double ms;
    @Column(name = "rule_count")           private Integer ruleCount;
    @Column(name = "pct_of_rules")         private Double pctOfRules;
    @Column(name = "ordinal")              private Integer ordinal;

    protected DocStatSection() {}

    public DocStatSection(String section, String label, Double ms, Integer ruleCount,
                          Double pctOfRules, Integer ordinal) {
        this.section = section; this.label = label; this.ms = ms;
        this.ruleCount = ruleCount; this.pctOfRules = pctOfRules; this.ordinal = ordinal;
    }

    public void setDocStat(DocStat d) { this.docStat = d; }

    public Long getId()          { return id; }
    public String getSection()   { return section; }
    public String getLabel()     { return label; }
    public Double getMs()        { return ms; }
    public Integer getRuleCount(){ return ruleCount; }
    public Double getPctOfRules(){ return pctOfRules; }
    public Integer getOrdinal()  { return ordinal; }
}
