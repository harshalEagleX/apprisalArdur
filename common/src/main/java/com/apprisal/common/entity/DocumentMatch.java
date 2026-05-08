package com.apprisal.common.entity;

import com.apprisal.common.util.AppTime;
import jakarta.persistence.*;

import java.time.LocalDateTime;

/**
 * Durable record of how an appraisal document was paired with supporting docs.
 */
@Entity
@Table(name = "document_match",
       uniqueConstraints = {
           @UniqueConstraint(name = "uq_document_match_appraisal_support_type",
                             columnNames = {"appraisal_file_id", "supporting_file_type"})
       },
       indexes = {
           @Index(name = "idx_document_match_supporting", columnList = "supporting_file_id")
       })
public class DocumentMatch {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "appraisal_file_id", nullable = false)
    private BatchFile appraisalFile;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "supporting_file_id")
    private BatchFile supportingFile;

    @Enumerated(EnumType.STRING)
    @Column(name = "supporting_file_type", nullable = false, length = 20)
    private FileType supportingFileType;

    @Column(name = "match_type", nullable = false, length = 50)
    private String matchType;

    @Column(name = "confidence_score", nullable = false)
    private Double confidenceScore = 0.0;

    @Column(name = "match_reason", columnDefinition = "TEXT")
    private String matchReason;

    @Column(name = "ambiguous_candidates_json", columnDefinition = "TEXT")
    private String ambiguousCandidatesJson;

    @Column(name = "rejected_candidates_json", columnDefinition = "TEXT")
    private String rejectedCandidatesJson;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "matched_by")
    private User matchedBy;

    @Column(name = "matched_at", nullable = false)
    private LocalDateTime matchedAt;

    @Column(name = "updated_at", nullable = false)
    private LocalDateTime updatedAt;

    @PrePersist
    protected void onCreate() {
        LocalDateTime now = AppTime.now();
        if (matchedAt == null) matchedAt = now;
        updatedAt = now;
    }

    @PreUpdate
    protected void onUpdate() {
        updatedAt = AppTime.now();
    }

    public Long getId() { return id; }
    public BatchFile getAppraisalFile() { return appraisalFile; }
    public void setAppraisalFile(BatchFile appraisalFile) { this.appraisalFile = appraisalFile; }
    public BatchFile getSupportingFile() { return supportingFile; }
    public void setSupportingFile(BatchFile supportingFile) { this.supportingFile = supportingFile; }
    public FileType getSupportingFileType() { return supportingFileType; }
    public void setSupportingFileType(FileType supportingFileType) { this.supportingFileType = supportingFileType; }
    public String getMatchType() { return matchType; }
    public void setMatchType(String matchType) { this.matchType = matchType; }
    public Double getConfidenceScore() { return confidenceScore; }
    public void setConfidenceScore(Double confidenceScore) { this.confidenceScore = confidenceScore; }
    public String getMatchReason() { return matchReason; }
    public void setMatchReason(String matchReason) { this.matchReason = matchReason; }
    public String getAmbiguousCandidatesJson() { return ambiguousCandidatesJson; }
    public void setAmbiguousCandidatesJson(String ambiguousCandidatesJson) { this.ambiguousCandidatesJson = ambiguousCandidatesJson; }
    public String getRejectedCandidatesJson() { return rejectedCandidatesJson; }
    public void setRejectedCandidatesJson(String rejectedCandidatesJson) { this.rejectedCandidatesJson = rejectedCandidatesJson; }
    public User getMatchedBy() { return matchedBy; }
    public void setMatchedBy(User matchedBy) { this.matchedBy = matchedBy; }
    public LocalDateTime getMatchedAt() { return matchedAt; }
    public void setMatchedAt(LocalDateTime matchedAt) { this.matchedAt = matchedAt; }
    public LocalDateTime getUpdatedAt() { return updatedAt; }
}
