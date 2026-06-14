package com.apprisal.common.entity;

import com.apprisal.common.util.AppTime;
import jakarta.persistence.*;
import jakarta.persistence.Version;
import org.hibernate.annotations.SQLRestriction;
import org.hibernate.envers.Audited;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;

/**
 * Batch entity representing a collection of appraisal documents.
 *
 * Soft-deleted rows (deleted_at IS NOT NULL) are globally excluded from every
 * JPQL/criteria query via {@link SQLRestriction}, so a deleted batch disappears
 * from the app while its data and audit trail are preserved. A hard purge is a
 * separate, explicit admin action (see BatchService).
 */
@Audited
@Entity
@SQLRestriction("deleted_at IS NULL")
@Table(name = "batch",
       indexes = {
           @Index(name = "idx_batch_status_updated", columnList = "status, updated_at"),
           @Index(name = "idx_batch_file_hash", columnList = "file_hash")
       })
public class Batch {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    private Long version = 0L;

    @Column(name = "parent_batch_id", nullable = false)
    private String parentBatchId;

    @Column(name = "file_hash", length = 64)
    private String fileHash;

    @Column(name = "error_message", columnDefinition = "TEXT")
    private String errorMessage;

    /**
     * Non-fatal intake warnings (e.g. ambiguous document roles — more than one
     * appraisal, engagement, or contract). The batch still processes, but the
     * admin is asked to confirm the intended mapping. Newline-separated.
     */
    @Column(name = "intake_warnings", columnDefinition = "TEXT")
    private String intakeWarnings;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "client_id", nullable = false)
    private Client client;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private BatchStatus status = BatchStatus.UPLOADED;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "assigned_reviewer_id")
    private User assignedReviewer;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "created_by", nullable = false)
    private User createdBy;

    @OneToMany(mappedBy = "batch", cascade = CascadeType.ALL, orphanRemoval = true)
    private List<BatchFile> files = new ArrayList<>();

    /**
     * Denormalized file count — incremented by addFile(), decremented by removeFile().
     * Replaces the @Formula subquery that fired on every batch list row load.
     * ddl-auto: update will auto-add this column on next startup.
     */
    @Column(name = "file_count", nullable = false, columnDefinition = "integer default 0")
    private Integer fileCount = 0;

    @Column(name = "created_at")
    private LocalDateTime createdAt;

    @Column(name = "updated_at")
    private LocalDateTime updatedAt;

    /** Set when the batch is soft-deleted; non-null rows are hidden by @SQLRestriction. */
    @Column(name = "deleted_at")
    private LocalDateTime deletedAt;

    /** Id of the user who soft-deleted the batch (audit). */
    @Column(name = "deleted_by")
    private Long deletedBy;

    public Batch() {
    }

    @PrePersist
    protected void onCreate() {
        LocalDateTime now = AppTime.now();
        createdAt = now;
        updatedAt = now;
    }

    @PreUpdate
    protected void onUpdate() {
        updatedAt = AppTime.now();
    }

    // Getters and Setters
    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public String getParentBatchId() {
        return parentBatchId;
    }

    public void setParentBatchId(String parentBatchId) {
        this.parentBatchId = parentBatchId;
    }

    public Client getClient() {
        return client;
    }

    public void setClient(Client client) {
        this.client = client;
    }

    public BatchStatus getStatus() {
        return status;
    }

    public void setStatus(BatchStatus status) {
        this.status = status;
    }

    public User getAssignedReviewer() {
        return assignedReviewer;
    }

    public void setAssignedReviewer(User assignedReviewer) {
        this.assignedReviewer = assignedReviewer;
    }

    public User getCreatedBy() {
        return createdBy;
    }

    public void setCreatedBy(User createdBy) {
        this.createdBy = createdBy;
    }

    public List<BatchFile> getFiles() {
        return files;
    }

    public void setFiles(List<BatchFile> files) {
        this.files = files;
    }

    public void addFile(BatchFile file) {
        files.add(file);
        file.setBatch(this);
        fileCount = (fileCount != null ? fileCount : 0) + 1;
    }

    public void removeFile(BatchFile file) {
        files.remove(file);
        file.setBatch(null);
        fileCount = Math.max(0, (fileCount != null ? fileCount : 1) - 1);
    }

    public Long getVersion() { return version; }

    public Integer getFileCount() { return fileCount != null ? fileCount : 0; }

    public String getFileHash() { return fileHash; }
    public void setFileHash(String fileHash) { this.fileHash = fileHash; }

    public String getErrorMessage() { return errorMessage; }
    public void setErrorMessage(String errorMessage) { this.errorMessage = errorMessage; }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(LocalDateTime createdAt) {
        this.createdAt = createdAt;
    }

    public LocalDateTime getUpdatedAt() {
        return updatedAt;
    }

    public void setUpdatedAt(LocalDateTime updatedAt) {
        this.updatedAt = updatedAt;
    }

    public LocalDateTime getDeletedAt() {
        return deletedAt;
    }

    public void setDeletedAt(LocalDateTime deletedAt) {
        this.deletedAt = deletedAt;
    }

    public Long getDeletedBy() {
        return deletedBy;
    }

    public void setDeletedBy(Long deletedBy) {
        this.deletedBy = deletedBy;
    }

    public String getIntakeWarnings() {
        return intakeWarnings;
    }

    public void setIntakeWarnings(String intakeWarnings) {
        this.intakeWarnings = intakeWarnings;
    }

    // Builder pattern
    public static BatchBuilder builder() {
        return new BatchBuilder();
    }

    public static class BatchBuilder {
        private Long id;
        private String parentBatchId;
        private Client client;
        private BatchStatus status = BatchStatus.UPLOADED;
        private User assignedReviewer;
        private User createdBy;

        public BatchBuilder id(Long id) {
            this.id = id;
            return this;
        }

        public BatchBuilder parentBatchId(String parentBatchId) {
            this.parentBatchId = parentBatchId;
            return this;
        }

        public BatchBuilder client(Client client) {
            this.client = client;
            return this;
        }

        public BatchBuilder status(BatchStatus status) {
            this.status = status;
            return this;
        }

        public BatchBuilder assignedReviewer(User assignedReviewer) {
            this.assignedReviewer = assignedReviewer;
            return this;
        }

        public BatchBuilder createdBy(User createdBy) {
            this.createdBy = createdBy;
            return this;
        }

        public Batch build() {
            Batch batch = new Batch();
            batch.id = this.id;
            batch.parentBatchId = this.parentBatchId;
            batch.client = this.client;
            batch.status = this.status;
            batch.assignedReviewer = this.assignedReviewer;
            batch.createdBy = this.createdBy;
            return batch;
        }
    }
}
